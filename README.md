# SQLFP

Normalize and fingerprint SQL queries in Python — typically **16–20× faster than sqlglot** on realistic workloads.

![PyPI](https://img.shields.io/pypi/v/sqlfp)
![Python](https://img.shields.io/pypi/pyversions/sqlfp)
![License](https://img.shields.io/pypi/l/sqlfp)

**SQLFP** is a fast Python library that normalizes SQL queries and
generates stable fingerprints.

It parses a SQL string, canonicalizes it (removing literals and
normalizing structure), and returns:

-   a normalized SQL string
-   a stable hash suitable for grouping queries
-   extracted parameters

Ideal for observability, monitoring, and performance tooling.

SQLFP is not a general-purpose SQL transformation library.

---

## Quick Example

``` python
import sqlfp

result = sqlfp.normalize(
    sql="SELECT * FROM users WHERE id = 123",
    dialect="mysql",
    placeholder="<val>",
)

print(result.hash)
# 3886cc37e387f27530d0506c3ba2305bb8d75dbb17ce68036e92567b1791c639

print(result.normalized)
# SELECT * FROM users WHERE id = <val>

print(result.original)
# SELECT * FROM users WHERE id = 123

print(result.params)
# ['123']
```

---

## Installation

``` bash
pip install sqlfp
```

Prebuilt wheels are provided.\
No Rust toolchain is required.

**Requirements:** Python ≥ 3.9

---

## Why SQLFP?

SQLFP is implemented in **Rust** (via `sqlparser-rs` + PyO3) and exposed
as a minimal Python extension.

Compared to pure-Python SQL parsers, it focuses specifically on
**deterministic fingerprinting** and performance.

Typical characteristics:

-   **16×–20× faster than sqlglot**
-   Deterministic normalization
-   Multi-dialect support
-   Designed for query fingerprinting workloads

SQLFP focuses on one problem: producing stable query fingerprints as fast and predictably as possible.

---

## Performance

Benchmarks were executed in **release mode** over **100 rounds** using realistic queries.

SQLFP is typically **16×–20× faster than sqlglot** depending on dialect and query complexity.

| Workload | sqlfp | sqlglot |
|---|---|---|
| PostgreSQL queries | baseline | ~16× slower |
| MySQL queries | baseline | ~20× slower |
| Oracle queries | baseline | ~21× slower |
| ORM-style long queries | baseline | ~20× slower |

Benchmark scripts are available in `bench/`.
Results may vary depending on workload and hardware.


---

## API

### `normalize()`

``` python
normalize(
    sql: str,
    dialect: str = "postgres",
    placeholder: str = "?"
) -> NormalizeResult
```

Returns a `NormalizeResult` object:

-   `hash: str`
-   `normalized: str`
-   `original: str`
-   `params: list[str]`

---

## Supported Dialects

-   PostgreSQL
-   MySQL
-   SQLite
-   Oracle
-   MSSQL
-   ANSI

---

## What SQLFP Normalizes

SQLFP performs:

-   Literal replacement (`123`, `'abc'`, etc. → placeholder)
-   Whitespace normalization
-   Case normalization
-   Removal of redundant parentheses
-   Canonical formatting (stable rendering)
-   Stable hashing (SHA-256)

Example:

``` sql
SELECT id FROM users WHERE id = 42;
SELECT id FROM users WHERE id = 999;
```

Both normalize to:

``` sql
SELECT id FROM users WHERE id = ?
```

They therefore share the same fingerprint.

---

## What SQLFP Does NOT Do

-   Does not rewrite queries semantically
-   Does not optimize SQL
-   Does not execute queries
-   Does not guarantee cross-dialect equivalence

SQLFP focuses strictly on structural fingerprinting.

---

## Use Cases

-   Database performance monitoring
-   Query aggregation dashboards
-   Slow query analysis
-   Log deduplication
-   Observability pipelines

---

## Architecture

SQLFP uses a Rust core for performance and deterministic parsing,
exposed through a minimal Python API.

Users do **not** need Rust installed.

Technologies used:

-   Rust core
-   `sqlparser-rs`
-   PyO3 bindings
-   Built with maturin

---

## Project Status

SQLFP is currently in **alpha**.

APIs may evolve before version 1.0.

---

## Stability Guarantees

-   Fingerprints are stable within a given major version.
-   Any normalization change will trigger a major version bump.

---

## Version

``` python
import sqlfp
print(sqlfp.__version__)
```

---

## Contributing

Issues and pull requests are welcome.

Please:

-   open an issue before large changes
-   run tests before submitting
-   keep API stability in mind

---

## Security

Please report vulnerabilities to:

opensource@iwod.com

Do not disclose vulnerabilities publicly before a fix is available.

---

## License

MIT

---

## Development

Development dependencies are pinned in `requirements.lock`
to ensure reproducible local environments.

They are **not required** to use sqlfp as a library.
