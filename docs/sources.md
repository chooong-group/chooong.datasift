# Explicit Table Sources

Use `TableSource` when automatic detection cannot distinguish your layout, or
when data boundaries and comment rows are known. Names are aliases bound to
absolute Excel columns; header text is not interpreted.

```json
{
  "sheet": "Data",
  "source": {
    "columns": [
      {"name": "Country", "column": "C"},
      {"name": "Amount", "column": "E"}
    ],
    "data_start_row": 7,
    "data_end_row": 20,
    "skip_rows": [8]
  },
  "where": {
    "all": [
      {"column": "Country", "op": "eq", "value": "DE"},
      {"column": "Amount", "op": "gte", "value": 1000}
    ]
  }
}
```

This reads only C/E from rows 7 through 20 inclusive, excluding row 8. Names in
`source.columns` must be nonempty and unique. Columns are uppercase A..XFD.
Multiple aliases may intentionally reference the same physical column. Only
aliases used by `where` are returned, in binding order; unknown filter aliases fail.

`data_start_row` is required. `data_end_row` is optional; without it, the rest of
the worksheet is selected. All row indices are 1..1048576. `skip_rows` must fall
inside that interval. No header-setting field is accepted.

For `sheet: null`, these **same** absolute bindings/ranges apply on each worksheet.
One explicit source selects one range; use separate masks for several explicit
regions. Values outside the selected scope are not converted or returned, while
XML structure, coordinates and limits are still checked throughout the worksheet.
A broken XML tail remains an error even after `data_end_row`.
