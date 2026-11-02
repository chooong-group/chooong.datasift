# CSV input

CSV uses the same rules and column mapping as Excel. Cells initially contain
text or null, so enable conversion before numeric comparisons. Row numbers count
logical records from 1, including headers; an embedded newline does not add a row.
CSV event metadata uses worksheet name `csv`.

## Delimiters and types

Create `sales.csv`:

<!-- file: sales.csv -->

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

<!-- file: raw.csv -->

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
