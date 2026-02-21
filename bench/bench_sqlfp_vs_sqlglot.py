from __future__ import annotations

import argparse
import time
import logging
from statistics import mean

import sqlglot
from tests.test_sqlfp import CASES, ORM_CASES

DIALECTS_DEFAULT = ["postgres", "mysql", "sqlite", "oracle", "ansi", "mssql"]
logging.getLogger("sqlglot").setLevel(logging.ERROR)


DIALECT_TO_GLOT = {
    "postgres": "postgres",
    "postgresql": "postgres",
	"mysql": "mysql",
    "sqlite": "sqlite",
	"oracle": "oracle",
	"mssql": "tsql",
	"ansi": ""
}


def bench_sqlfp(dialect: str, queries: list[str], rounds: int) -> dict:
    import sqlfp

    times = []
    ok = 0
    total = 0

    for _ in range(rounds):
        start = time.perf_counter()

        ok = 0
        total = 0
        for q in queries:
            total += 1
            try:
                sqlfp.normalize(sql=q, dialect=dialect)
                ok += 1
            except Exception:
                pass

        times.append(time.perf_counter() - start)

    avg = mean(times)
    return {
        "engine": "sqlfp",
        "dialect": dialect,
        "queries": len(queries),
        "ok": ok,
        "total": total,
        "avg_s": avg,
        "qps": len(queries) / avg if avg > 0 else 0.0,
    }


def replace_literals(node):
    if isinstance(node, sqlglot.exp.Literal):
        return sqlglot.exp.Literal.string("?")
    return node


def bench_sqlglot(dialect: str, queries: list[str], rounds: int) -> dict:

    times = []
    ok = 0
    total = 0

    for _ in range(rounds):
        start = time.perf_counter()

        ok = 0
        total = 0
        for q in queries:
            total += 1
            try:
                expr = sqlglot.parse_one(q, read=dialect)
                expr = expr.transform(replace_literals)
                _ = expr.sql(dialect=dialect)
                ok += 1
            except Exception:
                pass

        times.append(time.perf_counter() - start)

    avg = mean(times)
    return {
        "engine": "sqlglot",
        "dialect": dialect,
        "queries": len(queries),
        "ok": ok,
        "total": total,
        "avg_s": avg,
        "qps": len(queries) / avg if avg > 0 else 0.0,
    }


def load_queries(dialect, orm=False) -> list[str]:
    res = []
    if orm:
        cases = ORM_CASES
    else:
        cases = CASES
    for case in cases:
        for sql in case["variants"]:
            if dialect in case["dialects"]:
                res.append(sql)
    return res


def print_result(result: dict) -> None:
    print(
        f"{result['engine']:7s} dialect={result['dialect']:9s} "
        f"ok={result['ok']:4d}/{result['total']:4d} "
        f"avg={result['avg_s']*1000:8.2f}ms "
        f"qps={result['qps']:10.1f}"
    )


def run_once_sqlfp(
    dialect: str, queries: list[str]
) -> tuple[int, int, list[str]]:
    import sqlfp

    ok = 0
    failed = []

    for q in queries:
        try:
            sqlfp.normalize(sql=q, dialect=dialect)
            ok += 1
        except Exception:
            failed.append(q)

    return ok, len(queries), failed


def run_once_sqlglot(
    dialect: str, queries: list[str]
) -> tuple[int, int, list[str]]:

    ok = 0
    failed = []

    for q in queries:
        try:
            expr = sqlglot.parse_one(q, read=dialect)
            _ = expr.sql(dialect=dialect, pretty=False)
            ok += 1
        except Exception:
            failed.append(q)

    return ok, len(queries), failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        choices=["sqlfp", "sqlglot", "both"],
        default="both",
        help="Which engine to benchmark.",
    )
    parser.add_argument(
        "--dialect",
        default="all",
        help="Dialect to use (postgres/mysql/sqlite) or 'all'.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="Number of rounds per dialect.",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--orm", action="store_true")

    args = parser.parse_args()

    dialects = DIALECTS_DEFAULT if args.dialect == "all" else [args.dialect]

    if args.check:
        for dialect in dialects:
            queries = load_queries(dialect=dialect, orm=args.orm)

            ok1, total1, fail1 = run_once_sqlfp(dialect, queries)
            glot_dialect = DIALECT_TO_GLOT[dialect]
            ok2, total2, fail2 = run_once_sqlglot(glot_dialect, queries)

            print(f"[{dialect}] sqlfp   ok={ok1}/{total1}")
            print(f"[{dialect}] sqlglot ok={ok2}/{total2}")

            if ok1 != ok2:
                only_sqlfp_fails = sorted(set(fail1) - set(fail2))
                only_sqlglot_fails = sorted(set(fail2) - set(fail1))

                print("\n--- Queries failing ONLY in sqlfp ---")
                for q in only_sqlfp_fails[:20]:
                    print(q)

                print("\n--- Queries failing ONLY in sqlglot ---")
                for q in only_sqlglot_fails[:20]:
                    print(q)

                raise SystemExit(
                    f"ERROR: different success rates for dialect={dialect}: "
                    f"sqlfp={ok1}/{total1} sqlglot={ok2}/{total2}"
                )

        return 0

    for dialect in dialects:
        queries = load_queries(dialect=dialect, orm=args.orm)
        print(f"queries count for dialect {dialect}: {len(queries)}")
        if args.engine in ("sqlfp", "both"):
            result = bench_sqlfp(dialect, queries, rounds=args.rounds)
            print_result(result=result)

        if args.engine in ("sqlglot", "both"):
            glot_dialect = DIALECT_TO_GLOT[dialect]
            result = bench_sqlglot(glot_dialect, queries, rounds=args.rounds)
            print_result(result=result)

        if args.engine == "both":
            print("-" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
