# Explicit table sources — verification report

## Snapshot and verdict

2026-10-31, `chooong.datasift`, branch `feat/datasift-package`, base
`beb1b834628dfc351ba4b7884ccfaf679ef4e5bb`, existing PR #1. The exact final
diff is this base against local HEAD or the working tree. User files and NDJSON
remain unversioned and are not package contents.

UNDETERMINED for overall approval: local implementation and evidence are available;
independent review, remote CI and transfer of this delta remain UNVERIFIED.
The previous push attempt was not executed because automatic approval review
could not finish due to insufficient workspace credits. No changes to version,
dependencies, Ruff rules, services or other repositories.

## Finding T01 — P1, independent closure pending

The previous approach treated the entire header row as the schema and even added
unnamed extra data. This failed to model adjacent tables, multiline headers and
comments correctly as extraction boundaries.

Solution ladder: the existing streaming engine can read cell ranges; explicit
source selection is needed, without another table heuristic or Excel library.
`TableSource` binds unique output/filter names to absolute columns through
`ColumnBinding`. The first row, optional end and `skip_rows` determine records.
Header text is not interpreted in this mode. `__column_*` support was removed;
unrelated values are no longer included automatically.

Invariant: `source` bounds input and output; `where` checks its bound values only.
Other tables/comment rows must not add matches or overwrite values. Batch size,
repetition and header text do not change results. Errors within the source and
corrupt XML remain errors; atomic NDJSON output is preserved.

Comments are not inferred: those before the data start are excluded; within the
data range, the mask specifies `skip_rows` or predicates. Multiple tables use
separate masks. Automatic detection or reconstruction of merged/multiline headers
is not implemented.

## Coverage

| Files / consumers | Status |
| --- | --- |
| src/chooong/datasift/_models.py | REVIEWED, canonical Pydantic models and range/alias validation |
| src/chooong/datasift/__init__.py | REVIEWED, public TableSource/ColumnBinding exports |
| datasift-core/src/filter.rs | REVIEWED, source contract, position resolution, unchanged filter operators |
| datasift-core/src/xlsx.rs | REVIEWED, streaming selection before cell conversion, full XML structure still validated |
| datasift-core/src/lib.rs | REVIEWED, bound fields only, lifecycle unchanged |
| datasift-core/src/value.rs, src/chooong/datasift/_reader.py, __main__.py | REVIEWED, direct consumers/cell types unchanged |
| tests/test_sources.py | REVIEWED, real OOXML layouts and error paths, no internal mocks |
| tests/test_contract.py | REVIEWED, previous extra-field expectation corrected |
| tests/test_engine.py, test_cli.py | REVIEWED, existing filter, atomicity and lifecycle paths |
| examples/filter.json, examples/layout-filter.json | REVIEWED, actual user file and synthetic layout test respectively |
| README.md, docs/contract.md, CHANGELOG.md | REVIEWED, source model, limits and contract correction documented |
| docs/verification.md, unnamed-columns-verification.md | REVIEWED, old snapshots marked historical |
| pyproject.toml, datasift-core/Cargo.toml, lockfiles, both workflows, Pre-Commit | REVIEWED, unchanged |
| scripts/bench.py | REVIEWED, direct consumer of unchanged simple header mode |
| External consumers | No cross-repository change or integration claim |

## Local evidence

Successful final commands (exit 0):

- `.venv/bin/ruff check src tests scripts`, `.venv/bin/ruff format --check src tests scripts`.
- `.venv/bin/mypy src`: 5 source files without errors.
- `.venv/bin/pytest --cov --cov-report=term-missing`: 88 passed,
  99.55% Python coverage; no Rust coverage claim.
- `cargo fmt --manifest-path datasift-core/Cargo.toml -- --check`.
- `cargo clippy --manifest-path datasift-core/Cargo.toml --locked --offline --all-targets -- -D warnings`.
- `cargo test --manifest-path datasift-core/Cargo.toml --locked --offline`: 6 passed.
- Declared Maturin backend, locally available version 1.16.0:
  `maturin build --release --offline --locked -i .venv/bin/python --out dist`
  and `maturin sdist --out dist`; `.venv/bin/twine check dist/*`.
- Isolated wheel installations on Python 3.13 and 3.14: 88 tests passed each.
- Actual local CLI with `daten.xlsx` and `examples/filter.json`: 121 matches,
  exactly the four selected fields, original input hash unchanged.
- `git diff --check`.

A diagnostic direct Cargo extension build without Maturin failed on macOS due to
missing dynamic Python linker flags. The supported Maturin build supplies these
flags and passes. No build or validation rules were weakened. The local native
extension was updated from this wheel.

## TODO T01 — independent review and remote evidence

- Base: `beb1b834628dfc351ba4b7884ccfaf679ef4e5bb`; complete local delta.
- Target: independently confirm source selection/projection without unrelated
  tables, unchanged filter semantics and safe error handling.
- Files: modified models, three Rust files, both test files and contract.
- Steps: read the complete delta, repeat source examples and README checks;
  transfer changes to the existing PR once approval review is available again.
- Negative/replay tests: range errors, alias collisions, unknown aliases, corrupt
  selected cells, corrupt XML beyond the range, atomic output, batch sizes
  1/2/1024 and repetition.
- Acceptance: independent review without open data-integrity findings and a
  successful regular CI run at final PR HEAD. Do not manually trigger/poll CI.
- Dependencies: reviewer, workspace approval review, configured runner toolchain.
- Consumer impact: optional new `source` mask and explicit output projection;
  no automatically generated extra fields. No version/release requested.

## Addendum H01 — automatic header indices

Base `f30f8cd9b60af58145fdaa0123194088e9d350bb`, 2026-10-31. The user clarified:
repeated Excel headers receive suffixes starting at 1, such as `Revenue_1` and
`Revenue_2`. Shared header resolution applies this before filter compilation and
iterator return, in physical column order and independently of batches. Unique
names remain unchanged. Indexed names must be unique; collisions with existing
suffixed names produce a controlled error. `source.columns.name` values are explicit
aliases and remain separate from this automatic behavior.

REVIEWED: datasift-core/src/filter.rs (root cause and naming), direct consumer
datasift-core/src/xlsx.rs (header resolution), datasift-core/src/lib.rs (Ready/output
contract), tests/test_contract.py, tests/test_header_indexing.py, README.md,
docs/contract.md and CHANGELOG.md. CLI, Python reader, models and workflows are
unchanged; existing contract/source/atomicity tests remain relevant and passed.
No version, dependency, migration or Ruff rule changed.

Final checks, exit 0: Ruff check/format, mypy (5 files), pytest --cov (99 passed,
99.55% Python coverage), cargo fmt, Clippy with `-D warnings`, cargo test (7 passed),
Maturin wheel/sdist and Twine. Isolated wheel: 99 tests passed each on Python 3.13
and 3.14. Regressions cover two/three repetitions, indices up to 12, empty columns,
shifted headers, typed values, batch sizes, replay, CLI keys, nontext headers and
suffix collisions before iterator return. User data remain outside Git and artifacts.

TODO H01 (P1, independent closure pending): reviewer checks the delta from the base
above, especially `headers_from_row`, collisions and filter/output mapping.
Repeat `tests/test_header_indexing.py`, Rust tests and README quality commands;
check the final regular PR CI run without manually triggering/polling it.
Acceptance: unique mapping without value loss/overwriting, unchanged unique headers,
all checks pass. Dependencies: independent reviewer and runner toolchain.
Consumer impact: previously rejected duplicate headers become selectable through
indexed names. Overall approval remains UNDETERMINED until review and remote evidence.

## Addendum S01 — all worksheets with `sheet: null`

Snapshot 2026-10-31, repository `chooong.datasift`, branch `feat/datasift-package`,
base `bc4d9f4304d1af86571e6c7b8ed3cec1abc4bcbb`, existing PR #1.
Exact diff after commit: `git diff bc4d9f4...feat/datasift-package`.
Eleven modified/new files. This addendum supersedes the older snapshots above
for this delta.

S01, P1, independent closure pending: `sheet` remains required and now accepts JSON
null. The existing streaming engine processes all worksheets in workbook order,
with separate header/filter resolution and no extra output fields. No second
reader or new dependency. Names still select one sheet. Without `source`, missing
headers and incompatible schemas are skipped; with `source`, bindings apply to
every sheet. Structural errors remain errors, including after initial matches and
in skipped sheets. The CLI replaces its destination only after a successful full scan.

REVIEWED in full: `_models.py`, `_reader.py`, `datasift-core/src/filter.rs`,
`datasift-core/src/xlsx.rs`, `datasift-core/src/lib.rs`, `tests/test_all_sheets.py`,
`examples/filter.json`, README.md, CHANGELOG.md and docs/contract.md.
Direct consumers: Python reader and CLI, existing contract/engine/source/header
tests; unchanged paths checked by the full suite. Build configuration, workflows
and lockfiles unchanged. No external consumer changes. Local user files remain
unversioned; the sdist is built from a targeted source copy to exclude unversioned examples.

Local evidence (exit 0): Ruff check/format, mypy (5 files), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 passed),
pytest --cov (112 passed, 99.55% Python coverage), Maturin wheel/sdist, Twine and
`git diff --check`. Isolated wheels: 112 tests each on Python 3.13 and 3.14.
Tests cover sheet order despite differently ordered relationships, hidden sheets,
chart sheets, different columns, missing headers, explicit sources, empty results,
invalid regexes, batch sizes 1/2/1024, replay and unchanged input. Errors in later
sheets, externally linked worksheets and truncated XML are rejected; existing CLI
output remains unchanged on failure.

Verdict: UNDETERMINED for overall approval; implementation and local evidence are
available, independent review and remote CI remain UNVERIFIED.

TODO S01-Review: base as above. Reviewer reads the full diff of listed files,
especially metadata order, Ready/Batch mapping, missing headers and atomic output
on late failure. Verification: repeat README quality commands and
`tests/test_all_sheets.py`. Acceptance: no open data-integrity findings, identical
matches for replay/all batch sizes, errors do not overwrite output. Dependency:
independent reviewer. Consumer impact: optional all-sheet search without changing row schemas.

TODO S01-CI: same base/files. After push, check regular CI at final PR HEAD;
no manual triggering/polling by the agent. Acceptance: all configured checks,
including existing negative/replay tests, pass. Dependency: runner toolchain.
Consumer impact: cross-platform build/contract evidence remains UNVERIFIED until then.

The first commit attempt failed with exit 128 (`agent refused operation`).
Following user feedback, commit/push is retried with unchanged SSH signing;
the final commit is recorded at PR HEAD.

## Addendum A01 — automatic header discovery and mask projection

Snapshot 2026-10-31, `chooong.datasift`, branch `feat/datasift-package`, base
`2b9bb9822079687ab09327b86082452772326c0b`, existing PR #1.
Exact diff after commit: `git diff 2b9bb98...feat/datasift-package`.
This addendum supersedes older header/output statements.

A01 (P1, independent closure pending): the previous fixed header row made row
positions part of mask knowledge and treated unrelated comments as columns.
The existing streaming engine now resolves the first row containing all mask
columns as the header. It projects filter input and output onto referenced columns,
including `any`/`not`, also with `source`. Solution ladder: reuse existing header
resolution and filter references; no second reader, formatting heuristic or new dependency.

Invariants: shifted headers and preceding titles require no row setting; comments
and neighboring columns do not enter results. Referenced columns remain unique
and in physical order (with `source`: binding order). Unrelated columns are not
converted after schema detection. Corrupt selected values and structurally corrupt
XML remain errors; atomic output survives late failures. Batch size/replay do not change values.

Explicit breaking change in the greenfield contract: `header_row` is removed;
remove it from masks. Unused headers/source aliases no longer appear in results.
Detection is limited to the first complete header per sheet. A line break within
one cell remains part of an exact name; headers spanning physical rows are not
inferred. Repeated header text in selected columns is skipped. Use explicit
`source` bindings for real data containing exactly those texts or for other layouts.

REVIEWED in full and modified: `_models.py`, `datasift-core/src/filter.rs`,
`datasift-core/src/xlsx.rs`, `tests/test_auto_headers.py`, `tests/test_all_sheets.py`,
`tests/test_contract.py`, `tests/test_header_indexing.py`, `tests/test_engine.py`,
`tests/test_cli.py`, `tests/test_sources.py`, README.md, CHANGELOG.md,
docs/contract.md and this report. REVIEWED, direct consumers unchanged: `_reader.py`,
`__main__.py`, `datasift-core/src/lib.rs`, `datasift-core/src/value.rs`, `scripts/bench.py`.
REVIEWED, unchanged: build configuration, lockfiles, workflows, public exports and
versioned examples. No cross-repository consumer changes. User files remain
unversioned and are not uploaded as fixtures/artifacts. `header_row` was removed
from local mask `examples/filter_schmutzig.json`; local output was regenerated
through the requested CLI path.

Final local checks, exit 0: Ruff check/format, mypy (5 files), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 passed),
pytest --cov (120 passed, 99.54% Python coverage), Maturin wheel/sdist, Twine,
`git diff --check`. Isolated wheel installations on Python 3.13/3.14: 120 tests
passed each. The sdist uses versioned sources plus the new synthetic test only;
no local user files. Regressions cover headers starting at row 7, shifted columns,
cell line breaks, preceding titles/numbers/partial headers, comments between
header/data, repeated headers, unused collisions and corrupt unrelated values
after detection, batch sizes 1/2/1024 and replay.
Actual CLI: exit 0, still 2 matches with exactly 3 mask columns, identical to the
previous output's projection; input hash unchanged.

Verdict: UNDETERMINED for overall approval; local implementation verified,
independent review and remote CI UNVERIFIED.

TODO A01-Review: base as above, independently read the full diff of listed files.
Target: automatic unique schema resolution without unrelated columns in output.
Repeat `tests/test_auto_headers.py`, header/source/atomicity tests and README checks;
check missing/ambiguous headers, rejection of `header_row` and corrupt selected
values. Acceptance: no open data-integrity finding, identical results across
replay/batch variants. Dependency: independent reviewer. Consumer impact: documented
new header/projection contract; no consumer integration claim.

TODO A01-CI: same base/files. User checks regular CI at final PR HEAD; no manual
triggering/polling by the agent. Acceptance: configured lint/type/test/build checks,
including negative/replay tests, pass. Dependency: runner toolchain. Consumer impact:
supported platforms remain UNVERIFIED until remote evidence is available.

## Addendum L01 — Excel line endings

Snapshot 2026-10-31, repository `chooong.datasift`, branch `feat/datasift-package`,
base `70f88e332228fe5935ab4a74c8e768914d98ebac`, existing PR #1.
Exact diff after commit: `git diff 70f88e3...feat/datasift-package`.

L01 (P1, independent closure pending): after saving in Excel, sharedStrings.xml
headers contained literal CRLF instead of LF. The reader kept raw bytes while the
mask used LF, so discovery found no complete schema. Invariant: XML-compliant line
endings change neither header mapping nor text filtering. Both XML input paths
use existing Quick-XML `xml10_content()` before the shared text helper appends content.
Solution ladder: existing library function; no custom replacement heuristic or
new dependency. Explicit character references are resolved separately and retain
the referenced character. No blanket trimming.

REVIEWED in full and modified: datasift-core/src/xlsx.rs, tests/test_xml_line_endings.py,
README.md, CHANGELOG.md, docs/contract.md and this report. Direct consumers:
shared strings, worksheet text/CDATA, header resolution in datasift-core/src/filter.rs
and Python/CLI output; existing tests remain relevant. Models, datasift-core/src/lib.rs,
workflows, lockfiles and build configuration unchanged. No external consumer changes.
Existing local deletions under rust_xlsx_filter are the user's and excluded from
this commit. Excel, local mask and NDJSON remain unversioned; user files are not packaged.

Final local checks, exit 0: Ruff check/format, mypy (5 files), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 passed),
pytest --cov (130 passed, 99.54% Python coverage), Maturin wheel/sdist, Twine and
`git diff --check`. Wheel tests on Python 3.13/3.14: 130 passed each. Regressions
cover LF, CRLF and CR in shared strings, inline strings and CDATA for headers/data;
replay and unchanged input are checked. Negative counterexample: explicit `&#13;`
remains CR. Actual requested CLI: exit 0, four matches with three mask columns,
input hash and mask unchanged. Two matching sheets contain two matches each;
`sheet: null` intentionally does not deduplicate them.

Verdict: UNDETERMINED for overall approval; verified locally;
independent review and remote CI UNVERIFIED.

TODO L01-Review: base/files as above. Independently read the full diff, especially
text/CDATA before character-reference resolution. Target: identical results across
all three XML line endings without changing explicit character references.
Verification: repeat tests/test_xml_line_endings.py and README checks, including
negative/replay cases. Acceptance: no open data-correctness findings. Dependency:
independent reviewer. Consumer impact: XML line endings in headers/text become LF;
character references retain their values.

TODO L01-CI: same base/files; user checks regular CI at final PR HEAD; no manual
triggering/polling by the agent. Acceptance: configured test/type/lint/build checks
pass, including line-ending/character-reference/replay tests. Dependency: runner
toolchain. Consumer impact: other platforms remain UNVERIFIED until remote evidence.

## Addendum N01 — module names and absolute imports

Snapshot 2026-10-31, `chooong.datasift`, branch `feat/datasift-package`, base
`d3818a32c3724c56aa5a42c5f6b46158feb030a1`, existing PR #1.
Exact diff after commit: `git diff d3818a3...feat/datasift-package`.

N01 (P2, independent closure pending): `_models.py`, `_reader.py` and `_rust.pyi`
are now named `models.py`, `reader.py`, `rust.pyi`. The native extension consistently
uses `chooong.datasift.rust` in Maturin, Cargo and PyO3. Existing modules were renamed;
no compatibility wrappers or additional dependencies. All Python imports are absolute.
The user's stricter Ruff rules (`TID252`, `ban-relative-imports = "all"`) are retained
unchanged and pushed with this change. `__init__.py` and `__main__.py` keep standard
Python names for exports and `python -m chooong.datasift`.

Invariants: public exports and CLI unchanged; no changes to filter semantics,
mask format or output. The wheel contains only new implementation names and the
matching native initializer, without old `_rust` stubs/binaries. Earlier implementation
imports were not a guaranteed contract and receive no redirects.

REVIEWED in full and modified: `src/chooong/datasift/models.py`, `reader.py`,
`rust.pyi`, `__init__.py`, `__main__.py`, `datasift-core/src/lib.rs`, `datasift-core/Cargo.toml`,
`pyproject.toml`, README.md, CHANGELOG.md, docs/contract.md and this report.
REVIEWED, direct consumers: all existing Python tests, `scripts/bench.py` and CLI
entry point; no changes needed outside package wiring. REVIEWED, unchanged:
lockfiles, workflows and Pre-Commit configuration. Existing user deletions under
`rust_xlsx_filter` remain unstaged; local Excel files and masks remain unversioned.
No cross-repository change.

Final local checks, exit 0: Ruff check/format with new user rules, mypy (5 files),
pytest --cov (130 passed, 99.54% Python coverage), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 passed),
Maturin wheel/sdist, Twine and `git diff --check`. Isolated wheel tests on Python
3.13/3.14: 130 passed each. Artifact inventory checks new module/stub names and
absence of old names/local user data. Native module mapping and CLI startup are
checked against the installed wheel. The sdist uses a targeted copy of versioned
sources, including renamed modules; no unversioned user examples.

Verdict: UNDETERMINED for overall approval; verified locally;
independent review and remote CI UNVERIFIED.

TODO N01-Review: base/files as above. Independently review the full diff, including
user Ruff rules, exports and Maturin/Cargo/PyO3 names. Target: no old implementation
files in artifacts, no relative imports, unchanged public import/CLI paths.
Repeat README checks, installed-wheel tests including existing negative/replay
cases and CLI startup. Acceptance: no open import/build/contract findings.
Dependency: independent reviewer. Consumer impact: public exports remain stable;
direct implementation imports remain outside the guaranteed API.

TODO N01-CI: same base/files; user checks regular CI at final PR HEAD, no manual
triggering/polling by the agent. Acceptance: configured Python/Rust/artifact checks,
including strict import rules and existing negative/replay tests, pass. Dependency:
runner toolchain. Consumer impact: other platforms remain UNVERIFIED until remote evidence.

## Addendum P01 — remaining user changes

Snapshot 2026-10-31, `chooong.datasift`, branch `feat/datasift-package`, base
`a847719fa05cab14215bf30217de64075f711339`, existing PR #1.
Exact diff after commit: `git diff a847719...feat/datasift-package`.
This addendum supersedes older statements about a PoC present in the checkout.

P01 (P2, independent closure pending): requested user changes adopted: `.data/`
is ignored, `examples/filter_schmutzig.json` is versioned as an example mask and
historical directory `rust_xlsx_filter/` is removed. Its Python/Rust files,
manifests, README, example and benchmark are not consumers of the current build.
Git history is preserved. README/contract describe the current state; the obsolete
Pre-Commit exclusion for the removed directory is dropped. No runtime code, filter
format, public import or CLI path changed; no new dependency or version.

REVIEWED: .gitignore, new example mask, all twelve specifically removed PoC files
and their exclusion from the current build, .pre-commit-config.yaml, README.md,
CHANGELOG.md, docs/contract.md and this report. Current Python/Rust sources,
pyproject.toml, workflows, lockfiles and direct consumers unchanged. Historical
reports remain historical snapshots. No Excel/NDJSON files or local `.data/`
contents are versioned or packaged.

Final local checks, exit 0: Ruff check/format, mypy (5 files), pytest --cov
(130 passed, 99.54% Python coverage), `pre-commit validate-config`, Pydantic
validation of all three example masks, Maturin wheel/sdist, Twine and
`git diff --check`. Artifact inventory confirms the new mask in the sdist,
without PoC or local example data.

Verdict: UNDETERMINED for overall approval; local checks available,
independent review and remote CI UNVERIFIED.

TODO P01-Review: base/files as above. Reviewer checks the complete diff, especially
unintended deletions outside the PoC, example-mask validity, ignore rules and current
docs. Target: current package/public paths unchanged; no private example data in
commits/artifacts. Repeat existing contract/negative/replay tests and README checks.
Acceptance: no open data/build/contract findings. Dependency: independent reviewer.
Consumer impact: historical PoC removed, which was already outside the guaranteed
API; current import/mask contract remains stable.

TODO P01-CI: same base/files; user checks regular CI at final PR HEAD. No manual
triggering/polling by the agent. Acceptance: configured Python/Rust/artifact checks,
including existing negative/replay tests, pass. Dependency: runner toolchain.
Consumer impact: remote build remains UNVERIFIED until this evidence is available.

## Addendum M01 — multiple tables per worksheet

Snapshot 2026-10-31, `chooong.datasift`, branch `feat/datasift-package`, base
`c4d8e2b2c7e6d34daa915446b4b5d3e135c66b46`, existing PR #1.
Exact diff after commit: `git diff c4d8e2b...feat/datasift-package`.
This addendum supersedes older statements limiting detection to one header per sheet.

M01 (P1, independent closure pending): previous discovery missed tables beside/below
the first region; identical names across adjacent tables were incorrectly indexed
globally. Shared header resolution now detects multiple complete groups of identical
mask columns within a row. A single row schema retains existing indexing/collision
semantics. Each column region has its own compiled filter/bindings. New overlapping
headers replace the old region; independent neighbors continue. Solution ladder:
extend the existing streaming reader and header/filter compiler; no second parser,
additional dependency or artificial API.

Invariants: no mixing of neighboring table values, no duplicate evaluation of
replaced regions; workbook/row/left-column order. Only mask columns are exposed,
without table metadata. Existing batches are flushed before changing output-column
order; projected values match the current Ready schema. Corrupt selected values
and XML remain errors; late errors preserve CLI output. Explicit `source` boundaries,
batch sizes and replay remain stable. Active regions do not overlap.

The documented limit remains deliberate: horizontal splitting requires at least
two complete identical mask schemas with at least two distinct mask columns.
Single repeated names, partial schemas and horizontal tables with internally indexed
mask names are not inferred; use explicit sources. Headers spanning physical rows
are not reconstructed. Outside active columns, only valid text header candidates
are considered; invalid unselected values are still not extracted. No mask-format
change, new version or publication.

REVIEWED in full and modified: datasift-core/src/filter.rs (schema resolution and
mask-derived header candidates), datasift-core/src/xlsx.rs (active tables, cell
selection, projection, batch boundaries), tests/test_multiple_tables.py, README.md,
CHANGELOG.md, docs/contract.md and this report. REVIEWED, direct consumers unchanged:
datasift-core/src/lib.rs (Ready/Batch), Python reader, CLI and benchmark; existing
contract/header/source/line-ending tests remain relevant. Models, workflows and
lockfiles unchanged. The user's concurrent comment translation in pyproject.toml
remains unstaged; no Ruff rule changed. User files and `treffer.ndjson` remain unversioned.

Final local checks, exit 0: Ruff check/format, mypy (5 files), cargo fmt,
Clippy `--locked --offline --all-targets -- -D warnings`, cargo test (8 passed),
pytest --cov (147 passed, 99.54% Python coverage), Maturin wheel/sdist, Twine,
`git diff --check`. Isolated wheels on Python 3.13/3.14: 147 passed each. Artifacts
contain no local Excel/NDJSON files or `.data/` contents. Synthetic regressions
cover five tables on two sheets, identical/reordered columns, horizontal/vertical/
shifted headers, headers beside data, shared-string headers outside prior bindings,
independent predicates, late corrupt values, batch sizes 1/2/3/1024 and replay.
Existing indices/collisions remain checked. The existing benchmark reads 250000
rows and correctly yields 12500 matches; no cross-platform performance/RAM claim
follows from this local run.

Actual requested CLI: exit 0, ten records with exactly three mask columns, Excel
hash and mask unchanged. As a multiset, results exactly match five separate scans
with explicit column/row boundaries: four tables with two matches each on one
sheet and one table with two matches on another. No blanket expected counter or
duplicated result records in code.

Verdict: UNDETERMINED for overall approval; verified locally;
independent review and remote CI UNVERIFIED.

TODO M01-Review: base/files as above. Independently check the full diff, especially
splitting complete schemas, overlap rules, compact projection and Ready/Batch order.
Repeat README commands and `tests/test_multiple_tables.py`, including negative/
replay/atomicity cases. Target: all ten synthetic matches without mixing or extra
matches, unchanged explicit sources and index semantics. Acceptance: no open
data-correctness/lifecycle findings. Dependency: independent reviewer. Consumer
impact: additional matching tables produce additional records; mask format and
public import/CLI paths remain unchanged.

TODO M01-CI: same base/files; user checks regular CI at final PR HEAD. No manual
triggering/polling by the agent. Acceptance: configured Python/Rust/artifact checks,
including existing/new negative/replay tests, pass. Dependency: runner toolchain.
Consumer impact: other platforms remain UNVERIFIED until remote evidence is available.
