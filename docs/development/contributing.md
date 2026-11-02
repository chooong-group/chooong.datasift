# Contributing

Use a feature branch and one focused pull request. Read the repository's current
instructions, inspect affected consumers and preserve public contracts. Use
synthetic files; do not commit personal workbooks, credentials or generated output.

## Setup

Install CPython 3.12, 3.13 or 3.14, uv, Rust 1.95.0 and a native linker.
The toolchain is pinned in `rust-toolchain.toml`; Python and Cargo dependencies
are locked. From the repository root:

<!-- check: syntax -->

```bash
uv sync --frozen
```

## Checks

<!-- check: syntax -->

```bash
uv run --frozen ruff check src tests tooling scripts release
uv run --frozen ruff format --check src tests tooling scripts release
uv run --frozen mypy --strict src scripts release tests/benchmarks
uv run --frozen pytest tests/ -m "not benchmark" --cov --cov-report=term-missing
uv run --frozen pytest tooling/tests/
cargo fmt --manifest-path datasift-core/Cargo.toml -- --check
cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path datasift-core/Cargo.toml --locked
uv run --frozen python scripts/docs.py
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check --strict dist/*
git diff --check
```

Python tests are grouped by behavior; deterministic ZIP/XML/CSV fixtures live in
`tests/fixtures/`. Tooling tests under `tooling/tests/` run separately without live
external APIs. Rust unit/pipeline suites are described in the
[core README](https://github.com/chooong-group/chooong.datasift/blob/main/datasift-core/README.md#test-structure).
Cover real failures and replay, including preserving prior outputs on scan failure.
Keep annotations complete and imports absolute; do not weaken lint/type rules.

## Documentation

`scripts/docs.py` inventories versioned and new non-ignored Markdown, runs
PyMarkdown, checks relative file links and Markdown anchors, verifies navigation
coverage, renders the PyPI README with its GFM renderer and executes marked
examples in temporary directories. Python snippets
on one page share a process; CSV/JSON file blocks create synthetic inputs.
Workbook blocks represent sheet `Data`, with empty fields as blank cells and
JSON numeric/boolean scalars as native cells. Shell blocks without a syntax-only
marker must invoke the real DataSift CLI. JSON masks are structurally and natively
validated; schemas remain generated from the public models.

Installation, build and owner-only release shell blocks carry `check: syntax`:
these are parsed, not executed by the example runner. Their real commands are
covered by local development/build checks or isolated release-tooling tests;
examples never publish or deploy. `--python PATH` runs examples against an installed
candidate wheel. `--external` checks external HTTP links with bounded timeouts;
private project links resolve to checked repository paths instead of requiring
anonymous public access. An external-link failure fails that invocation and does
not disable offline checks. CI runs the offline checks reproducibly.

Review docs, examples, metadata and user-relevant [changelog](https://github.com/chooong-group/chooong.datasift/blob/main/CHANGELOG.md)
changes together. The runtime/Python model is authoritative; never change the
engine silently to make prose pass. [Release procedures](https://github.com/chooong-group/chooong.datasift/blob/main/.github/RELEASING.md)
require explicit publication approval. Contributions use [Apache-2.0](https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE).
