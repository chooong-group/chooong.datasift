# Contributing

Use a feature branch and pull request. Keep the public API and filter behavior
stable; describe contract changes before implementing them. Update the
[JSON filter reference](docs/contract.md), relevant guides and `CHANGELOG.md`
when behavior changes. Version bumps and publication require a release decision.

## Setup and checks

Install CPython 3.12, 3.13 or 3.14, uv and the Rust toolchain in `rust-toolchain.toml`.
`uv sync --frozen` builds the native extension and installs locked development
dependencies.

```bash
uv sync --frozen
uv run --frozen ruff check src tests tooling scripts release
uv run --frozen ruff format --check src tests tooling scripts release
uv run --frozen mypy --strict src scripts release tests/benchmarks
uv run --frozen pytest tests/ -m "not benchmark" --cov --cov-report=term-missing
uv run --frozen pytest tooling/tests/
cargo fmt --manifest-path datasift-core/Cargo.toml -- --check
cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path datasift-core/Cargo.toml --locked
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check dist/*
git diff --check
```

## Tests and review

Tests are grouped by behavior. Shared deterministic generators live in
`tests/fixtures/`; `tests/conftest.py` supplies common temporary inputs.
Release tooling tests run separately under `tooling/tests/` without network access.
Large workloads are opt-in: see [Benchmarks](tests/benchmarks/README.md).

The [core README](datasift-core/README.md#test-structure) describes the Rust test
suites. Run them with Cargo; repository-level pytest tests cover the Python API and CLI.

Use synthetic workbooks and the existing ZIP/XML fixtures. Never commit personal
data, credentials or generated NDJSON. Cover meaningful failures, including
preserving existing CLI output after a failed scan. Keep Python annotations
complete and imports absolute; do not weaken lint/type rules to hide failures.

Describe behavior, checks and remaining gaps in the PR. Native artifact tests
must use installed wheels/sdist on the matching platform. Release procedures are maintained in
[RELEASING](.github/RELEASING.md).

Contributions use the repository's [Apache-2.0 license](LICENSE).
