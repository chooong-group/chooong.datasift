# DataSift

Extract, validate and filter tables from XLSX, XLSM and CSV using a JSON mask.
Rust reads rows and writes exports; Python validates masks and exposes typed results.
No database or external service is required.

Start with [installation](installation.md) and the [quickstart](quickstart.md).
Then choose a guide for [Excel](guides/excel.md), [CSV](guides/csv.md),
[complex layouts](guides/complex-layouts.md), [validation](guides/validation.md)
or [exporting](guides/exporting.md).

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
