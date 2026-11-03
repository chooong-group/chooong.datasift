# CSV input

CSV uses the same rules and column mapping as Excel. Cells initially contain
text or null, so enable conversion before numeric comparisons. Row numbers count
logical records from 1, including headers; an embedded newline does not add a row.
CSV event metadata uses worksheet name `csv`.

## Automatic table discovery

Both [discovery modes](automatic-table-discovery.md) work on CSV records, including
headers after a preamble and several table regions. Start with the
[standalone Free Discovery example](complex-layouts.md#automatic-csv-example);
use [anchors for text-only tables](complex-layouts.md#text-only-data-and-comments).
Automatic table detection does not detect delimiter or encoding: defaults are
comma and UTF-8. Configure other formats explicitly as below.

## Delimiters and types

Create `sales.csv`:

```csv
ID;Amount;Country
a;1200;DE
b;900;AT
```

```python
from chooong.datasift import iter_matching_rows

mask = {
    "sheet": None,
    "csv": {"delimiter": ";", "encoding": "utf-8"},
    "header": {"anchors": ["ID", "Amount", "Country"]},
    "types": {"Amount": {"type": "integer", "convert": True}},
    "where": {"column": "Amount", "op": "gte", "value": 1000},
    "select": ["ID", "Amount"],
}
assert [dict(row) for row in iter_matching_rows("sales.csv", mask)] == [
    {"ID": "a", "Amount": 1200}
]
```

`csv.encoding` accepts encoding_rs labels, including `utf-8`, `utf-16le` and
`windows-1252`. The decoder removes BOMs and rejects malformed sequences.
Quoted delimiters, doubled quotes and embedded newlines are supported.
Delimiter and quote must be distinct single ASCII characters.

## Headerless records

Create `raw.csv`:

```csv
a,1200
b,900
```

```python
mask = {
    "sheet": None,
    "csv": {"header": False},
    "source": {
        "columns": [{"name": "ID", "column": "A"}, {"name": "Amount", "column": "B"}],
        "data_start_row": 1,
    },
    "types": {"Amount": {"type": "integer", "convert": True}},
}
assert [dict(row) for row in iter_matching_rows("raw.csv", mask)] == [
    {"ID": "a", "Amount": 1200}, {"ID": "b", "Amount": 900}
]
```

`csv.header=False` requires a `source` or `sources` declaration. The native
check does not require column-binding mode: a header-bound source is also accepted.
It does not otherwise change the shared discovery pipeline: with headers enabled,
a source still sets its own start row; `header=True` does not blindly discard
record 1. CSV input has a u32 logical record counter; explicit source bounds use
Excel-compatible row limits. All exact fields/defaults are in
[filter models](../api/filters.md#csvconfig).

A header-bound source still reads its declared header even when `header=False`:

```python
mask = {
    "sheet": None,
    "csv": {"header": False, "delimiter": ";"},
    "source": {"header_start_row": 1, "data_start_row": 2},
}
assert next(iter_matching_rows("sales.csv", mask))["ID"] == "a"
```

## Encoding, quoting and multiline fields

This standalone example creates a UTF-16 file with a BOM, semicolon delimiters,
an embedded newline, a quoted delimiter and doubled quotes. Delimiter and encoding
are configured explicitly; neither is sniffed from the input.

```python
from pathlib import Path

from chooong.datasift import CsvConfig, FilterMask, HeaderConfig, scan_batches

Path("quoted.csv").write_bytes(
    'ID;Note\na;"Café\nNorth; say ""hello"""\nb;plain\n'.encode("utf-16")
)
mask = FilterMask(
    sheet=None,
    csv=CsvConfig(encoding="utf-16le", delimiter=";"),
    header=HeaderConfig(anchors=("ID", "Note")),
)
with scan_batches("quoted.csv", mask) as scan:
    records = [record for batch in scan for record in batch]
    statistics = scan.statistics
assert [(record.row, record.values) for record in records] == [
    (2, {"ID": "a", "Note": 'Café\nNorth; say "hello"'}),
    (3, {"ID": "b", "Note": "plain"}),
]
assert statistics is not None and statistics.complete
```

The embedded newline belongs to record 2, not a new logical record. Malformed
encoding is an error; replacement characters are not silently inserted. Completely
blank lines are skipped by the CSV parser, so use explicit empty fields such as
`,,,` (with comma delimiters) for Free Discovery region boundaries.
