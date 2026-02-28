# Contributing

Issues and pull requests are welcome.

## Guidelines

- Open an issue before large changes to align on approach
- Keep API stability in mind — fingerprint changes require a major version bump
- Run tests before submitting

## Requirements

- [Rust](https://rustup.rs/) (stable toolchain)
- Python ≥ 3.9
- [Maturin](https://github.com/PyO3/maturin)

## Setup

```bash
git clone https://github.com/mstute/sqlfp
cd sqlfp
pip install -r requirements-dev.txt
```

## Build

Compile the Rust extension and install it in the current environment:

```bash
maturin develop --release
```

## Tests

```bash
pytest
```

## Updating reference hashes

`tests/hashes_refs.txt` contains the reference fingerprints used by
`test_sqlfp_hashed_refs`. If a normalization change intentionally affects
existing hashes, update the file manually — `test_sqlfp_hashed_refs` prints
the expected vs. current values for each differing entry.

> Any change to reference hashes must be accompanied by a major version bump.
