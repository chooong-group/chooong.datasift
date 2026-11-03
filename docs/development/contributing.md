# Contributing

Use a feature branch and one focused pull request. Read the repository's current
instructions, inspect affected consumers and preserve public contracts. Use
synthetic files; do not commit personal workbooks, credentials or generated output.

## Setup

Install CPython 3.12, 3.13 or 3.14, uv, Rust 1.95.0 and a native linker.
The toolchain is pinned in `rust-toolchain.toml`; Python and Cargo dependencies
are locked. From the repository root:

```bash
uv sync --frozen
```

## Checks

```bash
uv run --frozen ruff check src tests
uv run --frozen ruff format --check src tests
uv run --frozen mypy --strict src tests/benchmarks
uv run --frozen pytest tests/ -m "not benchmark" --cov --cov-report=term-missing
cargo fmt --manifest-path datasift-core/Cargo.toml -- --check
cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path datasift-core/Cargo.toml --locked
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check --strict dist/*
git diff --check
```

Python tests are grouped by behavior; deterministic ZIP/XML/CSV fixtures live in
`tests/fixtures/`. Rust unit/pipeline suites are described in the
[core README](https://github.com/chooong-group/chooong.datasift/blob/main/datasift-core/README.md#test-structure).
Cover real failures and replay, including preserving prior outputs on scan failure.
Keep annotations complete and imports absolute; do not weaken lint/type rules.

## Documentation

Build the documentation with `uv run --frozen mkdocs build --strict`.
Check examples against the public API and CLI when changing them. Package behavior
is covered by the Python and Rust suites; benchmark cases measure real scans and
exports and run separately with `pytest -m benchmark`.

Review docs, examples, metadata and user-relevant [changelog](https://github.com/chooong-group/chooong.datasift/blob/main/CHANGELOG.md)
changes together. The runtime/Python model is authoritative; never change the
engine silently to make prose pass. [Release procedures](https://github.com/chooong-group/chooong.datasift/blob/main/.github/RELEASING.md)
describe the tag-triggered publisher. Contributions use [Apache-2.0](https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE).

The documentation uses Material for MkDocs for search, responsive navigation and
system/light/dark appearance. `docs/stylesheets/chooong.css` adapts the palettes
from Chooong's `src/styles.css`; `docs/assets/brand/` contains the original Chooong
logos and favicon. Keep logo files unchanged and use the bright logo in light
appearance and the dark logo in dark appearance. Inter and Roboto Mono are loaded
through the theme's Google Fonts integration; the browser uses system fallbacks
when that service is unavailable. The documentation needs no application frontend.
