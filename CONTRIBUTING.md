# Contributing

Work on a feature branch and submit one focused pull request. Preserve public
contracts and use synthetic inputs; never attach personal workbooks or secrets.

Install CPython 3.12–3.14, uv, Rust 1.95.0 and a native linker, then run:

<!-- check: syntax -->

```bash
uv sync --frozen
```

The canonical [contributor guide](docs/development/contributing.md) lists exact
lint, type, test, documentation and build commands. Run those checks before
submitting changes. It also explains runnable documentation examples and local
verification against installed wheels.

Update affected guides/API references with behavior changes. Keep
[CHANGELOG.md](CHANGELOG.md) limited to features, breaking changes, relevant
bugfixes and security changes. Report observed test failures and validation gaps
in the PR, not in public usage guides.

See [architecture](docs/development/architecture.md),
[Rust tests](datasift-core/README.md#test-structure),
[benchmarks](docs/development/benchmarks.md) and
[release procedures](.github/RELEASING.md). Version changes, tags and publication
require a separate explicit release decision. Contributions use [Apache-2.0](LICENSE).
