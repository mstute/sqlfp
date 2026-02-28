# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Stability guarantee:** the normalized form and its hash are stable within a
> major version. Any normalization change that affects existing fingerprints
> triggers a major version bump.

---

## [Unreleased]

---

## [0.1.3] - 2026-02-28

### Added
- `sqlfp.pyi` type stub with full annotations (`NormalizeResult`, `normalize`, `Dialect` literal)
- `py.typed` marker included in the wheel (PEP 561)
- mypy strict mode configuration in `pyproject.toml` & added in CI
- Python 3.9–3.13 matrix in CI
- Rust build cache in CI (`Swatinem/rust-cache`)

### Changed
- Project status promoted from alpha to beta
- Version is now read dynamically from `Cargo.toml` (`dynamic = ["version"]`)
- pytest constraint relaxed to `>=8,<10` for Python 3.9 compatibility
- black constraint relaxed to `>=25,<27` for Python 3.9 compatibility

### Fixed
- Default dialect in README API reference was incorrectly shown as `"postgres"` instead of `"generic"`

---

## [0.1.2] - 2026-02-22

### Added
- Pre-built wheels for Linux, macOS, and Windows

---

## [0.1.1] - 2026-02-21

### Added
- CI pipeline (GitHub Actions)

---

## [0.1.0] - 2026-02-21

### Added
- Initial release
- SQL normalization (joins, aliases, parentheses, function names, ORDER BY)
- Query fingerprinting via SHA-256
- Parameter extraction
- Support for PostgreSQL, MySQL/MariaDB, SQLite, ANSI, MSSQL, and Oracle dialects

---

[Unreleased]: https://github.com/mstute/sqlfp/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/mstute/sqlfp/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mstute/sqlfp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mstute/sqlfp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mstute/sqlfp/releases/tag/v0.1.0
