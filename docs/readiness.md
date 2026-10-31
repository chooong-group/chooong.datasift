# Validation and Release Blockers

**Verdict: BLOCKED for release.** Native Linux x86_64/aarch64, Windows x86_64
and Intel macOS execution, the complete real artifact gate and independent review
are outstanding. Publishing and Pages are hard-disabled. No release, tag, merge,
visibility change or external account/environment configuration was performed.

## Review baseline and evidence

Repository: `chooong-group/chooong.datasift`; branch: `feat/open-source-readiness`.
Base: `4c3913905c1a048bc452fe961ee5ea098fcbcf49` (merged PR #1).
Executable candidate: `caeba467ed23340ceddbec578e51b271bb91b92b`, version `0.1.0`.
Checked on 2026-10-31, macOS arm64, CPython 3.13.15 / 3.14.6, Rust 1.95.0.
The subsequent commit records documentation only; these artifact identities bind
to the executable candidate, not to a future PR HEAD. No final-head remote CI
result is claimed. The PR contains the exact base-to-head file list; reproduce it
with `git diff --name-status 4c3913905c1a048bc452fe961ee5ea098fcbcf49...HEAD`.

Local artifacts, receipts, JUnit and logs are under
`/tmp/datasift-readiness-final/`, outside Git and the distributions. They are
local evidence, not durable CI artifacts or evidence for another native platform.

| Target | CPython 3.13 | CPython 3.14 | Release status |
| --- | --- | --- | --- |
| Linux x86_64 / manylinux 2.28 | UNVERIFIED | UNVERIFIED | BLOCKED: R01 |
| Linux aarch64 / manylinux 2.28 | UNVERIFIED | UNVERIFIED | BLOCKED: R02 |
| Windows x86_64 | UNVERIFIED | UNVERIFIED | BLOCKED: R03 |
| macOS x86_64 | UNVERIFIED | UNVERIFIED | BLOCKED: R04 |
| macOS arm64 wheel | 179 passed, 99.54% coverage | 179 passed, 99.53% coverage | Locally validated candidate |
| sdist build/install on macOS arm64 | 179 passed, 99.54% coverage | 179 passed, 99.53% coverage | Locally validated candidate |

Wheel: `chooong_datasift-0.1.0-cp313-abi3-macosx_11_0_arm64.whl`.
SHA-256: `1ab71609fa2b39bc7d78235b92bfdd14a3002c58dbc069310043f7105c94d389`.

Source: `chooong_datasift-0.1.0.tar.gz`.
SHA-256: `0cb128744f3d0576f85a675e2adaa0e96db971cc6e4089408ae82337cf444e9d`.

Binary-only installation of this exact wheel (`uv pip install --only-binary :all:`)
and both `chooong-datasift` and `python -I -m chooong.datasift` were additionally
verified in fresh 3.13/3.14 environments against the two-row quickstart result.

The native import probe runs with `-I` outside the checkout and verifies both
package and extension origins inside each fresh environment. Installation uses
the exact candidate, never an editable source import. Coverage explicitly uses
the project configuration and measures the installed package. Real fixtures cover
XLSX/XLSM, masks, adjacent tables, headers, error paths and atomic CLI output.

## Executed checks

All success rows below returned exit code 0. The incomplete-set gate deliberately
returned 1; the surrounding check asserted its reason and absence of output.

| Command | Observed result |
| --- | --- |
| `uv lock --check` | 68 locked packages resolved; lock consistent |
| `.venv/bin/ruff check src tests scripts examples` | All checks passed |
| `.venv/bin/ruff format --check src tests scripts examples` | 19 files formatted |
| `.venv/bin/mypy src` | Five source files, no issues |
| `.venv/bin/mypy --strict scripts/artifacts.py scripts/verify_publish.py scripts/bench.py examples/create_sample.py` | Four files, no issues |
| `.venv/bin/python -m pytest --cov --cov-report=term-missing -q` | 179 passed, 99.54% coverage |
| `.venv/bin/python -m pytest tests/test_release_tooling.py -q` | 32 passed |
| `cargo fmt --manifest-path native/Cargo.toml -- --check` | Passed |
| `cargo clippy --manifest-path native/Cargo.toml --locked --all-targets -- -D warnings` | Passed |
| `cargo test --manifest-path native/Cargo.toml --locked` | Eight passed |
| `.venv/bin/mkdocs build --strict` | Site built without warnings |
| `/tmp/datasift-actionlint/actionlint -shellcheck= -pyflakes= .github/workflows/*.yml` | Actionlint 1.7.12 passed; optional ShellCheck/Pyflakes unavailable |
| `.venv/bin/python scripts/artifacts.py plan` | Five native targets; metadata/toolchain constraints valid |
| `uv build --wheel --sdist --out-dir /tmp/datasift-readiness-final/dist` | Exact wheel/sdist above built |
| `.venv/bin/twine check /tmp/datasift-readiness-final/dist/*` | Both passed |
| `.venv/bin/python scripts/artifacts.py test --kind wheel --target macos-arm64 --bundle /tmp/datasift-readiness-final/wheel` | Both isolated Python runs passed |
| `.venv/bin/python scripts/artifacts.py test --kind sdist --target sdist --bundle /tmp/datasift-readiness-final/sdist` | Both isolated source build/install runs passed |
| `.venv/bin/python scripts/artifacts.py gate --bundle /tmp/datasift-readiness-final/incomplete-bundle --output /tmp/datasift-readiness-final/must-not-publish` | Expected exit 1: incomplete platform evidence; output absent |
| `.venv/bin/python scripts/bench.py` | 2,000,000 scanned; 100,000 matched; two sheets; 3.11 seconds filtering locally, not a performance guarantee |
| `git diff --check` | Passed |
| `gh issue list --state open --limit 100 --json number,title,body,url` | No open GitHub issues; remaining work comes from the local task and blockers below |

The 32 tooling tests exercise complete synthetic evidence, byte preservation and
replay refusal, missing platforms/sdist/Python runs, duplicate Python evidence,
wrong commits/versions/native platforms, changed artifacts/JUnit, failed/skipped
or missing fixture tests, extra files, unsafe filenames, wrong ABI/platform/content
tags, missing native/source inputs and license inconsistencies. They also test
uncommitted tracked/untracked inputs, post-gate upload tampering, disabled workflow
permissions and the real quickstart's overwrite guard. Synthetic native binaries
and receipts are explicitly fake; they establish gate behavior only.

An existing coverage mistake was found during isolated installation: plain
`--cov` from a temporary directory measured tests instead of the installed
package. The final candidate explicitly supplies `--cov=chooong.datasift` and
`--cov-config`; the four results above come from the corrected execution.

## Coverage of changed files and direct consumers

`GEPRÜFT` means local source/diff review, not independent approval or remote CI.

| Files or consumer | Coverage |
| --- | --- |
| `.github/workflows/ci.yml`, `checks.yml`, `artifacts.yml`, `release.yml`, `docs-pages.yml` | GEPRÜFT: triggers, public-only compute, read-only fork execution, native matrix, needs chain, evidence transfer, hard-disabled publication/deployment; Actionlint and policy test passed; actual hosted execution UNVERIFIED |
| Removed `.github/workflows/release-gitlab-pypi.yml` | GEPRÜFT: tag publisher, shared OIDC rights, self-hosted execution and polling removed; historical external authorization remains R08 |
| `.github/actions/tooling/action.yml`, `.github/release-targets.json`, `rust-toolchain.toml` | GEPRÜFT: pinned toolchain/actions and canonical native matrix; target execution R01-R04 |
| `.github/ISSUE_TEMPLATE/{bug,feature,config}.yml`, `.github/pull_request_template.md` | GEPRÜFT: synthetic reproducers, private security reporting caveat, explicit verification/release blockers |
| `scripts/artifacts.py`, `scripts/verify_publish.py`, `tests/test_release_tooling.py` | GEPRÜFT: actual CLI gate/provenance/inventory/publisher failure paths, replay, byte preservation, atomic output and strict typing; 32 tooling tests |
| `scripts/bench.py` | GEPRÜFT: explicitly requested 2,000,000-row default, all-sheet mask, Excel-compliant per-sheet coordinates; actual native benchmark passed |
| `examples/create_sample.py`, `examples/quickstart-filter.json`, `examples/filter_2000000.json` | GEPRÜFT: synthetic quickstart and overwrite refusal; existing large-workbook mask retained without semantic edits |
| `.gitignore`, `pyproject.toml`, `uv.lock`, `native/Cargo.toml` | GEPRÜFT: excludes, metadata/URLs/classifiers, pinned build backend and justified dev dependencies; runtime requirements/version/engine unchanged; wheel/sdist inventory validated |
| `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` | GEPRÜFT: English entry point, runnable public quickstart, Unreleased notes, honest support/security status |
| `mkdocs.yml`, `docs/{index,getting-started,installation,python-api,cli,contract,headers,sources,tables,limits,errors,contributing,releases,readiness}.md` | GEPRÜFT: contract-consistent English site, limits, disabled deployment and manual activation; strict build passed |
| Root `AGENTS.md` removal / local `.data/AGENTS.md` | GEPRÜFT: user moved maintainer rules to ignored local data; current rules read and retained locally |
| Local `examples/{daten,daten_schmutzig,daten_2000000_schmutzig}.xlsx` | GEPRÜFT: moved from `.data` without changing SHA-256; excluded from Git and both distribution inventories; business contents not inspected/published |
| `src/chooong/datasift/**`, `native/src/**`, `native/Cargo.lock` | GEPRÜFT: base-to-candidate diff empty; public runtime/contract unchanged; full real fixture suite run against installed candidates |
| Existing `tests/*.py`, CLI, public Python imports, JSON masks and benchmark | GEPRÜFT: direct repository consumers exercised; quickstart and CLI run through the installed candidates; no supported external consumer integration supplied or changed |
| Historical `docs/*verification.md` | GEPRÜFT as historical evidence, excluded from new site/sdist; old broker/CI statements are not current acceptance evidence |
| GitHub settings, PyPI, hosted native runs and external consumers | NICHT GEPRÜFT operationally: no authorization to configure accounts/publish/change visibility; only repository metadata read; no CI dispatched, polled or awaited |

MkDocs is required for the requested website; packaging validates wheel tags and
metadata; PyYAML checks workflow policy in tests. These are development dependencies.
No new runtime dependency, external service, API/mask change or version bump exists.
Apache-2.0 metadata and actual artifact license files match the unchanged repository
license; no unverified copyright ownership statement was added. Source installation
passes `maturin.build-args=--locked` to prevent Cargo lockfile updates.

## Findings and individually acceptable TODOs

All items use base `4c3913905c1a048bc452fe961ee5ea098fcbcf49`. Revalidate against
the reviewed activation/candidate HEAD; local evidence at `caeba46` does not carry
forward automatically. Independent review is required before closing any item.

### R01 — P1, UNVERIFIED: Linux x86_64

Files: `.github/release-targets.json`, `.github/workflows/artifacts.yml`,
`scripts/artifacts.py`. On native Linux x86_64, build the declared manylinux wheel,
run `artifacts.py test --kind wheel --target linux-x86_64`, and validate with Twine.
Accept only successful 3.13/3.14 XLSX/XLSM tests, matching native probes, commit,
version, tags and hashes. Re-run the gate negatives after any correction; replay
must not overwrite a verified bundle. Depends on R06. Consumers: Linux wheel users.

### R02 — P1, UNVERIFIED: Linux aarch64

Same files; use a native ARM runner and target `linux-arm64`. Run the exact wheel
under both interpreters; a cross-build is insufficient. Apply R01's hash/tag,
fixture, negative and replay criteria. Depends on R06. Consumers: Linux ARM users.

### R03 — P1, UNVERIFIED: Windows x86_64

Same files; use native Windows/MSVC and target `windows-x86_64`. Both interpreters
must load the installed `.pyd`, pass all fixtures including CLI path handling,
and validate the declared Windows tag. Apply R01's negative/replay criteria.
Depends on R06. Consumers: Windows wheel users.

### R04 — P1, UNVERIFIED: macOS x86_64

Same files; use native Intel macOS and target `macos-x86_64`. Both interpreters
must load the installed extension and pass fixtures with the declared macOS tag.
An Apple Silicon cross-build is insufficient. Apply R01's negative/replay criteria.
Depends on R06. Consumers: Intel macOS wheel users.

### R05 — P1, OPEN: complete real artifact set

Files: artifact workflow and both release scripts. At one reviewed commit collect
all five wheel receipts and one sdist receipt, then run `artifacts.py gate` and
`verify_publish.py` with the returned checksum digest. Accept six unchanged files,
valid metadata/tags/hashes and both Python reports for every artifact. Remove one
platform, mutate bytes or fail a test: each must prevent output/upload. Repeat
against existing output: refusal must preserve it. Depends on R01-R04 and new
same-commit macOS ARM/sdist evidence. Consumers: all registry installations.

### R06 — P1, OPEN: eligible compute policy

Files: CI/release/check/artifact workflow public-only guards and `docs/releases.md`.
The repository is private; standard hosted jobs are skipped to avoid implicit
charges. Owner must resolve this under the no-paid-runner/no-visibility-change
constraints or explicitly revise those constraints in a separate decision. This
PR neither changes visibility nor starts compute. Accept documented owner decision
and effective runner eligibility, retaining secret-free read-only fork execution.
Test private rejection and normal PR behavior after any policy change. Blocks
R01-R05; affects validation rather than runtime consumers.

### R07 — P1, OPEN: independent review

Files: complete base-to-head diff listed by the command above. A reviewer must
independently inspect permissions, dynamic native matrix, source/metadata inventory,
artifact provenance, byte handoff, test evidence, replay refusal and public docs.
Run the 32 tooling tests plus source and installed-artifact checks. Acceptance
requires recorded review findings resolved or explicitly left open; agent reports
alone cannot close this item. Consumers: all supported import/CLI/install paths.

### R08 — P1, OPEN: historical publisher retirement

Files: removed old workflow, `docs/releases.md`. An owner must disable the registered
historical GitLab publisher/reruns and revoke its external broker allowance. Verify
old tag/rerun paths cannot obtain publication rights; don't create a tag to test
this preparation. Acceptance requires configuration evidence from the responsible
owner. No account changes made here. Blocks any future upload activation.

### R09 — P1, OPEN: protected PyPI environment

Files: `.github/workflows/release.yml`, `docs/releases.md`. Owner must configure
`pypi` with effective required reviewers, prevented self-review, appropriate bypass
restrictions and protected-main deployment rules. Verify unapproved/non-main
publication is denied under the actual repository plan. Publishing stays literal
`false` until protections and R01-R08 are accepted. No runtime consumer change.

### R10 — P1, OPEN: Pending Trusted Publisher

Files: release workflow and release guide. Owner must verify name/account ownership
and configure PyPI project `chooong.datasift`, GitHub owner `chooong-group`, repository
`chooong.datasift`, workflow `release.yml`, environment `pypi`, without a permanent
token. Verify exact subject fields and denial of mismatched ref/environment. This
preparation performs no registry transaction. Depends on R08/R09; future activation
requires a separate approved PR and complete real dry run. A failed network upload
can still be partial at the registry; investigate before any deliberate replay.

### R11 — P2, DEFERRED: Pages activation

Files: `.github/workflows/docs-pages.yml`, `mkdocs.yml`, `docs/releases.md`.
Deployment is hard-disabled by literal `false`; local/CI docs builds remain
independent; README describes no live website. Those three conditions justify
DEFERRED, not completion. After separate owner approval configure Pages Actions
source and the protected `github-pages` environment, review guard activation,
then verify deployment URL and rejection of unapproved/non-main deployment.
No package consumer depends on the site being deployed. This PR activates nothing.
