# Contributing

Use a feature branch and pull request. Keep the public API and filter behavior
stable; describe contract changes before implementing them. Update the
[JSON filter reference](docs/contract.md), relevant guides and `CHANGELOG.md`
when behavior changes. Version bumps and publication require a release decision.

## Setup and checks

Install CPython 3.13 or 3.14, uv and the Rust toolchain in `rust-toolchain.toml`.
`uv sync --frozen` builds the native extension and installs locked development
dependencies.

```bash
uv sync --frozen
uv run --frozen ruff check src tests scripts examples
uv run --frozen ruff format --check src tests scripts examples
uv run --frozen mypy src
uv run --frozen mypy --strict scripts/artifacts.py scripts/verify_publish.py scripts/bench.py examples/create_sample.py
uv run --frozen pytest --cov --cov-report=term-missing
cargo fmt --manifest-path datasift-core/Cargo.toml -- --check
cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path datasift-core/Cargo.toml --locked
uv run --frozen mkdocs build --strict
uv build
uv run --frozen twine check dist/*
git diff --check
```

The synthetic benchmark is `uv run --frozen python scripts/bench.py`; it defaults
to 2,000,000 rows across multiple worksheets.

## Tests and review

Use synthetic workbooks and the existing ZIP/XML fixtures. Never commit personal
data, credentials or generated NDJSON. Cover meaningful failures, including
preserving existing CLI output after a failed scan. Keep Python annotations
complete and imports absolute; do not weaken lint/type rules to hide failures.

Describe behavior, checks and remaining gaps in the PR. Native artifact tests
must use installed wheels/sdist on the matching platform; synthetic gate receipts
do not establish platform support. Release procedures are maintained in
[RELEASING](.github/RELEASING.md).

Contributions use the repository's [Apache-2.0 license](LICENSE).
