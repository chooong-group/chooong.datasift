# Releasing

Version `0.1.0` remains unreleased. Publishing and Pages deployment are hard-disabled.
The project version in `pyproject.toml` is authoritative; Cargo and both lockfiles
must agree. Preparation supports canonical final PEP 440 versions (`X.Y.Z`).

## Prepare and review

From a clean, current `main` with uv, Rust and authenticated GitHub CLI installed:

<!-- check: syntax -->

```bash
uv run release/prepare.py --version 0.1.0 --dry-run
uv run release/prepare.py --version 0.1.0
uv run release/push.py --dry-run
uv run release/push.py
```

The changelog retains exactly one `## Unreleased` heading with user-facing notes.
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
failed/skipped tests or modified bytes block the complete set. `.gitattributes`
checks out `LICENSE` with LF endings on every build host, including Windows;
license comparisons remain byte-for-byte and do not normalize artifact contents.

Run **Release dry run** manually with the committed version and `publish: false`.
Validation jobs run for both private and public repositories. Record actual
platform results in the PR. Benchmarks are a separate
manual workflow; see [Benchmarks](../docs/development/benchmarks.md).

For a local artifact, put exactly one wheel or sdist in `bundle/dist/`:

<!-- check: syntax -->

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
visibility or organization billing settings as part of release preparation.

Once separately enabled, dispatch the release workflow on that tag with the
matching version, exact `approved-commit` and `publish: true`. It verifies the tag,
commit and ancestry on `main`, builds/tests once and hands immutable artifact ID
and authenticated checksums to the environment-gated OIDC publisher. The publisher
rechecks bytes without rebuilding, refuses `skip-existing`, and verifies the exact
published file set and downloaded PyPI bytes. GitHub Release creation follows only
after that verification. A partial upload needs investigation before recovery.

The publishing job directly requires both `release-identity` and `distributions`
to succeed. Keep this explicit identity gate even when distribution builds also
depend on it.

## Documentation deployment

Pages deployment remains hard-disabled. The prepared workflow builds the site,
checks its sources/examples and uploads only `site/`. Enabling deployment needs
an explicit reviewed change to the literal `false` guards,
`PAGES_DEPLOY_ENABLED=true` and an authorized GitHub Pages environment. Do not
change repository visibility, organization settings or budget guards as a shortcut.
The package Documentation URL stays on GitHub until Pages is reachable and authorized.

## Publisher identity

Configure a pending PyPI Trusted Publisher for distribution `chooong.datasift`
with owner `chooong-group`, repository `chooong.datasift`, workflow `release.yml`
and environment `pypi`. The workflow filename is case-sensitive. Configure this
in the owning PyPI account; a repository setting cannot establish PyPI ownership.
Use OIDC rather than adding a PyPI API token to GitHub secrets.

Before activation, configure a maintainer reviewer in the `pypi` environment.
Owner self-review may be enabled when explicitly approved by the release owner.
Restrict deployments to version tags (`v*`, type `tag`), not branch `main`.
The workflow independently checks exact version, approved commit and main ancestry;
the tag pattern alone is not release authorization. Verify the reviewer and tag
rules through GitHub settings after saving them. If the repository plan cannot
enforce approval, keep publishing disabled until an approved protection mechanism
is available. Do not upgrade billing or relax checks to bypass that limitation.

## First public release review

Review all reachable branches, commit messages, authors, PR bodies/comments,
review attachments and historical workflow logs/artifacts before changing
visibility. Squash merging a PR removes neither old PR records nor commits still
reachable through branches or GitHub PR refs. Deleting a working-tree document
also does not erase its history. Resolve sensitive findings with the owner before
exposure; secret rotation and GitHub support may be necessary. Never rewrite
history or delete records as an automatic preparation step.

Keep the changelog as the release-note source. Prepare the versioned section only
under a separate release authorization; review its text before the publisher
creates the GitHub Release. Do not add CI logs, process ledgers or local paths to
user-facing release notes. Update unreleased installation instructions and badges
only after verifying actual availability. Keep README/package links on repository
documentation until the Pages site is deployed and checked anonymously.
