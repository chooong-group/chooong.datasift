# Contributing

The repository's contribution policy is maintained in `CONTRIBUTING.md` at its
root. Use a feature branch and a pull request, keep public contracts stable, and
use synthetic XLSX fixtures. Never add local `.data/` workbooks or credentials.

Development setup:

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
```

The core runtime is unchanged by the open-source preparation. Native artifact
tests run in separate environments with `-I`, removing local source imports.
Each artifact has checksum-bound test evidence for both supported Python versions.
Static review and synthetic release-gate tests do not establish platform support.

The documentation uses MkDocs' bundled Read the Docs theme, without extra hosted
services or plugins. Run the strict build before submitting documentation changes.
Publishing and Pages deployment remain hard-disabled until separate owner approval
and external configuration; see [Releases](releases.md).
