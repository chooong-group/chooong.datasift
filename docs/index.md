# DataSift

Automatically discover, validate and filter tables in XLSX, XLSM and CSV using
a JSON mask, including tables beside or below one another and headers outside A1.
Rust reads rows and writes exports; Python validates masks and exposes typed results.
No database or external service is required.

Start with [installation](installation.md) and the [quickstart](quickstart.md).
Then choose a guide for [Excel](guides/excel.md), [CSV](guides/csv.md),
[complex layouts](guides/complex-layouts.md), [validation](guides/validation.md)
or [exporting](guides/exporting.md).

## Find a workflow

| Task | Guide |
| --- | --- |
| Locate offset, adjacent or stacked tables | [Automatic table discovery](guides/automatic-table-discovery.md) |
| Handle comments, multiline headers or known source windows | [Complex layouts](guides/complex-layouts.md) |
| Combine AND/OR/NOT, regex and comparisons | [Advanced filtering](guides/advanced-filtering.md) |
| Select/reorder fields with names, wildcard or regex | [Column selection](guides/column-selection.md) |
| Apply different filters and rules per table | [Per-table rules](guides/complex-layouts.md#different-rules-per-table) |
| Inspect schemas, bindings, counts and rejects | [Table inspection and diagnostics](guides/table-inspection.md) |
| Process large inputs incrementally and close iterators | [Batch processing](guides/batch-processing.md) |
| Convert exact money, decimals and dates | [Validation](guides/validation.md) |
| Continue across file errors and handle partial results | [Error handling](guides/error-handling.md) |
| Write NDJSON/Parquet and understand commit/recovery | [Exporting](guides/exporting.md) |
| Choose batch sizes and understand memory use | [Performance and resources](guides/performance.md) |

Automatic table discovery is structural, not arbitrary layout understanding.
Named-column Discovery uses anchors or filter names; Free Discovery needs scalar
evidence after each header. CSV delimiters and encodings are configured, not
sniffed. Text-only tables and comments need explicit names/rules or source windows.

## How a scan works

A scan discovers or binds columns, classifies rows, applies defaults and explicit
type conversions, validates values, evaluates the filter, then projects matches.
[Filters](concepts/filters.md) explains that order. Use matching iterators for
values, or an event iterator for both matches and rejected original records.

Tables may start away from A1 and appear beside or below other tables.
Automatic discovery needs structural evidence; text-only or ambiguous layouts
need [anchors or explicit sources](concepts/table-discovery.md).

## Reference

- [Python API](api/python.md): supported imports, signatures and result models.
- [Filter models](api/filters.md): mask fields and every operator.
- [JSON Schema](api/json-schema.md): generate schemas from the canonical models.
- [CLI](api/cli.md): arguments, output and exit behavior.
- [Limits](reference/limits.md), [errors](reference/errors.md) and
  [file safety](reference/file-safety.md): constraints and failure handling.

DataSift does not read XLS/XLSB or encrypted workbooks, calculate formulas or write
Excel files. It reads cached formula results. Rows stream, but shared strings,
metadata and batches still require memory. See [streaming](concepts/streaming.md).

Developers can start with [architecture](development/architecture.md),
[contributing](development/contributing.md) and [benchmarks](development/benchmarks.md).
