# Releasing

Version `0.1.0` remains unreleased. Publishing and Pages deployment are hard-disabled.
The project version in `pyproject.toml` is authoritative; Cargo and both lockfiles
must agree. Preparation supports canonical final PEP 440 versions (`X.Y.Z`).

## Prepare and review

From a clean, current `main` with uv, Rust and authenticated GitHub CLI installed:

```bash
uv run release/prepare.py --version 0.1.0 --dry-run
uv run release/prepare.py --version 0.1.0
uv run release/push.py --dry-run
uv run release/push.py
```

Preparation checks PyPI, synchronizes version entries and moves Unreleased notes
into one versioned section. Repeating it does not duplicate notes. Network failures
block preparation. The push command stages only release files, creates
`release/vX.Y.Z` and opens or reuses one PR against `main`. Neither command creates
a tag, merges a PR or publishes a release. Unrelated changes are rejected.

## Validate distributions

CI and **Release dry run** share the five-platform ABI3 build matrix: Linux x86_64
and ARM64, macOS x86_64 and ARM64, and Windows x86_64. Every wheel and the sdist is
installed in isolated Python 3.12, 3.13 and 3.14 environments on a matching runner.
Builds use `uvx` with the Maturin version pinned in `pyproject.toml`, the Rust
toolchain from `rust-toolchain.toml`, and `--release --locked`. Python 3.12 is
installed explicitly for the ABI3 build. Linux uses `ziglang==0.15.2` as a
build-only linker with `--zig --compatibility manylinux_2_28 --auditwheel check`;
macOS and Windows use their native toolchains. No Maturin GitHub Action is required.
The gate binds each artifact and JUnit report to one commit/version and checks
metadata, tags, licenses, inventories and SHA-256 hashes. Missing platforms,
failed/skipped tests or modified bytes block the complete set.

Run **Release dry run** manually with the committed version and `publish: false`.
Private-repository jobs are skipped under the existing cost policy; a skip is
not validation. Record actual platform results in the PR. Benchmarks are a separate
manual workflow; see [Benchmarks](../tests/benchmarks/README.md).

For a local artifact, put exactly one wheel or sdist in `bundle/dist/`:

```bash
uv run python scripts/artifacts.py plan
uv run python scripts/artifacts.py test --kind wheel --target macos-arm64
# For the sdist, use a separate bundle:
uv run python scripts/artifacts.py test --kind sdist --target sdist --bundle sdist-bundle
# After collecting all native wheel receipts and the sdist receipt:
uv run python scripts/artifacts.py gate --bundle bundle --output verified
```

The checkout must be clean and committed for testing/gating. Synthetic tooling
fixtures test rejection logic and do not qualify native platforms.

## Authorize publication separately

After the release PR is merged, review and explicitly approve its exact commit.
Only then create a non-overwriting `vX.Y.Z` tag on that commit. Tag creation and
push are manual owner actions. The workflow does not run automatically on tags.

Activation requires a separately reviewed removal of the literal `false` publish
guard, verified PyPI project ownership and Trusted Publisher configuration, and a
protected `pypi` environment with required reviewers. Disable any historical
GitLab publisher/broker permissions before activation. Do not change repository
visibility or enable private paid runners to obtain validation.

Once separately enabled, dispatch the release workflow on that tag with the
matching version, exact `approved-commit` and `publish: true`. It verifies the tag,
commit and ancestry on `main`, builds/tests once and hands immutable artifact ID
and authenticated checksums to the environment-gated OIDC publisher. The publisher
rechecks bytes without rebuilding, refuses `skip-existing`, and verifies the exact
published file set and downloaded PyPI bytes. GitHub Release creation follows only
after that verification. A partial upload needs investigation before recovery.

Pages deployment stays disabled until separately authorized and configured.
