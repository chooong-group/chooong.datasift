# datasift-core

The Rust engine behind [chooong.datasift](../README.md). It reads XLSX/XLSM and
CSV, discovers tables, validates and converts values, filters rows and writes
NDJSON or Parquet. PyO3 exposes it as `chooong.datasift.rust`.

Applications should use the typed [Python API](../docs/api/python.md). The core
module is an internal interface shipped with `chooong.datasift`, built from the
repository's root `pyproject.toml`.

## Internal boundary

Applications use the stable [Python API](../docs/api/python.md). Native PyO3
functions are implementation interfaces, not a standalone supported Rust/Python
consumer API. [Architecture](../docs/development/architecture.md) maps the modules
and worker ownership. The root Maturin configuration controls packaging.

## Development

Install Rust 1.95.0 (pinned in [`rust-toolchain.toml`](../rust-toolchain.toml)),
CPython 3.12, 3.13 or 3.14, uv and a native linker. Run from the repository root:

<!-- check: syntax -->

```bash
uv sync --frozen
cargo test --manifest-path datasift-core/Cargo.toml --locked
cargo fmt --manifest-path datasift-core/Cargo.toml -- --check
cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings
uv run --frozen pytest
```

Run a focused Rust suite by module name:

<!-- check: syntax -->

```bash
cargo test --manifest-path datasift-core/Cargo.toml --locked encoding::tests
cargo test --manifest-path datasift-core/Cargo.toml --locked output::integration_tests
```

The complete checks and package build commands are in [Contributing](../CONTRIBUTING.md).

## Test structure

| Location | Behavior |
| --- | --- |
| [`tests/unit/encoding.rs`](tests/unit/encoding.rs) | Incremental transcoding, BOMs, malformed sequences and I/O failures |
| [`tests/unit/discovery.rs`](tests/unit/discovery.rs) | Independent regions, multiline/repeated headers and ambiguous layouts |
| [`tests/unit/filter.rs`](tests/unit/filter.rs) | Configuration validation, column bindings and predicate evaluation |
| [`tests/unit/rules.rs`](tests/unit/rules.rs) | Exact conversions, strict types, currencies and header normalization |
| [`tests/unit/value.rs`](tests/unit/value.rs) | Exact JSON values, numeric lexemes and temporal precision |
| [`tests/unit/input.rs`](tests/unit/input.rs) | Input ordering, CSV records, bounded batches, cancellation and file errors |
| [`tests/unit/xlsx.rs`](tests/unit/xlsx.rs) | Cell references, XML entities and cached cell values |
| [`tests/unit/output.rs`](tests/unit/output.rs) | Typed Parquet serialization |
| [`tests/unit/recovery.rs`](tests/unit/recovery.rs) | Verified recovery under concurrent file/path changes |
| [`tests/pipeline/export.rs`](tests/pipeline/export.rs) | Real CSV/OOXML exports, output preservation and exclusive writers |

Rust tests are included in their owning modules, so private implementation stays
private. Pipeline tests use real files and serializers. Shared fixtures under
[`tests/support/`](tests/support/) create isolated temporary directories and OOXML
archives; they need no external data or services. The repository-level
[`tests/`](../tests/) covers the public Python API and CLI.

## Limits

The core does not calculate Excel formulas; it reads cached results. It supports
XLSX/XLSM and CSV, with bounded row streaming; workbook metadata and shared strings
are retained in memory. See [Limits & Errors](../docs/reference/limits.md) for format and
resource limits.

Licensed under [Apache-2.0](../LICENSE).
