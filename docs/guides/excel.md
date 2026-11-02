# Excel workbooks

Pass an XLSX/XLSM path with a nonblank worksheet name, or `sheet=None` for all
worksheets. All-sheet scans follow workbook order, including hidden worksheets;
chart sheets without worksheet rows are skipped. The string `"null"` selects a
worksheet literally named null. XLS, XLSB and encrypted files are unsupported.

## Automatic table discovery

Both [Named-column and Free Discovery](automatic-table-discovery.md) support
XLSX/XLSM. Use names from anchors or filters when the schema is known; use Free
Discovery when each candidate has structural confirmation. The
[complete Excel example](complex-layouts.md#automatic-excel-example) creates its
own workbook and finds adjacent and shifted tables without coordinates in the mask.

## Tables outside A1

Create `offset.xlsx`, sheet `Data`, with the following cells. The first three
rows and first two columns are blank. The two tables start at C4 and F4.
This CSV representation shows the complete worksheet, including blank positions:

<!-- workbook: offset.xlsx -->

```csv
,,,,,,
,,,,,,
,,,,,,
,,Country,Amount,,Country,Amount
,,DE,1500,,DE,2400
,,AT,2000,,DE,900
```

```python
from chooong.datasift import iter_matching_rows

mask = {
    "sheet": "Data",
    "where": {"all": [
        {"column": "Country", "op": "eq", "value": "DE"},
        {"column": "Amount", "op": "gte", "value": 1000},
    ]},
}
assert [dict(row) for row in iter_matching_rows("offset.xlsx", mask)] == [
    {"Country": "DE", "Amount": 1500},
    {"Country": "DE", "Amount": 2400},
]
```

The complete Country/Amount groups identify two independent tables.
[Table discovery](../concepts/table-discovery.md) defines adjacent/stacked tables,
repeated names, ambiguity and ordering. Use
[anchors and row rules](complex-layouts.md#text-only-data-and-comments) for text-only
data and known comments; reserve
[sources](complex-layouts.md#manual-fallback-with-tablesource) for boundaries that
automatic discovery cannot establish.

## Text and formulas

A line break within a cell is part of its header name. Literal XML CRLF/CR is
normalized to LF in shared strings, inline strings and CDATA. Explicit character
references retain the referenced character. No implicit trimming occurs.
`header.rows` handles physical multiline headers; see [complex layouts](complex-layouts.md).

Formulas are not calculated. Cached values are read; missing caches yield null.
Macros and external links are not executed. Selected external worksheet relationships
are rejected. Numeric styles and date systems are used only through configured
[type rules](../concepts/data-types.md). Missing worksheet rows are not synthesized.
