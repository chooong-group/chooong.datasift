# Contributing

Use a feature branch and a pull request. Keep the public API and the versioned
mask semantics stable; explain any proposed contract change before implementing it.
The current package is unreleased. Do not bump versions or publish artifacts as
part of an ordinary contribution.

## Environment

Install CPython 3.13 or 3.14, uv, and the toolchain from `rust-toolchain.toml`.
`uv sync --frozen` installs the locked development dependencies and builds the
native extension. A compatible installed wheel does not require Rust.

Run the development checks listed in [README](README.md). CI additionally builds
native wheels on five standard GitHub-hosted platforms and installs every wheel
under both supported Python versions. The sdist is separately built and installed.
No cross-build substitutes for a native runtime test. Private-repository jobs are
skipped to avoid implicit billing; a skipped job is not validation evidence.

## Changes and tests

Python imports are absolute. Keep annotations complete and run Ruff and mypy;
do not weaken checks to hide failures. Reuse the real ZIP/XML fixtures in `tests/`
for data-path changes. Include a meaningful negative case and prove that failed
CLI scans preserve the previous output. Test replay and batch-size independence
when relevant. Tests for release tooling may use clearly synthetic receipts;
these are not evidence that another operating system was actually tested.

Update `CHANGELOG.md` under Unreleased and adjust README or the
[canonical contract](docs/contract.md) when behavior changes. Documentation is
built with MkDocs in strict mode. Use synthetic workbooks only: no personal data,
credentials, local `.data/` contents, or generated NDJSON in commits or artifacts.

Maintainer-specific work rules are kept locally in `.data/AGENTS.md`. CI has no
write permissions, persistent registry credentials, or access to self-hosted
runners. Do not introduce privileged fork triggers or shared publishing secrets.

## Pull requests and reviews

Describe the problem, behavior, exact checks and their exit status. Separate local
validation from CI and independent review. List untested platforms as release
blockers. Follow the pull-request template. Only a separately approved release
activation may enable publishing or Pages deployment; see [Releases](docs/releases.md).

Contributions are made under the repository's Apache-2.0 license. Ensure you have
the rights to contribute code and preserve applicable third-party notices.
