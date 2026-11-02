# Changelog

## Unreleased

### Added

- Native CSV input, deterministic multi-file scanning, optional predicates,
  independent discovery anchors and ordered literal/regex/wildcard projection.
- Required/default/type rules, exact Decimal/Money and temporal conversions,
  configurable headers, multiple sources and explicit row classification.
- One-pass matched/rejected streaming, source metadata, explain/statistics,
  native NDJSON/Parquet exports and journaled two-file commit/recovery.

- English README and MkDocs documentation, contribution guide and issue/PR templates.
- Native five-platform ABI3 wheel matrix, source-distribution installation checks,
  checksum-bound fixture evidence and a complete-set release gate. Remote platform
  validation remains a release blocker until actually executed.
- A shared dry-run/release build path and an OIDC publishing job that is hard-disabled
  pending independent review, owner approval and external PyPI/GitHub configuration.
- Strict documentation checks and a disabled, manually activated Pages workflow.
- A synthetic quickstart workbook generator with adjacent offset tables and comment rows; existing files are never overwritten.
- Automatic discovery of multiple complete table schemas per worksheet, including
  adjacent and vertically offset areas, with independent predicates and row-ordered output.
- Example masks for explicit layouts and multiline cell labels.
- `sheet: null` scans all worksheets in workbook order, with whole-scan atomic CLI output.
- Repeated headers receive indices such as `Amount_1` and `Amount_2`;
  unique names stay unchanged and selected collisions fail.
- `TableSource` / `ColumnBinding` support explicit columns, data bounds and skipped rows.
- Installable `chooong.datasift`, typed filter models, immutable rows, closeable batches
  and the `chooong-datasift` NDJSON CLI.

### Changed

- **Breaking change:** `recover_export` requires a separately trusted
  `journal_sha256` and an explicit `rejected_output` for two-file recovery.
  Untrusted journals no longer authorize destination paths.
- Schema failures now quarantine affected tables, continue independent tables,
  and finish both iterator APIs with `SCHEMA_MISMATCH` and `complete=false`.
  Exports preserve both prior outputs after any schema error.
- Free discovery uses the same bounded confirmation rule for every region;
  ambiguous text layouts require anchors or explicit sources. Comment, total
  and separator classification is explicitly configuration driven.

- Consolidated user documentation into six guides; moved release instructions to
  `.github/RELEASING.md` and validation reports to the PR.

- Benchmark defaults to 2,000,000 rows across Excel-compliant worksheets.
- Local example workbooks live under `examples/` and remain excluded from Git and distributions; the large-workbook JSON mask is retained.
- CI uses read-only GitHub-hosted standard runners; private-repository compute is
  blocked rather than silently permitting charges. Actions, uv, Rust and Maturin
  are pinned; Python/Cargo dependencies are locked.
- Public metadata, project URLs and distribution inventories are checked.
- Implementation modules are `models`, `reader` and `rust`; imports are absolute.
- **Breaking change:** automatic header discovery removed
  `header_row`. Masks must omit it; output/conversion include only names referenced
  by `where`, including with explicit source bindings.
- Public import path is `chooong.datasift`; results are immutable `Row` values.
  `rust_xlsx_filter` and `extract_rows` are not supported APIs.
- Python and Cargo metadata use the repository's Apache-2.0 license.

### Fixed

- Continue independent tables after projection, binding or normalization errors.
- Discover different adjacent/stacked free schemas and multiline headers with
  explicit diagnostics for ambiguous candidates.

- Use supported `uv run --no-sync` in native CI/release checks; retain dependency-only `uv sync --no-install-project`.

- XML line endings in shared/inline strings and CDATA are normalized, preserving
  multiline header matches after saving in Excel.
- Unselected fields and the earlier local `__column_*` extras are not extracted.
- Native receiver thread safety, truncated-XML detection and protection against
  overwriting the input/mask with CLI output.
- Invalid duplicate build configuration and project-unrelated CI commands.

### Removed

- Automatic tag-triggered GitLab publishing and its CI-run polling. No replacement
  upload or deployment is enabled by this preparation.
- Historical `rust_xlsx_filter/` PoC; implementation lives in `src/chooong/datasift`
  and `native`, with earlier code retained in Git history.

### Security

- Bind recovery to caller destinations and a trusted journal digest; reject
  symlinks, hardlinks and special files. Pin directory/file handles, verify
  private snapshots, and recheck target, lock and journal changes before commit.
  Output directories must remain protected from untrusted concurrent writers.
