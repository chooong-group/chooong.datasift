# Automatic table discovery

Discover tables in XLSX/XLSM and CSV without fixed header rows, start positions
or column coordinates. The same discovery engine serves both formats; Excel
supplies native cell values, while CSV initially supplies text or null.

## Start with the data you know

- **Known column names:** use Named-column Discovery with `header.anchors`.
  With no anchors, column names anywhere in `where` locate the schema instead.
  Follow the [standalone Excel example](complex-layouts.md#automatic-excel-example).
- **Unknown column names:** omit anchors, `where` and explicit sources to use
  Free Discovery. Each candidate needs a confirming data record immediately after
  its configured header rows. Follow the
  [standalone CSV example](complex-layouts.md#automatic-csv-example).
- **Text-only data or comments:** use
  [anchors and explicit row classification](complex-layouts.md#text-only-data-and-comments).
  Free Discovery cannot infer business meaning from text.
- **Known boundaries that discovery cannot establish:** use the
  [manual TableSource fallback](complex-layouts.md#manual-fallback-with-tablesource).
  Per-source `rules` can then apply different filters and validation to each table.

Automatic CSV table discovery does not detect delimiters or encodings. Set
`csv.delimiter` and `csv.encoding` when the comma/UTF-8 defaults do not apply;
see [CSV input](csv.md).

## Check the whole scan

The [layout comparison](complex-layouts.md#supported-layouts-and-limits) describes
adjacent/stacked regions, blank records, multiline headers and ambiguities.
The [discovery contract](../concepts/table-discovery.md) defines exact matching,
normalization, duplicate names and output order.

Inspect actual discovered schemas and bindings with
[Table inspection and diagnostics](table-inspection.md). An early match does not
certify the complete scan: ambiguous regions can fail after independent regions
have yielded records. [Error handling](error-handling.md) demonstrates this
with incomplete statistics and explains why partial results need explicit handling.
