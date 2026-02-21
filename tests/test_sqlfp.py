from hashlib import sha256
import json
from pathlib import Path

import pytest

import sqlfp

DIALECTS = ["mysql", "postgres", "sqlite", "ansi", "mssql", "oracle"]


def _slug(s: str) -> str:
    return (
        s.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
    )


@pytest.mark.parametrize("placeholder", ["?", "<val>"])
@pytest.mark.parametrize(
    "dialect",
    DIALECTS,
)
def test_sqlfp_normalize_basics(dialect, placeholder):
    query = "SELECT * FROM users WHERE id = 123"
    # placeholder = "<val>"
    result = sqlfp.normalize(
        sql=query, dialect=dialect, placeholder=placeholder
    )
    assert result.hash == sha256(result.normalized.encode()).hexdigest()
    assert result.normalized == query.replace("123", placeholder)
    assert result.original == query
    assert result.params == ["123"]
    print(f"Hash: {result.hash}")
    print(f"Normalized: {result.normalized}")
    print(f"Params: {result.params}")


def test_sqlfp_normalize_unknown_dialect():
    with pytest.raises(ValueError):
        sqlfp.normalize(sql="SELECT 1", dialect="not_a_dialect")


def test_sqlfp_normalize_parse_error():
    with pytest.raises(ValueError) as error:
        sqlfp.normalize(sql="SELECT * TROM", dialect="mariadb")
    assert str(error.value).startswith(
        "Parse error: sql parser error: Expected: end of statement,"
    )


CASES = [
    {
        "name": "basic select / parentheses / semicolon",
        "dialects": DIALECTS,
        "variants": [
            "SELECT 1;",
            "SELECT (1);",
        ],
    },
    {
        "name": "columns / comments / whitespace / missing semicolon",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id, email FROM users;",
            "SELECT id, email FROM users",
            "SELECT id, email /* hello */ FROM users;",
            "SELECT id, /*hello1*/ email /* hello2*/ FROM    users;",
        ],
    },
    {
        "name": "where eq (values should be normalized)",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE id = 42;",
            "SELECT * FROM users WHERE id = 324324;",
            "SELECT * FROM users WHERE id = 'bob';",
        ],
    },
    {
        "name": "boolean + null (case-insensitive)",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE is_active = TRUE AND deleted_at IS NULL;",
            "SELECT * FROM users WHERE is_active = False AND deleted_at IS null;",
            "SELECT * FROM users WHERE is_active = FALSE AND deleted_at IS Null;",
        ],
    },
    {
        "name": "parentheses + OR/AND + string variants",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE (role = 'admin' OR role = 'notstaff') AND is_active = true;",
            "SELECT * FROM users WHERE (role = 'bob' OR role = 'staff') AND is_active = tRue;",
            "SELECT * FROM users WHERE (role = 'john' OR role = 'lead') AND is_active = FaLse;",
            'SELECT * FROM users WHERE (role = "ignacio" OR role = "stuff") AND is_active = TrUe;',
        ],
    },
    {
        "name": "IN list + comments",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE id IN (1, 2, 3, 4, '5');",
            "SELECT * FROM users WHERE id IN (1, /*2, */ 1234444, 3, 4, 5);",
        ],
    },
    {
        "name": "NOT IN list + whitespace + comments",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE id NOT IN (10, 20, 30);",
            "SELECT * FROM users   wheRe id NOT IN (10, 20, '30');",
            "SELECT * FROM   users WHERE id NOT IN (/* great query*/ 10, 1, 30);",
        ],
    },
    {
        "name": "BETWEEN + date strings",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM events WHERE created_at BETWEEN '2024-01-01' AND '2024-12-31';",
            "SELECT * FROM events WHERE created_at between  '1010-12-13' AND '12-12-12';",
        ],
    },
    {
        "name": "LIKE patterns",
        "dialects": DIALECTS,
        "variants": [
            "SELECT a FROM users WHERE email LIKE '%@example.com';",
            "SELECT a FROM users WHERE email LIKE '%@bob%';",
            "SELECT a FROM users WHERE email LIKE '%bob@world-company.com';",
        ],
    },
    {
        "name": "quoted identifiers (postgres/sqlite only)",
        "dialects": ["postgres", "postgresql", "sqlite"],
        "variants": [
            'SELECT "User".id, "User".email FROM "User" WHERE "User".id = 1;',
            'SELECT "User".id, "User".email FROM "User" WHERE "User".id = 123;',
        ],
    },
    # -------------------------
    # ORDER BY / LIMIT / OFFSET
    # -------------------------
    {
        "name": "order_by_+_limit",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id FROM users ORDER BY id LIMIT 10;",
            "SELECT id FROM users ORDER BY id ASC LIMIT 10;",
            "SELECT id FROM users ORDER BY id LIMIT 00010;",
        ],
    },
    {
        "name": "order by + offset + limit",
        "dialects": ["postgres", "postgresql", "sqlite"],
        "variants": [
            "SELECT id FROM users ORDER BY id LIMIT 10 OFFSET 20;",
            "SELECT id FROM users ORDER BY id ASC LIMIT 10 OFFSET 20;",
            "SELECT id FROM users ORDER BY id LIMIT 00010 OFFSET 00020;",
        ],
    },
    {
        "name": "order by + limit offset (mysql style)",
        "dialects": ["mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT id FROM users ORDER BY id LIMIT 20, 10;",
            "SELECT id FROM users ORDER BY id ASC LIMIT 20, 10;",
            "SELECT id FROM users ORDER BY id LIMIT 00020, 00010;",
        ],
    },
    {
        "name": "distinct",
        "dialects": DIALECTS,
        "variants": [
            "SELECT DISTINCT email FROM users;",
            "SELECT distinct email FROM users;",
            "SELECT DISTINCT(email) FROM users;",
        ],
    },
    # -------------------------
    # Aliases / AS
    # -------------------------
    {
        "name": "table alias with AS",
        "dialects": DIALECTS,
        "variants": [
            "SELECT u.id FROM users AS u;",
            "SELECT u.id FROM users u;",
        ],
    },
    {
        "name": "column alias with AS",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id AS user_id FROM users;",
            "SELECT id user_id FROM users;",
        ],
    },
    {
        "name": "multiple aliases",
        "dialects": DIALECTS,
        "variants": [
            "SELECT u.id AS uid, u.email AS mail FROM users u;",
            "SELECT u.id uid, u.email mail FROM users AS u;",
        ],
    },
    # -------------------------
    # JOINs
    # -------------------------
    {
        "name": "inner join basic",
        "dialects": DIALECTS,
        "variants": [
            "SELECT u.id, o.id FROM users u JOIN orders o ON o.user_id = u.id;",
            "SELECT u.id, o.id FROM users AS u INNER JOIN orders AS o ON o.user_id = u.id;",
        ],
    },
    {
        "name": "left join",
        "dialects": DIALECTS,
        "variants": [
            "SELECT u.id, p.bio FROM users u LEFT JOIN profiles p ON p.user_id = u.id;",
            "SELECT u.id, p.bio FROM users u LEFT OUTER JOIN profiles p ON p.user_id = u.id;",
        ],
    },
    {
        "name": "join_with_multiple_conditions",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM a JOIN b ON a.id = b.a_id AND b.is_active = TRUE;",
            "SELECT * FROM a JOIN b ON (a.id = b.a_id) AND (b.is_active = true);",
        ],
    },
    {
        "name": "join using",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT * FROM users JOIN orders USING (user_id);",
            "SELECT * FROM users INNER JOIN orders USING (user_id);",
        ],
    },
    # -------------------------
    # GROUP BY / HAVING
    # -------------------------
    {
        "name": "group by basic count star",
        "dialects": DIALECTS,
        "variants": [
            "SELECT user_id, COUNT(*) FROM orders GROUP BY user_id;",
            "SELECT user_id, count(*) FROM orders GROUP BY user_id;",
            "SELECT user_id, COUNT( * ) FROM orders GROUP BY user_id;",
        ],
    },
    {
        "name": "group by basic count literal",
        "dialects": DIALECTS,
        "variants": [
            "SELECT user_id, COUNT(1) FROM orders GROUP BY user_id;",
            "SELECT user_id, count(999) FROM orders GROUP BY user_id;",
            "SELECT user_id, COUNT('x') FROM orders GROUP BY user_id;",
        ],
    },
    {
        "name": "group by + having",
        "dialects": DIALECTS,
        "variants": [
            "SELECT user_id, COUNT(*) c FROM orders GROUP BY user_id HAVING COUNT(*) > 10;",
            "SELECT user_id, count( * ) AS c FROM orders GROUP BY user_id HAVING count( * ) > 10;",
        ],
    },
    # -------------------------
    # Subqueries / EXISTS
    # -------------------------
    {
        "name": "subquery in where",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);",
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);",
            "SELECT * FROM users WHERE id IN ( SELECT user_id FROM orders );",
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders /*hello*/);",
        ],
    },
    {
        "name": "exists subquery",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);",
            "SELECT * FROM users u WHERE exists (SELECT 1 FROM orders o WHERE (o.user_id = u.id));",
        ],
    },
    {
        "name": "not exists subquery",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users u WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);",
            "SELECT * FROM users u WHERE not exists (SELECT 1 FROM orders o WHERE (o.user_id = u.id));",
        ],
    },
    # -------------------------
    # UNION / UNION ALL
    # -------------------------
    {
        "name": "union",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id FROM users UNION SELECT id FROM admins;",
            "SELECT id FROM users union seLecT id FRoM admins;",
        ],
    },
    {
        "name": "union all",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id FROM users UNION ALL SELECT id FROM admins;",
            "SELECT id FROM users UNION ALL SELECT id FROM admins;",
        ],
    },
    # -------------------------
    # CASE WHEN
    # -------------------------
    {
        "name": "case when basic",
        "dialects": DIALECTS,
        "variants": [
            "SELECT CASE WHEN is_active = TRUE THEN 1 ELSE 0 END FROM users;",
            "SELECT CASE WHEN is_active = true THEN 1 ELSE 0 END FROM users;",
        ],
    },
    {
        "name": "case when with alias",
        "dialects": DIALECTS,
        "variants": [
            "SELECT CASE WHEN role = 'admin' THEN 'A' ELSE 'U' END AS kind FROM users;",
            "SELECT CASE WHEN role = 'bob' THEN 'A' ELSE 'U' END kind FROM users;",
        ],
    },
    # -------------------------
    # Functions
    # -------------------------
    {
        "name": "coalesce",
        "dialects": DIALECTS,
        "variants": [
            "SELECT COALESCE(email, 'none') FROM users;",
            "SELECT coalesce(email, 'x') FROM users;",
        ],
    },
    {
        "name": "lower/upper",
        "dialects": DIALECTS,
        "variants": [
            "SELECT LOWER(email) FROM users;",
            "SELECT lower(email) FROM users;",
        ],
    },
    {
        "name": "concat",
        "dialects": ["mysql", "mariadb", "postgres", "postgresql", "sqlite"],
        "variants": [
            "SELECT CONCAT(first_name, ' ', last_name) FROM users;",
            "SELECT concat(first_name, ' ', last_name) FROM users;",
        ],
    },
    # -------------------------
    # CASTs (dialect specific)
    # -------------------------
    {
        "name": "cast standard",
        "dialects": DIALECTS,
        "variants": [
            "SELECT CAST(id AS TEXT) FROM users;",
            "SELECT cast(id AS text) FROM users;",
        ],
    },
    {
        "name": "postgres cast operator ::",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT id::text FROM users;",
            "SELECT (id)::text FROM users;",
        ],
    },
    # -------------------------
    # CTE
    # -------------------------
    {
        "name": "cte basic",
        "dialects": DIALECTS,
        "variants": [
            "WITH u AS (SELECT id FROM users) SELECT * FROM u;",
            "WITH u AS (SELECT id FROM users) SELECT * FROM u",
        ],
    },
    {
        "name": "cte with multiple",
        "dialects": DIALECTS,
        "variants": [
            "WITH u AS (SELECT id FROM users), o AS (SELECT user_id FROM orders) SELECT * FROM u JOIN o ON o.user_id = u.id;",
            "WITH u AS (SELECT id FROM users), o AS (SELECT user_id FROM orders) SELECT * FROM u INNER JOIN o ON o.user_id = u.id;",
        ],
    },
    # -------------------------
    # Window functions
    # -------------------------
    {
        "name": "window row_number",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT ROW_NUMBER() OVER (ORDER BY id) FROM users;",
            "SELECT row_number() OVER (ORDER BY id ASC) FROM users;",
        ],
    },
    {
        "name": "window partition by",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT COUNT( 1 ) OVER (PARTITION BY user_id) FROM orders;",
            "SELECT count(1) OVER (PARTITION BY user_id) FROM orders;",
        ],
    },
    # -------------------------
    # INSERT / UPDATE / DELETE
    # -------------------------
    {
        "name": "insert values",
        "dialects": DIALECTS,
        "variants": [
            "INSERT INTO users (id, email) VALUES (1, 'a@example.com');",
            "INSERT INTO users (id, email) VALUES (123, 'b@example.com');",
        ],
    },
    {
        "name": "insert default values",
        "dialects": ["postgres", "postgresql", "sqlite", "mysql", "mariadb"],
        "variants": [
            "INSERT INTO users DEFAULT VALUES;",
            "INSERT INTO users DEFAULT VALUES",
        ],
    },
    {
        "name": "update set",
        "dialects": DIALECTS,
        "variants": [
            "UPDATE users SET email = 'a@example.com' WHERE id = 1;",
            "UPDATE users SET email = 'b@example.com' WHERE id = 2;",
        ],
    },
    {
        "name": "delete where",
        "dialects": DIALECTS,
        "variants": [
            "DELETE FROM users WHERE id = 1;",
            "DELETE FROM users WHERE id = 2;",
        ],
    },
    # -------------------------
    # Dialect-specific quoting
    # -------------------------
    {
        "name": "mysql backtick identifiers",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "SELECT `User`.id, `User`.email FROM `User` WHERE `User`.id = 1;",
            "SELECT `User`.id, `User`.email FROM `User` WHERE `User`.id = 123;",
        ],
    },
    # -------------------------
    # Comments edge cases
    # -------------------------
    {
        "name": "line comments",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id FROM users -- hello\nWHERE id = 1;",
            "SELECT id FROM users -- hello\nWHERE id = 123;",
        ],
    },
    {
        "name": "block comments",
        "dialects": DIALECTS,
        "variants": [
            "SELECT id /* hello */ FROM users WHERE id = 1;",
            "SELECT id /* hello */ FROM users WHERE id = 123;",
        ],
    },
]

HARD_CASES = [
    # -------------------------
    # ORDER BY / GROUP BY positions
    # -------------------------
    {
        "name": "order by position",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT id, email FROM users ORDER BY 1;",
            "SELECT id, email FROM users ORDER BY 1 ASC;",
        ],
    },
    {
        "name": "group by position",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT user_id, COUNT(*) FROM orders GROUP BY 1;",
            "SELECT user_id, COUNT(*) FROM orders GROUP BY 1;",
        ],
    },
    # -------------------------
    # NULLS FIRST/LAST (Postgres)
    # -------------------------
    {
        "name": "order by nulls last postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT id FROM users ORDER BY last_login NULLS LAST;",
            "SELECT id FROM users ORDER BY last_login ASC NULLS LAST;",
        ],
    },
    {
        "name": "order by nulls first postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT id FROM users ORDER BY last_login NULLS FIRST;",
            "SELECT id FROM users ORDER BY last_login ASC NULLS FIRST;",
        ],
    },
    # -------------------------
    # ILIKE (Postgres)
    # -------------------------
    {
        "name": "ilike postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT * FROM users WHERE email ILIKE '%@example.com';",
            "SELECT * FROM users WHERE email ilike '%@bob%';",
        ],
    },
    # -------------------------
    # DISTINCT ON (Postgres)
    # -------------------------
    {
        "name": "distinct on postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT DISTINCT ON (user_id) user_id, created_at FROM orders ORDER BY user_id, created_at DESC;",
            "SELECT DISTINCT ON(user_id) user_id, created_at FROM orders ORDER BY user_id, created_at DESC;",
        ],
    },
    # -------------------------
    # RETURNING (Postgres)
    # -------------------------
    {
        "name": "insert returning postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "INSERT INTO users (email) VALUES ('a@example.com') RETURNING id;",
            "INSERT INTO users (email) VALUES ('b@example.com') RETURNING id;",
        ],
    },
    {
        "name": "update returning postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "UPDATE users SET email = 'a@example.com' WHERE id = 1 RETURNING id;",
            "UPDATE users SET email = 'b@example.com' WHERE id = 2 RETURNING id;",
        ],
    },
    {
        "name": "delete returning postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "DELETE FROM users WHERE id = 1 RETURNING id;",
            "DELETE FROM users WHERE id = 2 RETURNING id;",
        ],
    },
    # -------------------------
    # UPDATE FROM (Postgres)
    # -------------------------
    {
        "name": "update from postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "UPDATE users u SET email = o.email FROM orders o WHERE o.user_id = u.id;",
            "UPDATE users AS u SET email = o.email FROM orders AS o WHERE o.user_id = u.id;",
        ],
    },
    # -------------------------
    # ON CONFLICT (Postgres)
    # -------------------------
    {
        "name": "insert on conflict do nothing postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "INSERT INTO users (email) VALUES ('a@example.com') ON CONFLICT DO NOTHING;",
            "INSERT INTO users (email) VALUES ('b@example.com') ON CONFLICT DO NOTHING;",
        ],
    },
    {
        "name": "insert on conflict do update postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "INSERT INTO users (id, email) VALUES (1, 'a@example.com') ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email;",
            "INSERT INTO users (id, email) VALUES (2, 'b@example.com') ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email;",
        ],
    },
    # -------------------------
    # MySQL: ON DUPLICATE KEY UPDATE
    # -------------------------
    {
        "name": "mysql on duplicate key update",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "INSERT INTO users (id, email) VALUES (1, 'a@example.com') ON DUPLICATE KEY UPDATE email = VALUES(email);",
            "INSERT INTO users (id, email) VALUES (2, 'b@example.com') ON DUPLICATE KEY UPDATE email = VALUES(email);",
        ],
    },
    # -------------------------
    # MySQL: INSERT IGNORE / REPLACE
    # -------------------------
    {
        "name": "mysql insert ignore",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "INSERT IGNORE INTO users (id, email) VALUES (1, 'a@example.com');",
            "INSERT IGNORE INTO users (id, email) VALUES (2, 'b@example.com');",
        ],
    },
    {
        "name": "mysql replace into",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "REPLACE INTO users (id, email) VALUES (1, 'a@example.com');",
            "REPLACE INTO users (id, email) VALUES (2, 'b@example.com');",
        ],
    },
    # -------------------------
    # JSON: Postgres operators
    # -------------------------
    {
        "name": "postgres json extract operator",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT payload->>'email' FROM events;",
            "SELECT payload ->> 'email' FROM events;",
        ],
    },
    {
        "name": "postgres json nested operator",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT payload->'user'->>'id' FROM events;",
            "SELECT payload -> 'user' ->> 'id' FROM events;",
        ],
    },
    # -------------------------
    # JSON: MySQL JSON_EXTRACT
    # -------------------------
    {
        "name": "mysql json_extract",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "SELECT JSON_EXTRACT(payload, '$.user.id') FROM events;",
            "SELECT json_extract(payload, '$.user.id') FROM events;",
        ],
    },
    {
        "name": "mysql json_unquote",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(payload, '$.email')) FROM events;",
            "SELECT json_unquote(json_extract(payload, '$.email')) FROM events;",
        ],
    },
    # -------------------------
    # REGEXP (MySQL)
    # -------------------------
    {
        "name": "mysql regexp",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "SELECT * FROM users WHERE email REGEXP '.*@example\\.com$';",
            "SELECT * FROM users WHERE email regexp '.*@bob\\.com$';",
        ],
    },
    # -------------------------
    # SQLite: LIMIT/OFFSET only
    # -------------------------
    {
        "name": "sqlite limit offset",
        "dialects": ["sqlite"],
        "variants": [
            "SELECT id FROM users ORDER BY id LIMIT 10 OFFSET 20;",
            "SELECT id FROM users ORDER BY id ASC LIMIT 10 OFFSET 20;",
        ],
    },
    # -------------------------
    # WITH RECURSIVE (Postgres + SQLite)
    # -------------------------
    {
        "name": "with recursive",
        "dialects": ["postgres", "postgresql", "sqlite", "mysql", "mariadb"],
        "variants": [
            "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 5) SELECT * FROM t;",
            "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 10) SELECT * FROM t;",
        ],
    },
    # -------------------------
    # EXISTS with correlated subquery
    # -------------------------
    {
        "name": "exists correlated",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.total > 0);",
            "SELECT * FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.total > 999);",
        ],
    },
    # -------------------------
    # IN with tuple (Postgres/MySQL/SQLite)
    # -------------------------
    {
        "name": "row value in",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT * FROM t WHERE (a, b) IN ((1, 2), (3, 4));",
            "SELECT * FROM t WHERE (a, b) IN ((9, 8), (7, 6));",
        ],
    },
    # -------------------------
    # CAST to common types
    # -------------------------
    {
        "name": "cast to int",
        "dialects": DIALECTS,
        "variants": [
            "SELECT CAST(id AS INTEGER) FROM users;",
            "SELECT cast(id as integer) FROM users;",
        ],
    },
    {
        "name": "cast to timestamp",
        "dialects": ["postgres", "postgresql", "mysql", "mariadb", "sqlite"],
        "variants": [
            "SELECT CAST(created_at AS TIMESTAMP) FROM events;",
            "SELECT cast(created_at as timestamp) FROM events;",
        ],
    },
    # -------------------------
    # Postgres: type casts to uuid/timestamptz
    # -------------------------
    {
        "name": "postgres cast uuid",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT id::uuid FROM users;",
            "SELECT (id)::uuid FROM users;",
        ],
    },
    {
        "name": "postgres cast timestamptz",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT created_at::timestamptz FROM events;",
            "SELECT (created_at)::timestamptz FROM events;",
        ],
    },
    # -------------------------
    # Postgres: ANY/ALL
    # -------------------------
    {
        "name": "postgres any",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT * FROM users WHERE id = ANY(ARRAY[1,2,3]);",
            "SELECT * FROM users WHERE id = ANY(ARRAY[9,8,7]);",
        ],
    },
    # -------------------------
    # MySQL: IF() expression
    # -------------------------
    {
        "name": "mysql if expression",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            "SELECT IF(is_active, 1, 0) FROM users;",
            "SELECT if(is_active, 1, 0) FROM users;",
        ],
    },
    # -------------------------
    # COALESCE with multiple args
    # -------------------------
    {
        "name": "coalesce multiple args",
        "dialects": DIALECTS,
        "variants": [
            "SELECT COALESCE(a, b, c, 'x') FROM t;",
            "SELECT coalesce(a, b, c, 'y') FROM t;",
        ],
    },
    # -------------------------
    # HAVING with aggregate
    # -------------------------
    {
        "name": "having aggregate",
        "dialects": DIALECTS,
        "variants": [
            "SELECT user_id, COUNT(*) FROM orders GROUP BY user_id HAVING COUNT(*) >= 10;",
            "SELECT user_id, COUNT(*) FROM orders GROUP BY user_id HAVING COUNT(*) >= 999;",
        ],
    },
    # -------------------------
    # Nested parentheses in WHERE (should unwrap)
    # -------------------------
    {
        "name": "nested parentheses comparisons",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users WHERE (((id = 1)));",
            "SELECT * FROM users WHERE ((id = 999));",
        ],
    },
    # -------------------------
    # Arithmetic expressions
    # -------------------------
    {
        "name": "arithmetic expressions",
        "dialects": DIALECTS,
        "variants": [
            "SELECT (price * quantity) + tax FROM orders;",
            "SELECT ((price * quantity) + tax) FROM orders;",
        ],
    },
    # -------------------------
    # IS DISTINCT FROM (Postgres)
    # -------------------------
    {
        "name": "is distinct from postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT * FROM users WHERE email IS DISTINCT FROM 'a@example.com';",
            "SELECT * FROM users WHERE email IS DISTINCT FROM 'b@example.com';",
        ],
    },
    # -------------------------
    # Postgres: FILTER (WHERE ...) on aggregates
    # -------------------------
    {
        "name": "aggregate filter postgres",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            "SELECT COUNT(*) FILTER (WHERE is_active = TRUE) FROM users;",
            "SELECT COUNT(*) FILTER (WHERE is_active = FALSE) FROM users;",
        ],
    },
    # -------------------------
    # CROSS JOIN
    # -------------------------
    {
        "name": "cross join",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM users CROSS JOIN roles;",
            "SELECT * FROM users CROSS JOIN roles;",
        ],
    },
    # -------------------------
    # Schema-qualified names
    # -------------------------
    {
        "name": "schema qualified names",
        "dialects": DIALECTS,
        "variants": [
            "SELECT * FROM public.users;",
            "SELECT * FROM public.users;",
        ],
    },
    # -------------------------
    # Postgres: double quoted schema/table
    # -------------------------
    {
        "name": "postgres quoted schema table",
        "dialects": ["postgres", "postgresql", "sqlite"],
        "variants": [
            'SELECT * FROM "public"."User";',
            'SELECT * FROM "public"."User";',
        ],
    },
]

ORM_CASES = [
    # ============================================================
    # POSTGRES ORM STYLE (Django / SQLAlchemy)
    # ============================================================
    {
        "name": "orm postgres huge select with many aliases",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."password" AS "col2",
                "auth_user"."last_login" AS "col3",
                "auth_user"."is_superuser" AS "col4",
                "auth_user"."username" AS "col5",
                "auth_user"."first_name" AS "col6",
                "auth_user"."last_name" AS "col7",
                "auth_user"."email" AS "col8",
                "auth_user"."is_staff" AS "col9",
                "auth_user"."is_active" AS "col10",
                "auth_user"."date_joined" AS "col11",
                "profile_profile"."id" AS "col12",
                "profile_profile"."user_id" AS "col13",
                "profile_profile"."company" AS "col14",
                "profile_profile"."job_title" AS "col15",
                "profile_profile"."timezone" AS "col16",
                "profile_profile"."created_at" AS "col17"
            FROM "auth_user"
            LEFT OUTER JOIN "profile_profile"
                ON ("profile_profile"."user_id" = "auth_user"."id")
            WHERE
                ("auth_user"."is_active" = TRUE)
                AND ("auth_user"."email" ILIKE '%@example.com')
            ORDER BY "auth_user"."id" ASC
            LIMIT 50 OFFSET 100;
            """,
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."password" AS "col2",
                "auth_user"."last_login" AS "col3",
                "auth_user"."is_superuser" AS "col4",
                "auth_user"."username" AS "col5",
                "auth_user"."first_name" AS "col6",
                "auth_user"."last_name" AS "col7",
                "auth_user"."email" AS "col8",
                "auth_user"."is_staff" AS "col9",
                "auth_user"."is_active" AS "col10",
                "auth_user"."date_joined" AS "col11",
                "profile_profile"."id" AS "col12",
                "profile_profile"."user_id" AS "col13",
                "profile_profile"."company" AS "col14",
                "profile_profile"."job_title" AS "col15",
                "profile_profile"."timezone" AS "col16",
                "profile_profile"."created_at" AS "col17"
            FROM "auth_user"
            LEFT OUTER JOIN "profile_profile"
                ON ("profile_profile"."user_id" = "auth_user"."id")
            WHERE
                ("auth_user"."is_active" = FALSE)
                AND ("auth_user"."email" ILIKE '%@bob.com')
            ORDER BY "auth_user"."id"
            LIMIT 50 OFFSET 100;
            """,
        ],
    },
    {
        "name": "orm postgres deep joins with select many columns",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT
                "shop_order"."id" AS "col1",
                "shop_order"."user_id" AS "col2",
                "shop_order"."status" AS "col3",
                "shop_order"."total_cents" AS "col4",
                "shop_order"."currency" AS "col5",
                "shop_order"."created_at" AS "col6",
                "shop_order"."updated_at" AS "col7",
                "shop_orderitem"."id" AS "col8",
                "shop_orderitem"."order_id" AS "col9",
                "shop_orderitem"."product_id" AS "col10",
                "shop_orderitem"."quantity" AS "col11",
                "shop_orderitem"."unit_price_cents" AS "col12",
                "catalog_product"."id" AS "col13",
                "catalog_product"."sku" AS "col14",
                "catalog_product"."name" AS "col15",
                "catalog_product"."is_active" AS "col16"
            FROM "shop_order"
            INNER JOIN "shop_orderitem"
                ON ("shop_orderitem"."order_id" = "shop_order"."id")
            INNER JOIN "catalog_product"
                ON ("catalog_product"."id" = "shop_orderitem"."product_id")
            WHERE
                ("shop_order"."user_id" = 123)
                AND ("shop_order"."status" IN ('paid', 'shipped', 'delivered'))
                AND ("catalog_product"."is_active" = TRUE)
            ORDER BY "shop_order"."created_at" DESC, "shop_order"."id" DESC
            LIMIT 200;
            """,
            """
            SELECT
                "shop_order"."id" AS "col1",
                "shop_order"."user_id" AS "col2",
                "shop_order"."status" AS "col3",
                "shop_order"."total_cents" AS "col4",
                "shop_order"."currency" AS "col5",
                "shop_order"."created_at" AS "col6",
                "shop_order"."updated_at" AS "col7",
                "shop_orderitem"."id" AS "col8",
                "shop_orderitem"."order_id" AS "col9",
                "shop_orderitem"."product_id" AS "col10",
                "shop_orderitem"."quantity" AS "col11",
                "shop_orderitem"."unit_price_cents" AS "col12",
                "catalog_product"."id" AS "col13",
                "catalog_product"."sku" AS "col14",
                "catalog_product"."name" AS "col15",
                "catalog_product"."is_active" AS "col16"
            FROM "shop_order"
            INNER JOIN "shop_orderitem"
                ON ("shop_orderitem"."order_id" = "shop_order"."id")
            INNER JOIN "catalog_product"
                ON ("catalog_product"."id" = "shop_orderitem"."product_id")
            WHERE
                ("shop_order"."user_id" = 999999)
                AND ("shop_order"."status" IN ('paid', 'shipped', 'delivered'))
                AND ("catalog_product"."is_active" = FALSE)
            ORDER BY "shop_order"."created_at" DESC, "shop_order"."id" DESC
            LIMIT 200;
            """,
        ],
    },
    {
        "name": "orm postgres correlated subquery exists",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."email" AS "col2"
            FROM "auth_user"
            WHERE EXISTS (
                SELECT 1
                FROM "shop_order"
                WHERE
                    ("shop_order"."user_id" = "auth_user"."id")
                    AND ("shop_order"."status" = 'paid')
                    AND ("shop_order"."total_cents" > 0)
            )
            ORDER BY "auth_user"."id" ASC
            LIMIT 100;
            """,
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."email" AS "col2"
            FROM "auth_user"
            WHERE EXISTS (
                SELECT 1
                FROM "shop_order"
                WHERE
                    ("shop_order"."user_id" = "auth_user"."id")
                    AND ("shop_order"."status" = 'paid')
                    AND ("shop_order"."total_cents" > 999999)
            )
            ORDER BY "auth_user"."id"
            LIMIT 100;
            """,
        ],
    },
    {
        "name": "orm postgres json extract in where",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT
                "events_event"."id" AS "col1",
                "events_event"."created_at" AS "col2",
                "events_event"."payload" AS "col3"
            FROM "events_event"
            WHERE
                ("events_event"."payload"->>'kind' = 'payment')
                AND ("events_event"."payload"->'user'->>'id' = '123')
                AND ("events_event"."created_at" >= '2024-01-01')
            ORDER BY "events_event"."created_at" DESC
            LIMIT 500;
            """,
            """
            SELECT
                "events_event"."id" AS "col1",
                "events_event"."created_at" AS "col2",
                "events_event"."payload" AS "col3"
            FROM "events_event"
            WHERE
                ("events_event"."payload"->>'kind' = 'refund')
                AND ("events_event"."payload"->'user'->>'id' = '999')
                AND ("events_event"."created_at" >= '2000-01-01')
            ORDER BY "events_event"."created_at" DESC
            LIMIT 500;
            """,
        ],
    },
    {
        "name": "orm postgres cte + join + aggregation",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            WITH "recent_orders" AS (
                SELECT
                    "shop_order"."id" AS "id",
                    "shop_order"."user_id" AS "user_id",
                    "shop_order"."total_cents" AS "total_cents",
                    "shop_order"."created_at" AS "created_at"
                FROM "shop_order"
                WHERE
                    ("shop_order"."created_at" >= '2024-01-01')
                    AND ("shop_order"."status" IN ('paid', 'shipped'))
            )
            SELECT
                "recent_orders"."user_id" AS "col1",
                COUNT(*) AS "col2",
                SUM("recent_orders"."total_cents") AS "col3"
            FROM "recent_orders"
            GROUP BY "recent_orders"."user_id"
            HAVING COUNT(*) >= 10
            ORDER BY SUM("recent_orders"."total_cents") DESC
            LIMIT 100;
            """,
            """
            WITH "recent_orders" AS (
                SELECT
                    "shop_order"."id" AS "id",
                    "shop_order"."user_id" AS "user_id",
                    "shop_order"."total_cents" AS "total_cents",
                    "shop_order"."created_at" AS "created_at"
                FROM "shop_order"
                WHERE
                    ("shop_order"."created_at" >= '2000-01-01')
                    AND ("shop_order"."status" IN ('paid', 'shipped'))
            )
            SELECT
                "recent_orders"."user_id" AS "col1",
                COUNT(*) AS "col2",
                SUM("recent_orders"."total_cents") AS "col3"
            FROM "recent_orders"
            GROUP BY "recent_orders"."user_id"
            HAVING COUNT(*) >= 999
            ORDER BY SUM("recent_orders"."total_cents") DESC
            LIMIT 100;
            """,
        ],
    },
    {
        "name": "orm postgres update returning",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            UPDATE "profile_profile"
            SET "timezone" = 'Europe/Paris', "updated_at" = NOW()
            WHERE ("profile_profile"."user_id" = 123)
            RETURNING "profile_profile"."id", "profile_profile"."user_id";
            """,
            """
            UPDATE "profile_profile"
            SET "timezone" = 'America/New_York', "updated_at" = NOW()
            WHERE ("profile_profile"."user_id" = 999)
            RETURNING "profile_profile"."id", "profile_profile"."user_id";
            """,
        ],
    },
    {
        "name": "orm postgres insert on conflict do update returning",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            INSERT INTO "profile_profile" ("user_id", "company", "job_title")
            VALUES (123, 'Acme', 'Engineer')
            ON CONFLICT ("user_id")
            DO UPDATE SET "company" = EXCLUDED."company", "job_title" = EXCLUDED."job_title"
            RETURNING "profile_profile"."id";
            """,
            """
            INSERT INTO "profile_profile" ("user_id", "company", "job_title")
            VALUES (999, 'Globex', 'CTO')
            ON CONFLICT ("user_id")
            DO UPDATE SET "company" = EXCLUDED."company", "job_title" = EXCLUDED."job_title"
            RETURNING "profile_profile"."id";
            """,
        ],
    },
    {
        "name": "orm postgres window function over partition",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT
                "shop_order"."user_id" AS "col1",
                "shop_order"."id" AS "col2",
                ROW_NUMBER() OVER (PARTITION BY "shop_order"."user_id" ORDER BY "shop_order"."created_at" DESC) AS "col3"
            FROM "shop_order"
            WHERE "shop_order"."status" = 'paid'
            ORDER BY "shop_order"."user_id" ASC, "shop_order"."created_at" DESC
            LIMIT 500;
            """,
            """
            SELECT
                "shop_order"."user_id" AS "col1",
                "shop_order"."id" AS "col2",
                ROW_NUMBER() OVER (PARTITION BY "shop_order"."user_id" ORDER BY "shop_order"."created_at" DESC) AS "col3"
            FROM "shop_order"
            WHERE "shop_order"."status" = 'shipped'
            ORDER BY "shop_order"."user_id", "shop_order"."created_at" DESC
            LIMIT 500;
            """,
        ],
    },
    {
        "name": "orm postgres huge in list",
        "dialects": ["postgres", "postgresql"],
        "variants": [
            """
            SELECT "auth_user"."id", "auth_user"."email"
            FROM "auth_user"
            WHERE "auth_user"."id" IN (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20)
            ORDER BY "auth_user"."id" ASC;
            """,
            """
            SELECT "auth_user"."id", "auth_user"."email"
            FROM "auth_user"
            WHERE "auth_user"."id" IN (101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120)
            ORDER BY "auth_user"."id";
            """,
        ],
    },
    # ============================================================
    # MYSQL ORM STYLE (SQLAlchemy / Django)
    # ============================================================
    {
        "name": "orm mysql huge select with backticks and aliases",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            SELECT
                `auth_user`.`id` AS `col1`,
                `auth_user`.`username` AS `col2`,
                `auth_user`.`email` AS `col3`,
                `auth_user`.`is_active` AS `col4`,
                `profile_profile`.`id` AS `col5`,
                `profile_profile`.`user_id` AS `col6`,
                `profile_profile`.`company` AS `col7`,
                `profile_profile`.`job_title` AS `col8`
            FROM `auth_user`
            LEFT OUTER JOIN `profile_profile`
                ON (`profile_profile`.`user_id` = `auth_user`.`id`)
            WHERE
                (`auth_user`.`is_active` = TRUE)
                AND (`auth_user`.`email` LIKE '%@example.com')
            ORDER BY `auth_user`.`id` ASC
            LIMIT 50 OFFSET 100;
            """,
            """
            SELECT
                `auth_user`.`id` AS `col1`,
                `auth_user`.`username` AS `col2`,
                `auth_user`.`email` AS `col3`,
                `auth_user`.`is_active` AS `col4`,
                `profile_profile`.`id` AS `col5`,
                `profile_profile`.`user_id` AS `col6`,
                `profile_profile`.`company` AS `col7`,
                `profile_profile`.`job_title` AS `col8`
            FROM `auth_user`
            LEFT OUTER JOIN `profile_profile`
                ON (`profile_profile`.`user_id` = `auth_user`.`id`)
            WHERE
                (`auth_user`.`is_active` = FALSE)
                AND (`auth_user`.`email` LIKE '%@bob.com')
            ORDER BY `auth_user`.`id`
            LIMIT 50 OFFSET 100;
            """,
        ],
    },
    {
        "name": "orm mysql deep joins + order by",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            SELECT
                `shop_order`.`id` AS `col1`,
                `shop_order`.`user_id` AS `col2`,
                `shop_order`.`status` AS `col3`,
                `shop_order`.`total_cents` AS `col4`,
                `shop_orderitem`.`id` AS `col5`,
                `shop_orderitem`.`order_id` AS `col6`,
                `shop_orderitem`.`product_id` AS `col7`,
                `shop_orderitem`.`quantity` AS `col8`,
                `catalog_product`.`id` AS `col9`,
                `catalog_product`.`sku` AS `col10`,
                `catalog_product`.`name` AS `col11`
            FROM `shop_order`
            INNER JOIN `shop_orderitem`
                ON (`shop_orderitem`.`order_id` = `shop_order`.`id`)
            INNER JOIN `catalog_product`
                ON (`catalog_product`.`id` = `shop_orderitem`.`product_id`)
            WHERE
                (`shop_order`.`user_id` = 123)
                AND (`shop_order`.`status` IN ('paid', 'shipped', 'delivered'))
            ORDER BY `shop_order`.`created_at` DESC, `shop_order`.`id` DESC
            LIMIT 200;
            """,
            """
            SELECT
                `shop_order`.`id` AS `col1`,
                `shop_order`.`user_id` AS `col2`,
                `shop_order`.`status` AS `col3`,
                `shop_order`.`total_cents` AS `col4`,
                `shop_orderitem`.`id` AS `col5`,
                `shop_orderitem`.`order_id` AS `col6`,
                `shop_orderitem`.`product_id` AS `col7`,
                `shop_orderitem`.`quantity` AS `col8`,
                `catalog_product`.`id` AS `col9`,
                `catalog_product`.`sku` AS `col10`,
                `catalog_product`.`name` AS `col11`
            FROM `shop_order`
            INNER JOIN `shop_orderitem`
                ON (`shop_orderitem`.`order_id` = `shop_order`.`id`)
            INNER JOIN `catalog_product`
                ON (`catalog_product`.`id` = `shop_orderitem`.`product_id`)
            WHERE
                (`shop_order`.`user_id` = 999999)
                AND (`shop_order`.`status` IN ('paid', 'shipped', 'delivered'))
            ORDER BY `shop_order`.`created_at` DESC, `shop_order`.`id` DESC
            LIMIT 200;
            """,
        ],
    },
    {
        "name": "orm mysql correlated exists",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            SELECT
                `auth_user`.`id` AS `col1`,
                `auth_user`.`email` AS `col2`
            FROM `auth_user`
            WHERE EXISTS (
                SELECT 1
                FROM `shop_order`
                WHERE
                    (`shop_order`.`user_id` = `auth_user`.`id`)
                    AND (`shop_order`.`status` = 'paid')
                    AND (`shop_order`.`total_cents` > 0)
            )
            ORDER BY `auth_user`.`id` ASC
            LIMIT 100;
            """,
            """
            SELECT
                `auth_user`.`id` AS `col1`,
                `auth_user`.`email` AS `col2`
            FROM `auth_user`
            WHERE EXISTS (
                SELECT 1
                FROM `shop_order`
                WHERE
                    (`shop_order`.`user_id` = `auth_user`.`id`)
                    AND (`shop_order`.`status` = 'paid')
                    AND (`shop_order`.`total_cents` > 999999)
            )
            ORDER BY `auth_user`.`id`
            LIMIT 100;
            """,
        ],
    },
    {
        "name": "orm mysql json_extract where",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            SELECT
                `events_event`.`id` AS `col1`,
                `events_event`.`created_at` AS `col2`,
                `events_event`.`payload` AS `col3`
            FROM `events_event`
            WHERE
                (JSON_EXTRACT(`events_event`.`payload`, '$.kind') = 'payment')
                AND (JSON_EXTRACT(`events_event`.`payload`, '$.user.id') = '123')
            ORDER BY `events_event`.`created_at` DESC
            LIMIT 500;
            """,
            """
            SELECT
                `events_event`.`id` AS `col1`,
                `events_event`.`created_at` AS `col2`,
                `events_event`.`payload` AS `col3`
            FROM `events_event`
            WHERE
                (JSON_EXTRACT(`events_event`.`payload`, '$.kind') = 'refund')
                AND (JSON_EXTRACT(`events_event`.`payload`, '$.user.id') = '999')
            ORDER BY `events_event`.`created_at` DESC
            LIMIT 500;
            """,
        ],
    },
    {
        "name": "orm mysql insert on duplicate key update",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            INSERT INTO `profile_profile` (`user_id`, `company`, `job_title`)
            VALUES (123, 'Acme', 'Engineer')
            ON DUPLICATE KEY UPDATE `company` = VALUES(`company`), `job_title` = VALUES(`job_title`);
            """,
            """
            INSERT INTO `profile_profile` (`user_id`, `company`, `job_title`)
            VALUES (999, 'Globex', 'CTO')
            ON DUPLICATE KEY UPDATE `company` = VALUES(`company`), `job_title` = VALUES(`job_title`);
            """,
        ],
    },
    {
        "name": "orm mysql huge in list",
        "dialects": ["mysql", "mariadb"],
        "variants": [
            """
            SELECT `auth_user`.`id`, `auth_user`.`email`
            FROM `auth_user`
            WHERE `auth_user`.`id` IN (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20)
            ORDER BY `auth_user`.`id` ASC;
            """,
            """
            SELECT `auth_user`.`id`, `auth_user`.`email`
            FROM `auth_user`
            WHERE `auth_user`.`id` IN (101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120)
            ORDER BY `auth_user`.`id`;
            """,
        ],
    },
    # ============================================================
    # SQLITE ORM STYLE
    # ============================================================
    {
        "name": "orm sqlite huge select",
        "dialects": ["sqlite"],
        "variants": [
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."username" AS "col2",
                "auth_user"."email" AS "col3",
                "auth_user"."is_active" AS "col4",
                "profile_profile"."id" AS "col5",
                "profile_profile"."user_id" AS "col6",
                "profile_profile"."company" AS "col7",
                "profile_profile"."job_title" AS "col8"
            FROM "auth_user"
            LEFT OUTER JOIN "profile_profile"
                ON ("profile_profile"."user_id" = "auth_user"."id")
            WHERE
                ("auth_user"."is_active" = 1)
                AND ("auth_user"."email" LIKE '%@example.com')
            ORDER BY "auth_user"."id" ASC
            LIMIT 50 OFFSET 100;
            """,
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."username" AS "col2",
                "auth_user"."email" AS "col3",
                "auth_user"."is_active" AS "col4",
                "profile_profile"."id" AS "col5",
                "profile_profile"."user_id" AS "col6",
                "profile_profile"."company" AS "col7",
                "profile_profile"."job_title" AS "col8"
            FROM "auth_user"
            LEFT OUTER JOIN "profile_profile"
                ON ("profile_profile"."user_id" = "auth_user"."id")
            WHERE
                ("auth_user"."is_active" = 0)
                AND ("auth_user"."email" LIKE '%@bob.com')
            ORDER BY "auth_user"."id"
            LIMIT 50 OFFSET 100;
            """,
        ],
    },
    {
        "name": "orm sqlite correlated exists",
        "dialects": ["sqlite"],
        "variants": [
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."email" AS "col2"
            FROM "auth_user"
            WHERE EXISTS (
                SELECT 1
                FROM "shop_order"
                WHERE
                    ("shop_order"."user_id" = "auth_user"."id")
                    AND ("shop_order"."status" = 'paid')
                    AND ("shop_order"."total_cents" > 0)
            )
            ORDER BY "auth_user"."id" ASC
            LIMIT 100;
            """,
            """
            SELECT
                "auth_user"."id" AS "col1",
                "auth_user"."email" AS "col2"
            FROM "auth_user"
            WHERE EXISTS (
                SELECT 1
                FROM "shop_order"
                WHERE
                    ("shop_order"."user_id" = "auth_user"."id")
                    AND ("shop_order"."status" = 'paid')
                    AND ("shop_order"."total_cents" > 999999)
            )
            ORDER BY "auth_user"."id"
            LIMIT 100;
            """,
        ],
    },
    {
        "name": "orm sqlite cte aggregation",
        "dialects": ["sqlite"],
        "variants": [
            """
            WITH "recent_orders" AS (
                SELECT
                    "shop_order"."id" AS "id",
                    "shop_order"."user_id" AS "user_id",
                    "shop_order"."total_cents" AS "total_cents",
                    "shop_order"."created_at" AS "created_at"
                FROM "shop_order"
                WHERE
                    ("shop_order"."created_at" >= '2024-01-01')
                    AND ("shop_order"."status" IN ('paid', 'shipped'))
            )
            SELECT
                "recent_orders"."user_id" AS "col1",
                COUNT(*) AS "col2",
                SUM("recent_orders"."total_cents") AS "col3"
            FROM "recent_orders"
            GROUP BY "recent_orders"."user_id"
            HAVING COUNT(*) >= 10
            ORDER BY SUM("recent_orders"."total_cents") DESC
            LIMIT 100;
            """,
            """
            WITH "recent_orders" AS (
                SELECT
                    "shop_order"."id" AS "id",
                    "shop_order"."user_id" AS "user_id",
                    "shop_order"."total_cents" AS "total_cents",
                    "shop_order"."created_at" AS "created_at"
                FROM "shop_order"
                WHERE
                    ("shop_order"."created_at" >= '2000-01-01')
                    AND ("shop_order"."status" IN ('paid', 'shipped'))
            )
            SELECT
                "recent_orders"."user_id" AS "col1",
                COUNT(*) AS "col2",
                SUM("recent_orders"."total_cents") AS "col3"
            FROM "recent_orders"
            GROUP BY "recent_orders"."user_id"
            HAVING COUNT(*) >= 999
            ORDER BY SUM("recent_orders"."total_cents") DESC
            LIMIT 100;
            """,
        ],
    },
]

ORACLE_ORM_CASES = [
    {
        "name": "orm oracle huge select with many columns and aliases",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                "AUTH_USER"."ID" AS "COL1",
                "AUTH_USER"."USERNAME" AS "COL2",
                "AUTH_USER"."EMAIL" AS "COL3",
                "AUTH_USER"."IS_ACTIVE" AS "COL4",
                "AUTH_USER"."DATE_JOINED" AS "COL5",
                "PROFILE_PROFILE"."ID" AS "COL6",
                "PROFILE_PROFILE"."USER_ID" AS "COL7",
                "PROFILE_PROFILE"."COMPANY" AS "COL8",
                "PROFILE_PROFILE"."JOB_TITLE" AS "COL9",
                "PROFILE_PROFILE"."TIMEZONE" AS "COL10"
            FROM "AUTH_USER"
            LEFT OUTER JOIN "PROFILE_PROFILE"
                ON ("PROFILE_PROFILE"."USER_ID" = "AUTH_USER"."ID")
            WHERE
                ("AUTH_USER"."IS_ACTIVE" = 1)
                AND ("AUTH_USER"."EMAIL" LIKE '%@example.com')
            ORDER BY "AUTH_USER"."ID" ASC
            OFFSET 100 ROWS FETCH FIRST 50 ROWS ONLY
            """,
            """
            SELECT
                "AUTH_USER"."ID" AS "COL1",
                "AUTH_USER"."USERNAME" AS "COL2",
                "AUTH_USER"."EMAIL" AS "COL3",
                "AUTH_USER"."IS_ACTIVE" AS "COL4",
                "AUTH_USER"."DATE_JOINED" AS "COL5",
                "PROFILE_PROFILE"."ID" AS "COL6",
                "PROFILE_PROFILE"."USER_ID" AS "COL7",
                "PROFILE_PROFILE"."COMPANY" AS "COL8",
                "PROFILE_PROFILE"."JOB_TITLE" AS "COL9",
                "PROFILE_PROFILE"."TIMEZONE" AS "COL10"
            FROM "AUTH_USER"
            LEFT OUTER JOIN "PROFILE_PROFILE"
                ON ("PROFILE_PROFILE"."USER_ID" = "AUTH_USER"."ID")
            WHERE
                ("AUTH_USER"."IS_ACTIVE" = 0)
                AND ("AUTH_USER"."EMAIL" LIKE '%@bob.com')
            ORDER BY "AUTH_USER"."ID"
            OFFSET 100 ROWS FETCH FIRST 50 ROWS ONLY
            """,
        ],
    },

    {
        "name": "orm oracle deep joins with many aliases",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                "SHOP_ORDER"."ID" AS "COL1",
                "SHOP_ORDER"."USER_ID" AS "COL2",
                "SHOP_ORDER"."STATUS" AS "COL3",
                "SHOP_ORDER"."TOTAL_CENTS" AS "COL4",
                "SHOP_ORDER"."CREATED_AT" AS "COL5",
                "SHOP_ORDERITEM"."ID" AS "COL6",
                "SHOP_ORDERITEM"."ORDER_ID" AS "COL7",
                "SHOP_ORDERITEM"."PRODUCT_ID" AS "COL8",
                "SHOP_ORDERITEM"."QUANTITY" AS "COL9",
                "CATALOG_PRODUCT"."ID" AS "COL10",
                "CATALOG_PRODUCT"."SKU" AS "COL11",
                "CATALOG_PRODUCT"."NAME" AS "COL12"
            FROM "SHOP_ORDER"
            INNER JOIN "SHOP_ORDERITEM"
                ON ("SHOP_ORDERITEM"."ORDER_ID" = "SHOP_ORDER"."ID")
            INNER JOIN "CATALOG_PRODUCT"
                ON ("CATALOG_PRODUCT"."ID" = "SHOP_ORDERITEM"."PRODUCT_ID")
            WHERE
                ("SHOP_ORDER"."USER_ID" = 123)
                AND ("SHOP_ORDER"."STATUS" IN ('paid', 'shipped', 'delivered'))
            ORDER BY "SHOP_ORDER"."CREATED_AT" DESC, "SHOP_ORDER"."ID" DESC
            FETCH FIRST 200 ROWS ONLY
            """,
            """
            SELECT
                "SHOP_ORDER"."ID" AS "COL1",
                "SHOP_ORDER"."USER_ID" AS "COL2",
                "SHOP_ORDER"."STATUS" AS "COL3",
                "SHOP_ORDER"."TOTAL_CENTS" AS "COL4",
                "SHOP_ORDER"."CREATED_AT" AS "COL5",
                "SHOP_ORDERITEM"."ID" AS "COL6",
                "SHOP_ORDERITEM"."ORDER_ID" AS "COL7",
                "SHOP_ORDERITEM"."PRODUCT_ID" AS "COL8",
                "SHOP_ORDERITEM"."QUANTITY" AS "COL9",
                "CATALOG_PRODUCT"."ID" AS "COL10",
                "CATALOG_PRODUCT"."SKU" AS "COL11",
                "CATALOG_PRODUCT"."NAME" AS "COL12"
            FROM "SHOP_ORDER"
            INNER JOIN "SHOP_ORDERITEM"
                ON ("SHOP_ORDERITEM"."ORDER_ID" = "SHOP_ORDER"."ID")
            INNER JOIN "CATALOG_PRODUCT"
                ON ("CATALOG_PRODUCT"."ID" = "SHOP_ORDERITEM"."PRODUCT_ID")
            WHERE
                ("SHOP_ORDER"."USER_ID" = 999999)
                AND ("SHOP_ORDER"."STATUS" IN ('paid', 'shipped', 'delivered'))
            ORDER BY "SHOP_ORDER"."CREATED_AT" DESC, "SHOP_ORDER"."ID" DESC
            FETCH FIRST 200 ROWS ONLY
            """,
        ],
    },

    {
        "name": "orm oracle correlated exists",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                "AUTH_USER"."ID" AS "COL1",
                "AUTH_USER"."EMAIL" AS "COL2"
            FROM "AUTH_USER"
            WHERE EXISTS (
                SELECT 1
                FROM "SHOP_ORDER"
                WHERE
                    ("SHOP_ORDER"."USER_ID" = "AUTH_USER"."ID")
                    AND ("SHOP_ORDER"."STATUS" = 'paid')
                    AND ("SHOP_ORDER"."TOTAL_CENTS" > 0)
            )
            ORDER BY "AUTH_USER"."ID" ASC
            FETCH FIRST 100 ROWS ONLY
            """,
            """
            SELECT
                "AUTH_USER"."ID" AS "COL1",
                "AUTH_USER"."EMAIL" AS "COL2"
            FROM "AUTH_USER"
            WHERE EXISTS (
                SELECT 1
                FROM "SHOP_ORDER"
                WHERE
                    ("SHOP_ORDER"."USER_ID" = "AUTH_USER"."ID")
                    AND ("SHOP_ORDER"."STATUS" = 'paid')
                    AND ("SHOP_ORDER"."TOTAL_CENTS" > 999999)
            )
            ORDER BY "AUTH_USER"."ID"
            FETCH FIRST 100 ROWS ONLY
            """,
        ],
    },

    {
        "name": "orm oracle cte aggregation",
        "dialects": ["oracle"],
        "variants": [
            """
            WITH "RECENT_ORDERS" AS (
                SELECT
                    "SHOP_ORDER"."ID" AS "ID",
                    "SHOP_ORDER"."USER_ID" AS "USER_ID",
                    "SHOP_ORDER"."TOTAL_CENTS" AS "TOTAL_CENTS",
                    "SHOP_ORDER"."CREATED_AT" AS "CREATED_AT"
                FROM "SHOP_ORDER"
                WHERE
                    ("SHOP_ORDER"."CREATED_AT" >= TO_DATE('2024-01-01', 'YYYY-MM-DD'))
                    AND ("SHOP_ORDER"."STATUS" IN ('paid', 'shipped'))
            )
            SELECT
                "RECENT_ORDERS"."USER_ID" AS "COL1",
                COUNT(*) AS "COL2",
                SUM("RECENT_ORDERS"."TOTAL_CENTS") AS "COL3"
            FROM "RECENT_ORDERS"
            GROUP BY "RECENT_ORDERS"."USER_ID"
            HAVING COUNT(*) >= 10
            ORDER BY SUM("RECENT_ORDERS"."TOTAL_CENTS") DESC
            FETCH FIRST 100 ROWS ONLY
            """,
            """
            WITH "RECENT_ORDERS" AS (
                SELECT
                    "SHOP_ORDER"."ID" AS "ID",
                    "SHOP_ORDER"."USER_ID" AS "USER_ID",
                    "SHOP_ORDER"."TOTAL_CENTS" AS "TOTAL_CENTS",
                    "SHOP_ORDER"."CREATED_AT" AS "CREATED_AT"
                FROM "SHOP_ORDER"
                WHERE
                    ("SHOP_ORDER"."CREATED_AT" >= TO_DATE('2000-01-01', 'YYYY-MM-DD'))
                    AND ("SHOP_ORDER"."STATUS" IN ('paid', 'shipped'))
            )
            SELECT
                "RECENT_ORDERS"."USER_ID" AS "COL1",
                COUNT(*) AS "COL2",
                SUM("RECENT_ORDERS"."TOTAL_CENTS") AS "COL3"
            FROM "RECENT_ORDERS"
            GROUP BY "RECENT_ORDERS"."USER_ID"
            HAVING COUNT(*) >= 999
            ORDER BY SUM("RECENT_ORDERS"."TOTAL_CENTS") DESC
            FETCH FIRST 100 ROWS ONLY
            """,
        ],
    },

    {
        "name": "orm oracle case when",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                CASE
                    WHEN "AUTH_USER"."IS_ACTIVE" = 1 THEN 'ACTIVE'
                    ELSE 'INACTIVE'
                END AS "COL1"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" = 123
            """,
            """
            SELECT
                CASE
                    WHEN "AUTH_USER"."IS_ACTIVE" = 1 THEN 'ACTIVE'
                    ELSE 'INACTIVE'
                END AS "COL1"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" = 999
            """,
        ],
    },

    {
        "name": "orm oracle rownum pagination legacy",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT * FROM (
                SELECT
                    "AUTH_USER"."ID" AS "COL1",
                    "AUTH_USER"."EMAIL" AS "COL2"
                FROM "AUTH_USER"
                WHERE ("AUTH_USER"."IS_ACTIVE" = 1)
                ORDER BY "AUTH_USER"."ID" ASC
            ) WHERE ROWNUM <= 100
            """,
            """
            SELECT * FROM (
                SELECT
                    "AUTH_USER"."ID" AS "COL1",
                    "AUTH_USER"."EMAIL" AS "COL2"
                FROM "AUTH_USER"
                WHERE ("AUTH_USER"."IS_ACTIVE" = 0)
                ORDER BY "AUTH_USER"."ID" ASC
            ) WHERE ROWNUM <= 100
            """,
        ],
    },

    {
        "name": "orm oracle sysdate usage",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                "SHOP_ORDER"."ID",
                "SHOP_ORDER"."CREATED_AT"
            FROM "SHOP_ORDER"
            WHERE "SHOP_ORDER"."CREATED_AT" >= SYSDATE - 30
            ORDER BY "SHOP_ORDER"."CREATED_AT" DESC
            """,
            """
            SELECT
                "SHOP_ORDER"."ID",
                "SHOP_ORDER"."CREATED_AT"
            FROM "SHOP_ORDER"
            WHERE "SHOP_ORDER"."CREATED_AT" >= SYSDATE - 365
            ORDER BY "SHOP_ORDER"."CREATED_AT" DESC
            """,
        ],
    },

    {
        "name": "orm oracle cast and functions",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT
                CAST("AUTH_USER"."ID" AS NUMBER) AS "COL1",
                LOWER("AUTH_USER"."EMAIL") AS "COL2",
                COALESCE("AUTH_USER"."EMAIL", 'none') AS "COL3"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" = 123
            """,
            """
            SELECT
                CAST("AUTH_USER"."ID" AS NUMBER) AS "COL1",
                LOWER("AUTH_USER"."EMAIL") AS "COL2",
                COALESCE("AUTH_USER"."EMAIL", 'none') AS "COL3"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" = 999
            """,
        ],
    },

    {
        "name": "orm oracle in list huge",
        "dialects": ["oracle"],
        "variants": [
            """
            SELECT "AUTH_USER"."ID", "AUTH_USER"."EMAIL"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" IN (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20)
            ORDER BY "AUTH_USER"."ID" ASC
            """,
            """
            SELECT "AUTH_USER"."ID", "AUTH_USER"."EMAIL"
            FROM "AUTH_USER"
            WHERE "AUTH_USER"."ID" IN (101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120)
            ORDER BY "AUTH_USER"."ID"
            """,
        ],
    },

    {
        "name": "orm oracle update",
        "dialects": ["oracle"],
        "variants": [
            """
            UPDATE "PROFILE_PROFILE"
            SET "TIMEZONE" = 'Europe/Paris', "UPDATED_AT" = SYSTIMESTAMP
            WHERE "PROFILE_PROFILE"."USER_ID" = 123
            """,
            """
            UPDATE "PROFILE_PROFILE"
            SET "TIMEZONE" = 'America/New_York', "UPDATED_AT" = SYSTIMESTAMP
            WHERE "PROFILE_PROFILE"."USER_ID" = 999
            """,
        ],
    },
]

ORM_CASES = ORM_CASES + ORACLE_ORM_CASES


CASES = CASES + HARD_CASES + ORM_CASES


@pytest.mark.parametrize("dialect", DIALECTS, ids=lambda d: d)
@pytest.mark.parametrize("case", CASES, ids=lambda c: _slug(c["name"]))
def test_sqlfp_query_normalization(case, dialect):
    if dialect not in case["dialects"]:
        pytest.skip(
            f"Case '{case['name']}' not supported for dialect '{dialect}'"
        )

    sql_variants = case["variants"]

    results = [sqlfp.normalize(sql=s, dialect=dialect) for s in sql_variants]

    hashes = [r.hash for r in results]
    normalized = [r.normalized for r in results]

    assert len(set(hashes)) == 1, (
        f"Expected all SQL variants to produce the same fingerprint.\n\n"
        f"Case: {case['name']}\n"
        f"Dialect: {dialect}\n\n"
        "Variants:\n"
        + "\n".join(f"- {s!r}" for s in sql_variants)
        + "\n\nNormalized:\n"
        + "\n".join(f"- {n!r}" for n in normalized)
        + "\n\nHashes:\n"
        + "\n".join(f"- {h!r}" for h in hashes)
    )

    assert len(set(normalized)) == 1, (
        f"Expected all SQL variants to produce the same normalized SQL.\n\n"
        f"Case: {case['name']}\n"
        f"Dialect: {dialect}\n\n"
        "Normalized:\n" + "\n".join(f"- {n!r}" for n in normalized)
    )



def test_sqlfp_hashed_refs():
    ref_path = Path(__file__).parent / "hashes_refs.txt"

    content = "\n".join(
        line
        for line in ref_path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    refs = json.loads(content)
    cases = {}
    for case in CASES:
        cases[case["name"]] = case

    for c, case_name in enumerate(refs):
        expected_hash = refs[case_name]["hash"]
        sql = cases[case_name]["variants"][0]
        dialect = cases[case_name]["dialects"][0]
        res = sqlfp.normalize(sql=sql, dialect=dialect)
        current_hash = res.hash
        current_normalized = res.normalized
        expected_normalized = refs[case_name]["normalized"]
        if current_hash != expected_hash:
            print(f"## query {c} {sql}")
            print(f"## hash {c}\n    expected: {expected_hash}\n    current:  {current_hash}")
            print(f"## normalized\n    expected: {expected_normalized}\n     current: {current_normalized}")
        else:
            print(f"## query {c} OK")


def test_sqlfp_result_type():
    result = sqlfp.normalize("select 1")
    cls = type(result)
    assert cls.__name__ == "NormalizeResult"
    assert cls.__module__ == "sqlfp"


def test_sqlfp_version():
    assert isinstance(sqlfp.__version__, str)
    assert len(sqlfp.__version__) > 0
