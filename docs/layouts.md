# Excel Layouts

## Worksheets

A nonblank `sheet` string selects one worksheet; `null` scans all worksheets,
including hidden ones, in workbook order. The string `"null"` names a worksheet.
Chart sheets without worksheet rows are skipped.

A named sheet without a complete schema raises `ValueError`. With `sheet: null`,
unmatched worksheets contribute no rows; no matching schema anywhere means an
empty result. Explicit bindings apply unchanged on each selected worksheet.

## Automatic headers

Without `source`, DataSift searches for a row containing every name referenced by
`where`. Only text cells are header labels. Titles and incomplete rows do not
define a table. No `header_row` setting is accepted.

Names match exactly: no trimming or case folding. A line break inside one cell
is part of the name, for example `"Amount\nEUR"`. Literal XML CRLF/CR becomes LF
in shared strings, inline strings and CDATA; character references preserve their
referenced character. Headers spread over several physical rows and merged cells
are not reconstructed; use explicit bindings for those layouts.

Within one schema, duplicate labels receive indices from left to right:
`Amount`, `Amount` become `Amount_1`, `Amount_2`; unique names stay unchanged.
Use indexed names in the mask. The ambiguous base name and selected collisions
with an existing suffix label are rejected. Blank cells do not affect numbering.

## Multiple tables

A header row with at least two complete groups of the mask's literal names
identifies adjacent tables. Each group contains every referenced name once;
at least two distinct mask columns are needed. For example, the
[quickstart](index.md) selects `Country` and `Amount` from both C/D and H/I.
A repeated single name alone cannot distinguish adjacent tables from duplicate
columns. Partial groups or horizontal groups using indexed names may require
explicit bindings.

A later complete header replaces active tables whose intervals from first to
last selected column overlap it. Other neighboring tables continue, including
records on the same row as a new header. Blank rows and comments do not end a
table. Output follows worksheet order, row number, then leftmost selected column.

A complete header is structural, not a record for the table it starts. Records
identical to all selected header labels are indistinguishable in automatic mode;
use explicit bounds. Comments below a header are evaluated by `where`, just like
records. A comment that satisfies the predicate requires a stricter mask,
`skip_rows` or explicit bounds to exclude it.

## Explicit sources

Use `source` when positions are known or automatic discovery is ambiguous:

```json
{
  "sheet": "Data",
  "source": {
    "columns": [
      {"name": "Country", "column": "C"},
      {"name": "Amount", "column": "D"}
    ],
    "data_start_row": 5,
    "data_end_row": 7,
    "skip_rows": [5]
  },
  "where": {"column": "Amount", "op": "gte", "value": 1000}
}
```

On the quickstart workbook, this selects the first table, skips its comment and
returns amounts 1500 and 2000. Header text is not interpreted in this mode.

`ColumnBinding(name, column)` binds a nonblank, unique alias to an uppercase
absolute column A..XFD. Several aliases may refer to one physical column. There
must be 1..16384 bindings. Aliases referenced by the filter must exist in them;
[returned-column rules](contract.md#returned-columns) still apply.

`data_start_row` is required. `data_end_row` is optional and inclusive; omitting it
selects the remainder of the sheet. Row indices are 1..1048576, the end cannot
precede the start, and `skip_rows` must be inside those bounds. One source selects
one region; use separate masks for several explicit regions.

Values outside the selected scope are not converted. XML structure, coordinates
and resource limits are checked throughout the worksheet, even beyond the end
bound. A corrupt XML tail still fails the scan.
