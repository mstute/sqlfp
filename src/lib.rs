use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use sqlparser::ast::{
    BinaryOperator, Expr, FromTable, JoinConstraint, JoinOperator,
    ObjectNamePart, OrderByKind, Query, SetExpr, Statement,
    TableFactor, UnaryOperator, UpdateTableFromKind,
    Value, WindowType, visit_expressions_mut,
};
use sqlparser::dialect::{GenericDialect, MySqlDialect, PostgreSqlDialect, SQLiteDialect, AnsiDialect, MsSqlDialect, OracleDialect};
use sqlparser::parser::Parser;
use sha2::{Sha256, Digest};
use core::ops::ControlFlow;


#[pyclass(module = "sqlfp")]
#[derive(Clone)]
struct NormalizeResult {
    #[pyo3(get)]
    normalized: String,
    #[pyo3(get)]
    hash: String,
    #[pyo3(get)]
    original: String,
    #[pyo3(get)]
    params: Vec<String>,
}

#[pymethods]
impl NormalizeResult {
    fn __repr__(&self) -> String {
        format!(
            "NormalizeResult(hash='{}', normalized='{}')",
            &self.hash[..8],
            if self.normalized.len() > 50 {
                format!("{}...", &self.normalized[..50])
            } else {
                self.normalized.clone()
            }
        )
    }
}

fn get_dialect(dialect: &str) -> Result<Box<dyn sqlparser::dialect::Dialect>, String> {
    match dialect.to_lowercase().as_str() {
        "mysql" | "mariadb" => Ok(Box::new(MySqlDialect {})),
        "postgresql" | "postgres" => Ok(Box::new(PostgreSqlDialect {})),
        "sqlite" => Ok(Box::new(SQLiteDialect {})),
        "generic" => Ok(Box::new(GenericDialect {})),
        "ansi" => Ok(Box::new(AnsiDialect {})),
        "mssql" => Ok(Box::new(MsSqlDialect {})),
        "oracle" => Ok(Box::new(OracleDialect {})),
        _ => Err(format!("Unsupported dialect: {}", dialect)),
    }
}

/// SQL operator precedence (higher = binds tighter)
fn op_precedence(op: &BinaryOperator) -> u8 {
    match op {
        BinaryOperator::Or => 10,
        BinaryOperator::Xor => 20,
        BinaryOperator::And => 30,
        // NOT (unary) sits at ~35
        BinaryOperator::Eq | BinaryOperator::NotEq
        | BinaryOperator::Lt | BinaryOperator::LtEq
        | BinaryOperator::Gt | BinaryOperator::GtEq
        | BinaryOperator::Spaceship => 40,
        BinaryOperator::BitwiseOr => 50,
        BinaryOperator::BitwiseXor | BinaryOperator::PGBitwiseXor => 55,
        BinaryOperator::BitwiseAnd => 60,
        BinaryOperator::PGBitwiseShiftLeft | BinaryOperator::PGBitwiseShiftRight => 65,
        BinaryOperator::Plus | BinaryOperator::Minus | BinaryOperator::StringConcat => 70,
        BinaryOperator::Multiply | BinaryOperator::Divide | BinaryOperator::Modulo
        | BinaryOperator::MyIntegerDivide | BinaryOperator::DuckIntegerDivide => 80,
        _ => 90,
    }
}

fn unary_precedence(op: &UnaryOperator) -> u8 {
    match op {
        UnaryOperator::Not => 35,
        _ => 85, // unary +/- and others bind tighter than multiplication
    }
}

/// Wrap the content of a Box<Expr> in Expr::Nested (i.e. add parentheses)
fn wrap_in_nested(e: &mut Box<Expr>) {
    let inner = std::mem::replace(e, Box::new(Expr::Value(Value::Null.into())));
    *e = Box::new(Expr::Nested(inner));
}

// ---- Structural normalization (aliases, joins, ORDER BY) ----

/// Normalize equivalent join types to their shorter canonical forms:
/// INNER JOIN → JOIN, LEFT OUTER JOIN → LEFT JOIN, RIGHT OUTER JOIN → RIGHT JOIN
fn normalize_join_operator(op: &mut JoinOperator) {
    let taken = std::mem::replace(op, JoinOperator::CrossJoin(JoinConstraint::None));
    *op = match taken {
        JoinOperator::Inner(c) => JoinOperator::Join(c),
        JoinOperator::LeftOuter(c) => JoinOperator::Left(c),
        JoinOperator::RightOuter(c) => JoinOperator::Right(c),
        other => other,
    };
}

/// Set alias to implicit form (no AS keyword) for all TableFactor variants
fn normalize_table_factor_alias(tf: &mut TableFactor) {
    let alias = match tf {
        TableFactor::Table { ref mut alias, .. }
        | TableFactor::Derived { ref mut alias, .. }
        | TableFactor::TableFunction { ref mut alias, .. }
        | TableFactor::Function { ref mut alias, .. }
        | TableFactor::UNNEST { ref mut alias, .. }
        | TableFactor::JsonTable { ref mut alias, .. }
        | TableFactor::OpenJsonTable { ref mut alias, .. }
        | TableFactor::NestedJoin { ref mut alias, .. }
        | TableFactor::Pivot { ref mut alias, .. }
        | TableFactor::Unpivot { ref mut alias, .. }
        | TableFactor::MatchRecognize { ref mut alias, .. }
        | TableFactor::XmlTable { ref mut alias, .. }
        | TableFactor::SemanticView { ref mut alias, .. } => alias,
    };
    if let Some(ref mut a) = alias {
        a.explicit = false;
    }
}

/// Normalize a TableFactor: recurse into subqueries/nested joins and normalize alias
fn normalize_table_factor(tf: &mut TableFactor) {
    match tf {
        TableFactor::Derived { ref mut subquery, .. } => normalize_query_structure(subquery),
        TableFactor::NestedJoin { ref mut table_with_joins, .. } => {
            normalize_table_with_joins(table_with_joins);
        }
        _ => {}
    }
    normalize_table_factor_alias(tf);
}

/// Normalize a TableWithJoins: the relation, all joins, and their table factors
fn normalize_table_with_joins(twj: &mut sqlparser::ast::TableWithJoins) {
    normalize_table_factor(&mut twj.relation);
    for join in &mut twj.joins {
        normalize_join_operator(&mut join.join_operator);
        normalize_table_factor(&mut join.relation);
    }
}

/// Normalize a SetExpr (query body): SELECT, UNION, etc.
fn normalize_set_expr(body: &mut SetExpr) {
    match body {
        SetExpr::Select(ref mut select) => {
            for twj in &mut select.from {
                normalize_table_with_joins(twj);
            }
        }
        SetExpr::SetOperation { ref mut left, ref mut right, .. } => {
            normalize_set_expr(left);
            normalize_set_expr(right);
        }
        SetExpr::Query(ref mut query) => normalize_query_structure(query),
        _ => {}
    }
}

/// Normalize a Query: CTEs, body, and ORDER BY
fn normalize_query_structure(query: &mut Query) {
    if let Some(ref mut with) = query.with {
        for cte in &mut with.cte_tables {
            normalize_query_structure(&mut cte.query);
        }
    }
    normalize_set_expr(&mut query.body);
    if let Some(ref mut order_by) = query.order_by {
        if let OrderByKind::Expressions(ref mut exprs) = order_by.kind {
            for expr in exprs {
                if expr.options.asc == Some(true) {
                    expr.options.asc = None;
                }
            }
        }
    }
}

/// Entry point: normalize structural elements of a Statement
fn normalize_structure(stmt: &mut Statement) {
    match stmt {
        Statement::Query(ref mut query) => normalize_query_structure(query),
        Statement::Update(ref mut update) => {
            normalize_table_with_joins(&mut update.table);
            if let Some(ref mut from) = update.from {
                let tables = match from {
                    UpdateTableFromKind::BeforeSet(t) | UpdateTableFromKind::AfterSet(t) => t,
                };
                for twj in tables {
                    normalize_table_with_joins(twj);
                }
            }
        }
        Statement::Delete(ref mut delete) => {
            let tables = match &mut delete.from {
                FromTable::WithFromKeyword(t) | FromTable::WithoutKeyword(t) => t,
            };
            for twj in tables {
                normalize_table_with_joins(twj);
            }
        }
        _ => {}
    }
}

// ---- Expression normalization ----

fn normalize_ast(stmt: &mut Statement) {
    // Phase 1: Structural normalization (aliases, joins, ORDER BY)
    normalize_structure(stmt);

    // Phase 2: Expression normalization
    // The visitor is post-order: children are processed before parents.
    // This lets us (1) strip ALL Nested, then (2) re-add only where
    // needed for operator precedence — producing a canonical form.
    visit_expressions_mut(stmt, |expr| {
        // Step 1: Strip ALL Nested (parentheses)
        if matches!(expr, Expr::Nested(_)) {
            let taken = std::mem::replace(expr, Expr::Value(Value::Null.into()));
            if let Expr::Nested(inner) = taken {
                *expr = *inner;
            }
        }

        // Step 2: Re-add Nested where removing parens would change semantics
        match expr {
            Expr::BinaryOp { ref mut left, ref op, ref mut right } => {
                let prec = op_precedence(op);
                // Left child: wrap if strictly lower precedence
                if let Expr::BinaryOp { op: ref child_op, .. } = left.as_ref() {
                    if op_precedence(child_op) < prec {
                        wrap_in_nested(left);
                    }
                }
                // Right child: wrap if lower-or-equal (SQL is left-associative)
                if let Expr::BinaryOp { op: ref child_op, .. } = right.as_ref() {
                    if op_precedence(child_op) <= prec {
                        wrap_in_nested(right);
                    }
                }
            }
            Expr::UnaryOp { op, expr: ref mut inner } => {
                let prec = unary_precedence(op);
                if let Expr::BinaryOp { op: ref child_op, .. } = inner.as_ref() {
                    if op_precedence(child_op) < prec {
                        wrap_in_nested(inner);
                    }
                }
            }
            _ => {}
        }

        // Normalize function names to uppercase (COUNT = count = CoUnT)
        // and strip ASC in window ORDER BY clauses
        if let Expr::Function(ref mut func) = expr {
            for part in &mut func.name.0 {
                if let ObjectNamePart::Identifier(ref mut ident) = part {
                    if ident.quote_style.is_none() {
                        ident.value = ident.value.to_uppercase();
                    }
                }
            }
            if let Some(WindowType::WindowSpec(ref mut spec)) = func.over {
                for ob in &mut spec.order_by {
                    if ob.options.asc == Some(true) {
                        ob.options.asc = None;
                    }
                }
            }
        }

        // Normalize boolean identifiers (TRUE/FALSE/True/true → uppercase)
        // In dialects like MSSQL/Oracle, TRUE/FALSE are parsed as identifiers
        if let Expr::Identifier(ref mut ident) = expr {
            if ident.quote_style.is_none() {
                let upper = ident.value.to_uppercase();
                if upper == "TRUE" || upper == "FALSE" {
                    ident.value = upper;
                }
            }
        }

        // Normalize structure inside subqueries embedded in expressions
        match expr {
            Expr::Subquery(ref mut query) => normalize_query_structure(query),
            Expr::Exists { ref mut subquery, .. } => normalize_query_structure(subquery),
            Expr::InSubquery { ref mut subquery, .. } => normalize_query_structure(subquery),
            _ => {}
        }

        ControlFlow::<()>::Continue(())
    });
}

fn normalize_statement(stmt: &mut Statement, placeholder: &str) -> (String, Vec<String>) {
    let mut params = Vec::new();

    normalize_ast(stmt);

    visit_expressions_mut(stmt, |expr| {
        match expr {
            Expr::Value(ref mut val) => {
                if !matches!(val.value, Value::Null | Value::Placeholder(_)) {
                    params.push(val.to_string());
                    *val = Value::Placeholder(placeholder.to_string()).into();
                }
            }
            // In MSSQL/Oracle, TRUE/FALSE are identifiers, not boolean values.
            // Parameterize them just like Value::Boolean in other dialects.
            Expr::Identifier(ref ident)
                if ident.quote_style.is_none()
                    && matches!(ident.value.to_uppercase().as_str(), "TRUE" | "FALSE") =>
            {
                params.push(ident.value.to_uppercase());
                *expr = Expr::Value(Value::Placeholder(placeholder.to_string()).into());
            }
            // Double-quoted strings are parsed as identifiers by GenericDialect,
            // but they are actually string values in many dialects (e.g. MySQL).
            Expr::Identifier(ref ident) if ident.quote_style == Some('"') => {
                params.push(format!("\"{}\"", ident.value));
                *expr = Expr::Value(Value::Placeholder(placeholder.to_string()).into());
            }
            _ => {}
        }
        ControlFlow::<()>::Continue(())
    });

    (stmt.to_string(), params)
}

fn compute_hash(normalized: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(normalized.as_bytes());
    hex::encode(hasher.finalize())
}

#[pyfunction]
#[pyo3(signature = (sql, dialect="generic", placeholder="?"))]
fn normalize(sql: &str, dialect: &str, placeholder: &str) -> PyResult<NormalizeResult> {
    let dialect_impl = get_dialect(dialect)
        .map_err(|e| PyValueError::new_err(e))?;

    let mut statements = Parser::parse_sql(&*dialect_impl, sql)
        .map_err(|e| PyValueError::new_err(format!("Parse error: {}", e)))?;

    if statements.is_empty() {
        return Err(PyValueError::new_err("No SQL statement found"));
    }

    let stmt = &mut statements[0];
    let (normalized, params) = normalize_statement(stmt, placeholder);
    let hash = compute_hash(&normalized);

    Ok(NormalizeResult {
        normalized,
        hash,
        original: sql.to_string(),
        params,
    })
}

#[pymodule]
fn sqlfp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(normalize, m)?)?;
    // m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_class::<NormalizeResult>()?;
    Ok(())
}
