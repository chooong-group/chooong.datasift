# Releasing

Publishing and Pages jobs are disabled by literal `false` guards. Activation
requires a separate reviewed change and maintainer approval.

## Validate a candidate

1. Synchronize Python/Cargo versions and update release notes only for an approved
   release. Use a clean reviewed commit.
2. Resolve hosted-runner eligibility: current workflows skip private repositories
   under the no-paid-runner policy. A skipped job does not validate a candidate.
3. Run **Release dry run** with the exact committed version and `publish: false`.
   It shares checks/builds with CI: five native ABI3 wheels and one sdist, each
   installed under Python 3.13 and 3.14 with real XLSX/XLSM tests.
4. Inspect the complete-set gate, metadata, platform tags, checksums and native
   test receipts. All evidence must match one commit/version. Cross-builds do
   not replace native tests. Record platform results and blockers in the PR/CI.

The gate hands off an immutable artifact ID and authenticated `SHA256SUMS` to
publishing. `verify_publish.py` rechecks those bytes; no rebuild occurs after
validation. Missing/failed platforms prevent upload.

For a local target, place one distribution in `bundle/dist/`:

```bash
uv run --frozen python scripts/artifacts.py plan
uv run --frozen python scripts/artifacts.py test --kind wheel --target macos-arm64
# Test the sdist in a separate bundle:
uv run --frozen python scripts/artifacts.py test --kind sdist --target sdist --bundle sdist-bundle
# Collect all five wheel receipts and the sdist receipt before gating:
uv run --frozen python scripts/artifacts.py gate --bundle bundle --output verified
```

Use the actual target ID from `release-targets.json`; the example assumes native
Apple Silicon. The gate refuses incomplete evidence and existing output.

## Enable PyPI publishing

1. Disable the registered historical GitLab publisher and revoke its old external
   OIDC broker allowance, including historical rerun paths.
2. Verify PyPI project/account ownership. Configure a Pending Trusted Publisher:
   project `chooong.datasift`, GitHub owner `chooong-group`, repository
   `chooong.datasift`, workflow `release.yml`, environment `pypi`. No token is needed.
3. Protect GitHub environment `pypi`: required reviewers, prevent self-review,
   restrict bypass where available and allow deployments only from protected
   `main`. Verify effective environment/ruleset restrictions under the current plan.
4. After independent review and complete native validation, review removal of
   `false &&` from the publish guard. Retain public-repository, protected-main,
   explicit `publish` and `PYPI_PUBLISH_ENABLED` guards. Set that variable to `true`
   only after configuration is verified.
5. Inspect a successful dry run, then explicitly approve a publishing invocation
   and its environment review. Verify registry contents before announcing it.

Uploads are not transactional: a network failure can leave a partial PyPI upload.
Investigate existing registry files before deliberate recovery; do not conceal
that state with `skip-existing`. Tag/release creation is not automated.

## Enable GitHub Pages

Configure Settings → Pages → GitHub Actions and protect `github-pages` for reviewed
`main` deployments. In a separately reviewed change, remove the Pages build's
`false &&` while retaining public/main/variable guards. Set `PAGES_DEPLOY_ENABLED`
to `true`, run **Documentation deployment**, approve the environment and verify the
site before linking it as live. Documentation builds remain independent of deployment.
