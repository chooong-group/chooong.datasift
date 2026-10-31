# Releases

**No release, tag, registry upload or visibility change is part of this preparation.**
Publishing and Pages deployment contain a literal `false` guard. The former
`release-gitlab-pypi.yml` tag publisher is removed, so an old/new double upload is
not possible from the current workflow set. There is no dependency on a future
CI run and no polling for an independently triggered workflow.

## Build and test flow

`ci.yml` and `release.yml` call the same source-check and artifact workflows.
Source checks use locked dependencies, Ruff, mypy strict, Rust fmt/Clippy/tests
and a strict documentation build. Artifact jobs build one ABI3 wheel on each of
five native standard runners and one sdist. The Linux builds use Maturin's
manylinux 2.28 container support. This does not count as runtime validation until
the resulting artifact is installed on its matching native runner.

Every wheel is installed unchanged in clean CPython 3.13 and 3.14 environments;
the native extension must import from inside that environment. The full real
XLSX/XLSM fixture suite is run. The sdist is built/installed independently in two
clean environments. The original distribution is hashed before and after its test.
Dependencies come from `uv.lock`, exported with hashes; the Maturin backend and
Rust toolchain are pinned. No full project install or extra native build is
performed for source-only lint/docs checks.

Receipts bind the artifact filename, SHA-256, checkout commit, project version,
native OS/architecture, interpreter and JUnit checksum/count. The final gate
rejects missing/duplicate platforms, missing Python runs, wrong ABI/platform tags,
metadata inconsistencies, failed/skipped fixture runs, checksum changes and extra
files. Only the complete set is copied into `verified/dist/`. No rebuild occurs
after final testing. An immutable artifact ID and an authenticated `SHA256SUMS`
are passed to the separate publishing job, which rechecks the bytes without
installing project code. A missing/failed platform prevents any upload.

Registry uploads are not a transaction across the network: once publishing is
explicitly activated, a transport failure at PyPI can still leave a partial
upload. The local completeness gate prevents starting with an incomplete set;
it cannot promise registry-side rollback. Do not use `skip-existing` to conceal
such an event; investigate the published files before a deliberate recovery.

## Safe dry run

The repository is currently private. Standard GitHub runners can incur charges
there, so all compute entry points are gated off for private repositories. A
skipped workflow is **not** successful validation. No paid/larger runners or
external CI services are used. An owner must resolve public availability or
explicitly approve a different compute policy separately; this change does neither.

Once eligible to run without violating that policy, an owner can manually invoke
**Release dry run** on a reviewed ref and supply its exact existing version.
Leave `publish` false. This uses the same native builds, installations, evidence
and final gate as a future release, with no PyPI access or permanent token.
The agent does not trigger/poll CI, change visibility, or dispatch a dry run.

Local native evidence can be produced without PyPI:

```bash
uv run --frozen python scripts/artifacts.py plan
# Put one already-built native wheel in bundle/dist/, then:
uv run --frozen python scripts/artifacts.py test --kind wheel --target macos-arm64
# Test an sdist separately in a bundle containing only that distribution:
uv run --frozen python scripts/artifacts.py test --kind sdist --target sdist --bundle sdist-bundle
# After collecting all five wheel receipts and the sdist receipt in one bundle:
uv run --frozen python scripts/artifacts.py gate --bundle bundle --output verified
```

Choose the actual native target ID from `.github/release-targets.json`; the example
is for Apple Silicon. Testing one local wheel does not satisfy the global gate.
The gate correctly fails until every required native platform has evidence.
Build inputs must match a clean reviewed commit for release evidence.

## Retire the historical publisher

Before any activation, an owner must disable the registered **Release to private
GitLab PyPI** workflow in GitHub Actions, including reruns of historical commits.
The file is removed from current source, but that alone cannot revoke historical
workflow definitions or an external OIDC broker policy. Revoke its old broker
allowlist/permissions through the responsible owner. This preparation makes no
external settings change; retirement is an explicit release blocker.

## Manual PyPI activation, after all release blockers close

1. Confirm the target project name is available and log into the intended PyPI
   owner account with the required organization permissions. No account or name
   reservation has been created by this change.
2. On PyPI, create a **Pending Trusted Publisher** for `chooong.datasift`: GitHub
   owner `chooong-group`, repository `chooong.datasift`, workflow `release.yml`,
   environment `pypi`. Use the exact filename and case. Do not create a token.
3. In GitHub repository Settings → Environments, create `pypi` with required
   reviewers, prevent self-review, disable administrator bypass where available,
   and allow deployments only from protected `main`. Configure branch/ruleset
   protection and require the CI gates. Verify those protections actually apply
   under the repository's plan before enabling publication.
4. Obtain owner approval and close every native platform, artifact, metadata and
   independent-review blocker in [Readiness](readiness.md).
5. In a separate reviewed activation PR, remove only the leading literal `false &&`
   from the publishing job guard. Keep the public-repository, explicit `publish`,
   `PYPI_PUBLISH_ENABLED == 'true'`, protected-main and successful-needs guards.
   Set the repository variable `PYPI_PUBLISH_ENABLED` to `true` only after the
   environment and PyPI publisher are verified. The publishing job alone has
   `id-token: write`; no permanent PyPI credential is needed.
6. Run the dry run first and inspect its complete verified artifact/evidence set.
   For an explicitly approved release invocation set `publish` true and obtain
   the environment review. The job publishes exactly `verified/dist/`, never a
   rebuilt package. Verify registry contents before announcing a release.

No tag/release creation is automated. Version 0.1.0 is unchanged. Future version
changes require an explicit release decision, synchronized Python/Cargo versions
and release notes moved from Unreleased to the actual version/date.

## Manual GitHub Pages activation

1. After owner approval, open Settings → Pages and select **GitHub Actions** as
   the build source. Create/protect the `github-pages` environment, with deployments
   restricted to reviewed `main` and required reviewers as appropriate.
2. In a separate reviewed change, remove the literal `false &&` from the Pages
   build guard, retaining the public-repository, `PAGES_DEPLOY_ENABLED == 'true'`
   and main-branch restrictions. Set that variable only when ready.
3. Manually invoke **Documentation deployment** on `main`, review the environment
   deployment and verify the resulting site before linking it as live.

The configured future URL is `https://chooong-group.github.io/chooong.datasift/`.
It is not advertised as an already deployed site. CI builds the docs independently
of this disabled deployment workflow.

## Authoritative references

- [GitHub standard runner availability and pricing](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Maturin distribution and manylinux](https://www.maturin.rs/distribution.html)
- [PyPI Pending Trusted Publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPI publishing with GitHub OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
