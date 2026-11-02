# Complex layouts

Use explicit sources to separate neighboring tables and exclude known comments
without inferring their meaning. Each source has independent bounds; optional
per-source rules replace the shared rules rather than merge with them.

## Known columns and rows

Create `layout.xlsx`, sheet `Data`, with these worksheet positions:

<!-- workbook: layout.xlsx -->

```csv
,,Customer,Amount,Previous,,Customer,Amount
,,Name,Current,Prior,,Name,Current
,,Comment before data,,,,,
,,one,120,80,,neighbor,999
,,ignore,1000,1000,,ignore,1000
,,two,200,180,,other,250
```

```python
from chooong.datasift import ColumnBinding, FilterMask, TableSource, iter_matching_rows

mask = FilterMask(
    sheet="Data",
    source=TableSource(
        columns=(
            ColumnBinding(name="Customer", column="C"),
            ColumnBinding(name="Amount", column="D"),
        ),
        data_start_row=4,
        data_end_row=6,
        skip_rows=(5,),
    ),
)
assert [dict(row) for row in iter_matching_rows("layout.xlsx", mask)] == [
    {"Customer": "one", "Amount": 120},
    {"Customer": "two", "Amount": 200},
]
```

Headers and unrelated columns are not interpreted in this mode. Alias names
are unique; two aliases may bind one physical column. Boundaries and collision
rules are defined in [column mapping](../concepts/column-mapping.md).

## Known header windows

Bind the first two physical header rows instead of assigning aliases:

```python
mask = {
    "sheet": "Data",
    "source": {
        "header_start_row": 1,
        "first_column": "C",
        "last_column": "E",
        "data_start_row": 4,
        "data_end_row": 6,
        "skip_rows": [5],
    },
    "header": {"rows": 2},
}
assert [dict(row) for row in iter_matching_rows("layout.xlsx", mask)] == [
    {"Customer Name": "one", "Amount Current": 120, "Previous Prior": 80},
    {"Customer Name": "two", "Amount Current": 200, "Previous Prior": 180},
]
```

`header.merged_fill=True` fills actual OOXML merged ranges from their top-left
cell; it does not guess missing labels. This requires a streaming metadata pass
before reading data. Use `sources` for several windows and a source `sheet`
restriction where needed. Explicit overlaps emit once per source, in declaration
order; automatic regions instead remain non-overlapping.

Comments, totals and separators inside data bounds need explicit
[row classification](validation.md#row-classification) or predicates. Corrupt
selected values and structural XML errors remain errors even with explicit bounds.
