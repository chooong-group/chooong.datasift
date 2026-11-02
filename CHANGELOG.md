# Changelog

## Unreleased

## 0.1.0

### Added

- Streaming XLSX/XLSM and CSV input with deterministic multi-file/glob ordering.
- Automatic table discovery, worksheet selection, repeated/normalized headers,
  adjacent and stacked tables, explicit column bindings and source windows.
- Composable filters, ordered projection, required/default/type rules and
  explicit row classification, with exact Decimal, Money and temporal values.
- Typed Python models, immutable matching rows, closeable batches and ordered
  matched/rejected records with source metadata, reasons and scan statistics.
- Native NDJSON/Parquet export and CLI, with staged output, journaled commit and
  recovery bound to caller destinations and an independently trusted journal hash.
- CPython 3.12–3.14 support using a native Python 3.12 stable ABI extension.

### Fixed

- Accept equivalent absolute Windows parent paths when validating recovery journals.
