# Verification report

Current addendum: [Explicit table sources](table-sources-verification.md).
The [extra-column addendum](unnamed-columns-verification.md) is historical;
source selection superseded it after the extraction goal was clarified.
The sections below record the initial package verification. User approval and
PR #1 subsequently resolved push blocker D08; current pending acceptance checks
are recorded in the addendum.

Snapshot: 2026-10-31, repository `chooong-group/chooong.datasift`, branch
`feat/datasift-package`, base `97d4f59614c5294ab50253213a920390da44323d`.
HEAD and PR can be traced through Git and the PR; distributed files contain no
self-referential commit or artifact hashes.

## Verdict

BLOCKED for push/PR: automatic approval review rejected `git push`, requiring
explicit user consent to transfer the new source code and history to `origin`.
The branch exists locally only; no PR was created. No bypass or retry was attempted.

UNDETERMINED for overall approval: implementation and local evidence are available;
Linux CI and independent re-review remain UNVERIFIED. No publication, tag, merge,
database change or service change.

## Analysis and decisions

The entire existing repository was read, including the PoC, tests, benchmark,
license, Git ignore rules, instructions and both workflows. AGENTS.md, workflows,
Pre-Commit and the PoC were already staged when work began. These supplied files
are preserved as the starting point; only workflows/Pre-Commit are specifically
adapted to the new package. `gh pr list --state open` reported no open PRs.

The PoC remains unchanged as a historical reference. Its pyproject.toml declares
two competing build backends and is not a valid package configuration.
The supplied workflows were Orchestrator templates with nonexistent imports,
tests, database commands and RabbitMQ commands.

Solution ladder: the existing native engine already covers the core functionality.
Maturin handles packaging, Pydantic validates masks and generates schemas, and
dataclasses model immutable rows. Pydantic is the only new Python runtime dependency,
required for recursive structured filter inputs at the trust boundary. No additional
service layer, framework, database access or UI. Ruff rules were retained from the
supplied configuration; the historical PoC is outside the root check paths.
The initial version remains 0.1.0.

## Findings

Corrections are implemented and verified locally; independent closure of all
findings requires re-review.

| ID | Priority | Status | Cause, correction and evidence |
| --- | --- | --- | --- |
| D01 | P1 | Implementation verified locally | pyproject.toml:1 — Invalid packaging: root pyproject with one Maturin backend, namespace package, native abi3 extension, stubs and py.typed; install and test wheel/sdist |
| D02 | P1 | Implementation verified locally | src/chooong/datasift/_models.py:93 — Unvalidated Python masks and Any API: Pydantic models, operator enum, immutable Row; test_contract.py and mypy |
| D03 | P1 | Implementation verified locally | datasift-core/src/lib.rs:26 — Receiver was not Sync: Mutex protects native receiver management; build, Clippy and thread-switch test |
| D04 | P1 | Implementation verified locally | datasift-core/src/xlsx.rs:25 — EOF could accept incomplete XML: shared XML depth validation for all parts; worksheet/shared-string truncation tests |
| D05 | P1 | Implementation verified locally | src/chooong/datasift/__main__.py:38 — Output could overwrite the filter: input/mask alias checks, temporary output and rename; real CLI failure/symlink tests |
| D06 | P1 | UNVERIFIED | .github/workflows/ci.yml:15 — Unrelated CI replaced; Linux runner and release broker execution remain unverified |
| D07 | P1 | UNVERIFIED | Independent contract/data-integrity re-review pending |
| D08 | P1 | [ ] OPEN | Automatic approval review blocks push/PR; explicit consent to transfer to origin required |

## Coverage record

REVIEWED means the complete file was read and checked locally; it does not claim
that CI has run.

| Files / consumers | Coverage |
| --- | --- |
| AGENTS.md | REVIEWED, supplied instructions retained unchanged |
| .gitignore, LICENSE | REVIEWED, unchanged; Apache-2.0 metadata in the new package |
| README.md, CHANGELOG.md | REVIEWED, introduction and changes updated |
| docs/contract.md, docs/verification.md | REVIEWED, contract, limits and evidence |
| pyproject.toml, uv.lock | REVIEWED, Python dependencies and quality commands |
| datasift-core/Cargo.toml, datasift-core/Cargo.lock | REVIEWED, PyO3/abi3 and pinned Rust dependencies |
| datasift-core/src/value.rs | REVIEWED, I/O-independent cell values |
| datasift-core/src/filter.rs | REVIEWED, all operators, header resolution and error paths |
| datasift-core/src/xlsx.rs | REVIEWED, archive/XML reader and resource/format limits |
| datasift-core/src/lib.rs | REVIEWED, worker, channel, GIL release and iterator lifecycle |
| src/chooong/datasift/__init__.py | REVIEWED, documented public exports |
| src/chooong/datasift/_models.py | REVIEWED, models/enums/Row |
| src/chooong/datasift/_reader.py | REVIEWED, direct engine callers and file adapters |
| src/chooong/datasift/_rust.pyi, py.typed | REVIEWED, native type boundary and wheel marker |
| src/chooong/datasift/__main__.py | REVIEWED, CLI/NDJSON direct consumer |
| tests/test_engine.py | REVIEWED, inherited real OOXML fixtures and core flows |
| tests/test_contract.py | REVIEWED, all operators, invalid inputs, replay and concurrency |
| tests/test_cli.py | REVIEWED, actual CLI production path with files |
| scripts/bench.py, examples/filter.json | REVIEWED, benchmark consumer and example mask |
| .pre-commit-config.yaml | REVIEWED, existing Python checks, archive excluded |
| .github/workflows/ci.yml | REVIEWED, Python 3.13/3.14 matrix, Rust and installed artifacts; CI UNVERIFIED |
| .github/workflows/release-gitlab-pypi.yml | REVIEWED, existing CI artifact/hash/OIDC path retained, package tests replaced; publication UNVERIFIED |
| rust_xlsx_filter/README.md, pyproject.toml, Cargo.toml | REVIEWED, unchanged historical design baseline |
| rust_xlsx_filter/src/lib.rs, filter.rs, xlsx.rs | REVIEWED, original engine; new production code under datasift-core/ |
| rust_xlsx_filter/python/rust_xlsx_filter/__init__.py, __main__.py | REVIEWED, old API/CLI; no guaranteed consumer contract |
| rust_xlsx_filter/filter_excel.py, filter.json | REVIEWED, historical wrapper and example |
| rust_xlsx_filter/tests/test_engine.py, benchmarks/bench.py | REVIEWED, basis of inherited evidence |
| External consumers | None established in the repository; no cross-repository changes or integration claims |

## Local verification

Platform: macOS ARM64, CPython 3.13.15 and 3.14.6, Rust/Cargo 1.95.0.
The table records successful final checks; earlier development failures were
corrected and affected checks repeated. Python coverage does not cover the Rust engine.

| Command | Result / exit code |
| --- | --- |
| uv lock --check; uv sync --frozen | Valid lock, native editable installation; 0 |
| .venv/bin/ruff check src tests scripts | All checks passed; 0 |
| .venv/bin/ruff format --check src tests scripts | 9 files formatted; 0 |
| .venv/bin/mypy src | 5 source files without errors; 0 |
| .venv/bin/pytest --cov --cov-report=term-missing | 60 passed, 99.47% Python coverage; 0 |
| cargo fmt --manifest-path datasift-core/Cargo.toml -- --check | Passed; 0 |
| cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings | Passed; 0 |
| cargo test --manifest-path datasift-core/Cargo.toml --locked | 6 passed; 0 |
| uv build | Wheel and sdist, wheel built from sdist; 0 |
| .venv/bin/twine check dist/* | Wheel and sdist PASSED; 0 |
| Isolated wheel, Python 3.13, pytest -o addopts= tests | 60 passed; 0 |
| Isolated sdist, Python 3.13, pytest -o addopts= tests | 60 passed; 0 |
| Isolated wheel, Python 3.14, pytest -o addopts= tests | 60 passed; 0 |
| Installed chooong-datasift --help, python -m chooong.datasift --help | Passed; 0 |
| .venv/bin/python scripts/bench.py --rows 250000 --batch-size 1024 | 12500 matches, approximately 0.225 s; 0; no general performance guarantee |
| Load YAML and compile embedded Python scripts | Passed; 0; no substitute for Actionlint/CI |
| git diff --check | Passed; 0 |

Artifacts were checked without PYTHONPATH or editable installations in three separate
/tmp environments. The package inventory contains the native extension, stubs,
py.typed and license; the sdist also contains Cargo.lock and uv.lock. No PoC or
bytecode caches. No access to external APIs, existing services or databases.

## Individually verifiable TODOs

### D06 — Linux CI

- Base: 97d4f59614c5294ab50253213a920390da44323d; check the final PR HEAD.
- Target: full CI passes on the existing Linux x64 runner without Orchestrator,
  PostgreSQL or RabbitMQ dependencies.
- Files: both .github/workflows/*.yml, pyproject.toml, datasift-core/Cargo.toml.
- Steps: user checks the automatically started PR run; run Actionlint on both
  workflows. No manual triggering or polling by the agent.
- Negative/replay evidence: existing 60 tests, including invalid masks,
  truncation, atomic failure output, concurrency and independent repetition.
- Commands: all quality/package commands from ci.yml; Actionlint if available.
- Acceptance: both Python versions and wheel/sdist tests pass; no skipped jobs.
- Dependency: existing runner with uv, Rust/Cargo, C linker and network access.
- Consumer impact: Linux installability; no registry release requested.

### D07 — Independent re-review

- Base: 97d4f59614c5294ab50253213a920390da44323d; complete final PR diff.
- Target: independent assessment of contract, resource limits, lifecycle, error
  paths and data integrity using code and tests; self-reporting does not close findings.
- Files: all production files and tests in the coverage record.
- Steps: read the full diff; trace dynamic header resolution, type-aware
  comparisons, worker cancellation, XML errors and atomic output.
- Negative/replay tests: run test_contract.py, test_cli.py and Rust unit tests.
- Commands: repeat README quality commands and isolated artifact checks.
- Acceptance: no open P1/P2 findings; reviewer documents closure of D01–D05.
- Dependency: independent reviewer; consumers are CLI, benchmark and Python API.

### D08 — Consent for push and PR

- Base: 97d4f59614c5294ab50253213a920390da44323d; use the final local HEAD.
- Target: transfer this feature branch to `chooong-group/chooong.datasift`
  and create exactly one PR against main.
- Files: complete reviewed branch diff; no additional changes.
- Steps: obtain explicit user consent; then `git push --set-upstream
  origin feat/datasift-package`, followed by `gh pr create --base main --head
  feat/datasift-package --body-file <reviewed-PR-description>`.
- Negative/replay check: no retry without consent; check existing PRs after
  consent to avoid creating a duplicate.
- Verification: `git status --short`, matching local/PR HEADs, unchanged diff
  against base and exactly one PR URL. Do not poll CI.
- Acceptance: successful push and PR; then stop without merge/tag/release.
- Dependency: explicit approval of the data transfer flagged by automatic review.
- Consumer impact: reviewer access to code; no runtime consumer changes.
