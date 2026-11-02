# Historical: XLSX extra columns without headers

This intermediate state is obsolete. [Explicit table sources](table-sources-verification.md)
are authoritative: unbound extra values are not emitted; `__column_*` support was removed.

## Snapshot and verdict

2026-10-31, repository `chooong.datasift`, branch `feat/datasift-package`,
bugfix base `456b3694804ce07f31e7c91a958559e65dbb7a8e`, existing PR #1.
The final HEAD is traceable through Git. The user file and generated NDJSON
are local data only, not fixtures or package contents.

UNDETERMINED for overall approval: implementation and local integration are
verified; remote CI and independent re-review of this delta remain UNVERIFIED.
No version change, dependency addition, release or deployment.

## Finding U01 — P1, independent closure OPEN

The user file has four headers and 2000 data rows with occasional extra values
in M, U and V. `Sink::on_row` aborted on the first matching record with such an
extra value. The CLI therefore reported only `RuntimeError`.

Correction: the worker still returns matches only. The PyO3 adapter transfers
named fields and additional populated cells under position-dependent keys such
as `__column_M`. `unnamed_column_name` resolves collisions by appending underscores
without overwriting real headers. No table pre-read or discarded extra values.
Filters still resolve real headers only. `None` without a header creates no
field; explicit empty text is preserved.

Invariant: identical input and mask yield identical typed values, including extra
data, regardless of batch size or repetition. Negative cases: name collisions must
not overwrite fields, unknown filter columns remain errors, and corrupt files
must not publish partial output.

## Coverage record

| File / direct consumer | Status |
| --- | --- |
| datasift-core/src/filter.rs | REVIEWED, header resolution and new position-dependent naming |
| datasift-core/src/lib.rs | REVIEWED, Ready/Batch processing, typed PyO3 cell conversion |
| datasift-core/src/xlsx.rs | REVIEWED, guard removed, remaining XML/archive validation preserved |
| datasift-core/src/value.rs | REVIEWED, cell types unchanged |
| src/chooong/datasift/_reader.py, __main__.py, _models.py | REVIEWED, direct consumers and Row contract unchanged |
| tests/test_contract.py | REVIEWED, synthetic OOXML regressions and actual CLI path |
| tests/test_cli.py, tests/test_engine.py | REVIEWED, existing error/atomicity/filter tests unchanged |
| scripts/bench.py, examples/filter.json | REVIEWED, direct consumers unchanged |
| README.md, docs/contract.md, CHANGELOG.md | REVIEWED, output contract and change documented |
| docs/verification.md | REVIEWED, addendum distinguished from historical snapshot |
| pyproject.toml, datasift-core/Cargo.toml, both CI workflows, Pre-Commit | REVIEWED, unchanged; Ruff rules unchanged |
| External consumers | No cross-repository changes or external integration claim |

## Executed checks

Successful final commands, exit code 0:

- `uv sync --frozen --reinstall-package chooong.datasift`: native local extension rebuilt.
- `.venv/bin/ruff check src tests scripts`; `.venv/bin/ruff format --check src tests scripts`.
- `.venv/bin/mypy src`: 5 source files without errors.
- `.venv/bin/pytest --cov --cov-report=term-missing`: 66 passed, 99.47% Python coverage.
- `cargo fmt --manifest-path datasift-core/Cargo.toml -- --check`.
- `cargo clippy --manifest-path datasift-core/Cargo.toml --locked --all-targets -- -D warnings`.
- `cargo test --manifest-path datasift-core/Cargo.toml --locked`: 6 passed.
- `.venv/bin/chooong-datasift daten.xlsx examples/filter.json --output treffer.ndjson`:
  121 matches, one extra value in matching rows preserved; complete independent
  ElementTree comparison against the original file passed; input hash unchanged.
- `uv build` and `.venv/bin/twine check dist/*`: wheel and sdist passed.
- Isolated installation of the built wheel: 66 tests passed and 121 matches
  with the user file; no editable installation or PYTHONPATH.
- `git diff --check`.

The original file was neither modified nor included in tests/artifacts. New fixtures
contain synthetic values only. Existing CLI error redaction is preserved;
cell values are not written to logs.

## TODO U01 — independent delta review

- Base: `456b3694804ce07f31e7c91a958559e65dbb7a8e`; check the final PR HEAD.
- Target: unnamed extra data remain lossless, names unique and streaming bounded.
- Files: three modified Rust files, test_contract.py and docs/contract.md.
- Steps: read the complete delta, trace collisions/column boundaries and repeat
  README quality commands and isolated wheel regression.
- Negative/replay tests: unknown filter columns, collisions, empty extra fields,
  corrupt data and atomic output; batch sizes 1, 3 and 1024, repeated scan.
- Acceptance: independent reviewer confirms data integrity and unchanged filter
  semantics; new regular CI run passes. Do not manually trigger or poll CI.
- Dependencies: independent reviewer and runner with the native toolchain.
- Consumer impact: previously rejected rows receive dynamic extra fields;
  previously valid rows and filters remain unchanged.
