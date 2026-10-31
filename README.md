# chooong.datasift

[![CI](https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml/badge.svg)](https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml)
![PyPI: not published](https://img.shields.io/badge/PyPI-not%20published-lightgrey)
![Python 3.13 / 3.14](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue)
![Wheel matrix: unverified](https://img.shields.io/badge/wheel%20matrix-unverified-lightgrey)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Stream XLSX/XLSM worksheets through Rust predicates. Python receives only matching
values as immutable, typed rows. No Pandas dependency or full worksheet
materialization; no formula calculation or Excel output.

**Unreleased, version 0.1.0.** CPython 3.13/3.14. The release matrix targets Linux
x86_64/aarch64, Windows x86_64, and macOS x86_64/arm64. These are release targets,
not a claim that all platforms have passed: see the [validation matrix](docs/readiness.md).
The PyPI and wheel badges deliberately do not claim a published release.

## Install

From a checkout, with Python and Rust 1.95.0 installed:

```bash
python -m pip install .
# or, in an existing environment:
uv pip install .
```

Compatible wheels need no compiler. Registry installation with
`pip install chooong.datasift` / `uv pip install chooong.datasift` becomes available
only after the first approved PyPI release. No release has been published by this preparation.

## Quickstart

Create a small synthetic workbook; the command refuses to overwrite a file:

```bash
python examples/create_sample.py sample.xlsx
```

```python
from chooong.datasift import FilterMask, Operator, ScalarCondition, iter_matching_rows

mask = FilterMask(
    sheet=None,
    where=ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
)
for row in iter_matching_rows("sample.xlsx", mask):
    print(dict(row))  # {'Country': 'DE'}, twice
```

The CLI accepts a JSON mask:

```json
{"sheet": null, "where": {"column": "Country", "op": "eq", "value": "DE"}}
```

```bash
chooong-datasift sample.xlsx examples/quickstart-filter.json --output matches.ndjson
# equivalent entry point:
python -m chooong.datasift sample.xlsx examples/quickstart-filter.json
```

`sheet: null` scans all worksheets. Headers are found from the mask; repeated
complete schemas can describe separate tables beside or below each other.
Only columns referenced by the mask are returned. `--output` replaces its target
atomically after the whole scan succeeds. Use the batch iterator as a context
manager when stopping early.

## API, architecture and limits

The supported imports are the exports of `chooong.datasift`, including `FilterMask`,
filter models, `TableSource`, `ColumnBinding`, `Row`, `iter_matching_rows` and
`iter_matching_batches`. The Python adapter validates masks with Pydantic; the
native engine separates predicate logic, XLSX I/O and PyO3. No service or database
is required. Runtime configuration is the mask and explicit function/CLI arguments.

Headers containing line breaks within one cell are supported. Headers spread over
multiple physical rows are **not** reconstructed. Arbitrary layouts and comments
are not guessed; use explicit source bindings for ambiguity. No XLS/XLSB,
encryption, date/style interpretation, or formula evaluation. Shared strings are
held in memory. Details: [public contract](docs/contract.md),
[limits](docs/limits.md), [errors and resources](docs/errors.md).

## Develop

```bash
uv sync --frozen
uv run --frozen ruff check src tests scripts examples
uv run --frozen ruff format --check src tests scripts examples
uv run --frozen mypy src
uv run --frozen mypy --strict scripts/artifacts.py scripts/verify_publish.py scripts/bench.py examples/create_sample.py
uv run --frozen pytest --cov --cov-report=term-missing
cargo fmt --manifest-path native/Cargo.toml -- --check
cargo clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path native/Cargo.toml --locked
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check dist/*
```

The benchmark defaults to 2,000,000 synthetic rows across multiple worksheets:

```bash
uv run --frozen python scripts/bench.py
```

Local workbooks are stored in `examples/` and excluded from Git and distribution archives.
`examples/filter_2000000.json` is retained for the corresponding local workbook.

[Documentation](docs/index.md) · [Contributing](CONTRIBUTING.md) ·
[Releases](docs/releases.md) · [Changelog](CHANGELOG.md) ·
[Security](SECURITY.md) · [License](LICENSE)
