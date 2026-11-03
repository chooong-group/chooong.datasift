# Releasing

## Validate

CI runs Ruff, mypy, Python and Rust tests, MkDocs and Maturin builds.
The five native wheel targets are Linux x86_64/ARM64, macOS x86_64/ARM64 and
Windows x86_64. Each ABI3 wheel is installed with CPython 3.12, 3.13 and 3.14 on its native
runner. Import, a CSV scan through the public API and CLI startup are smoke-tested.
The sdist is separately built and installed on Linux with CPython 3.13 and receives
the same smoke checks. Functional tests run once in the quality job. CI uploads the wheels and sdist as ordinary Actions artifacts.

Builds use the Maturin version from `pyproject.toml`, the pinned Rust toolchain and
locked Cargo dependencies. Linux builds use Zig 0.15.2 with the manylinux_2_28
baseline; macOS and Windows use their native linkers.

## Publish

Update the version in `pyproject.toml`, `datasift-core/Cargo.toml` and both lockfiles
and move the relevant `Unreleased` notes into a versioned changelog section.
Merge the reviewed changes before tagging. Never overwrite an existing release tag.
Pushing a `vX.Y.Z` tag starts `release.yml`, which verifies that the tag matches the
Python and Rust versions and runs the same CI workflow. After all checks and native
builds succeed, the official PyPI publishing action publishes those distributions
using OIDC. A GitHub Release with the changelog notes and distributions follows only
after successful PyPI publication. Failed checks or uploads stop subsequent jobs;
investigate a partial upload before attempting recovery.

Configure the PyPI Trusted Publisher for `chooong.datasift` with owner
`chooong-group`, repository `chooong.datasift`, workflow `release.yml` and environment
`pypi`. The GitHub `pypi` environment controls publication approval and allowed tags.
No PyPI API token or manual commit/SHA input is needed. External Actions are pinned
to full commit SHAs to comply with the organization policy.

## Third-party notices

`THIRD_PARTY_NOTICES.txt` contains the applicable upstream license, copyright and
NOTICE texts for linked Rust dependencies. `licenses/rust-std.html` retains the
Rust standard-library third-party notices. Both are packaged with `LICENSE` in
wheels and sdists. Review these texts when updating native dependencies or the Rust
toolchain; Python runtime dependencies and build tools are distributed separately.

## Other workflows

Benchmarks run manually; see [Benchmarks](../docs/development/benchmarks.md).
Documentation deployment remains a separate manual workflow controlled by
`PAGES_DEPLOY_ENABLED` and the `github-pages` environment.
