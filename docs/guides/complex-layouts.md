# Complex layouts

Automatic table discovery works for XLSX/XLSM and CSV without header row numbers,
data start positions or column coordinates. Start with known column names when
available; use Free Discovery when the schema is unknown and the data provides
structural evidence. Reserve [explicit sources](#manual-fallback-with-tablesource)
for layouts that these modes cannot identify reliably.

## Choose a discovery mode

| Mode | Configuration without `source`/`sources` | Suitable input |
| --- | --- | --- |
| Named-column Discovery | `header.anchors`, or the names referenced by `where` if anchors are empty | Known schemas, including text-only data |
| Free Discovery | No anchors and no `where` | Unknown schemas with a confirming data record immediately after each header |

`select`, `types` and `required` do not choose Named-column Discovery. Anchors
identify the schema independently of filtering; `where` still filters data.
Without `select`, a mask with `where` returns only filter columns; a mask without
`where` returns all discovered columns. See [projection](../api/filters.md#projection).

## Automatic Excel example

Run this complete Python example after [installation](../installation.md).
It creates a small workbook using only the standard library, then discovers two
neighboring tables and a later shifted table. The blank cells and rows belong to
the sample input; the mask contains only column names. An existing XLSX/XLSM file
can be passed directly to the same reader.

```python
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from chooong.datasift import FilterMask, HeaderConfig, iter_matching_batches

# Build synthetic input; DataSift itself does not write Excel files.
worksheet_rows = (
    ("Sales report",),
    (),
    (None, None, "Customer", "Amount", None, "Customer", "Amount"),
    (None, None, "left", 120, None, "right", 240),
    (),
    (None, "Customer", "Amount"),
    (None, "later", 360),
)

def xml_cell(value: str | int | None) -> str:
    if value is None:
        return "<c/>"
    if isinstance(value, int):
        return f"<c><v>{value}</v></c>"
    return f'<c t="inlineStr"><is><t>{escape(value)}</t></is></c>'

sheet_data = "".join(
    "<row>" + "".join(xml_cell(value) for value in row) + "</row>"
    for row in worksheet_rows
)
main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
doc_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
path = Path("discovery.xlsx")
with ZipFile(path, "w") as book:
    book.writestr("[Content_Types].xml", (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/data.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    ))
    book.writestr("_rels/.rels", (
        f'<Relationships xmlns="{rel_ns}"><Relationship Id="root" '
        f'Type="{doc_rel_ns}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    ))
    book.writestr("xl/workbook.xml", (
        f'<workbook xmlns="{main_ns}" xmlns:r="{doc_rel_ns}">'
        '<sheets><sheet name="Data" sheetId="1" r:id="data"/></sheets></workbook>'
    ))
    book.writestr("xl/_rels/workbook.xml.rels", (
        f'<Relationships xmlns="{rel_ns}"><Relationship Id="data" '
        f'Type="{doc_rel_ns}/worksheet" Target="worksheets/data.xml"/></Relationships>'
    ))
    book.writestr("xl/worksheets/data.xml", (
        f'<worksheet xmlns="{main_ns}"><sheetData>{sheet_data}</sheetData></worksheet>'
    ))

mask = FilterMask(sheet="Data", header=HeaderConfig(anchors=("Customer", "Amount")))
with iter_matching_batches(path, mask) as scan:
    rows = [dict(row) for batch in scan for row in batch]
    statistics = scan.statistics
assert rows == [
    {"Customer": "left", "Amount": 120},
    {"Customer": "right", "Amount": 240},
    {"Customer": "later", "Amount": 360},
]
assert statistics is not None and statistics.complete
assert len(statistics.tables) == 3
```

This uses Named-column Discovery: each complete Customer/Amount header group
identifies a table. Blank rows do not close named tables; a later complete header
replaces overlapping column intervals. Independent neighbors continue. See
[Excel](excel.md) for worksheet selection, cached formulas and XLSM restrictions.

## Automatic CSV example

This standalone example uses Free Discovery. It finds different schemas beside
and below one another, including a table shifted away from the first field.
Each header is followed immediately by a record containing numeric text.

```python
from pathlib import Path

from chooong.datasift import FilterMask, iter_matching_batches

path = Path("discovery.csv")
path.write_text(
    "Sales report\n"
    ",Customer,Amount,,Code,Count\n"
    ",left,120,,right,2\n"
    ",,,,,\n"
    ",,City,Population\n"
    ",,Berlin,3\n",
    encoding="utf-8",
)
with iter_matching_batches(path, FilterMask(sheet=None)) as scan:
    rows = [dict(row) for batch in scan for row in batch]
    statistics = scan.statistics
assert rows == [
    {"Customer": "left", "Amount": "120"},
    {"Code": "right", "Count": "2"},
    {"City": "Berlin", "Population": "3"},
]
assert statistics is not None and statistics.complete
assert len(statistics.tables) == 3
```

Numeric text confirms structure but remains text. Use explicit `types` for
conversion. CSV defaults to comma, UTF-8 and double-quote quoting; delimiter
sniffing is not implemented. Set `csv=CsvConfig(delimiter=";")` for semicolons.
See [CSV](csv.md) for encoding, quoting and headerless records.

## Text-only data and comments

Use anchors for text-only tables. Comments and totals have no inferred business
meaning. In named mode, classify them with content-based row rules or filter
them with `where`; no physical row numbers are necessary:

```python
from pathlib import Path

from chooong.datasift import (
    FilterMask, HeaderConfig, Operator, RowClass, RowPolicy, RowRule,
    ScalarCondition, iter_matching_rows,
)

Path("people.csv").write_text(
    "People report\n,Name,State\n,Alice,Open\n,Comment,Review pending\n,Bob,Closed\n",
    encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("Name", "State")),
    row_policy=RowPolicy(rules=(RowRule(
        classification=RowClass.COMMENT,
        where=ScalarCondition(column="Name", op=Operator.EQ, value="Comment"),
    ),)),
)
assert [dict(row) for row in iter_matching_rows("people.csv", mask)] == [
    {"Name": "Alice", "State": "Open"},
    {"Name": "Bob", "State": "Closed"},
]
```

Free Discovery checks structure before row classification or filtering: an
unexpected all-text comment can quarantine a region even when a row rule would
exclude it. Use anchors or explicit sources in that case. See
[row classification](validation.md#row-classification).

## Supported layouts and limits

| Scenario | Named-column Discovery | Free Discovery |
| --- | --- | --- |
| Offset headers / leading titles | Finds complete required names without coordinates | Finds text runs; multi-cell text titles can themselves become ambiguous candidates |
| Adjacent tables | Requires complete repeated groups of at least two distinct names | Blank column gaps separate independently confirmed regions |
| Stacked / shifted tables | Later complete headers replace overlapping intervals | Empty records within a region close it; later candidates need fresh confirmation |
| Multiple physical header rows | Set `header.rows`; sliding window before the first table only | Set `header.rows`; each candidate collects that many consecutive all-text header rows |
| Blank records in data | Do not close a table; empty rows are excluded by default | Close a region; later data needs a new header |
| Comments / totals | Ordinary data unless excluded explicitly | No semantic detection; unexpected all-text rows are ambiguous |
| Purely textual data | Supported with anchors or filter column names | Cannot confirm a table without scalar evidence |
| Incomplete / ambiguous headers | Partial groups, repeated single names or adjacent indexed schemas need sources | Unconfirmed candidates, including at EOF, fail with diagnostics |

Header depth is configured, not inferred. `header.rows` joins physical header
lines with spaces; a newline inside one cell remains part of that label. Later
multiline headers in named mode are not reconstructed generally. For merged
Excel headers, `header.merged_fill=True` fills actual OOXML merged ranges only;
use [known header windows](#known-header-windows) for controlled boundaries.

Free Discovery defaults to `header.min_columns=2`. Confirmation requires the
immediately following physical record to contain a native non-text scalar,
finite numeric text, ISO date or ISO datetime. Blank CSV lines are skipped by
the parser; use an explicit empty-field record such as `,,,` to delimit regions.
Missing Excel row numbers are not synthesized as empty rows.

Ambiguous Free Discovery regions emit `AMBIGUOUS_HEADER` and `SCHEMA_MISMATCH`.
Independent regions can still yield records, but iteration ultimately raises
`RuntimeError` with `SCHEMA_MISMATCH` and statistics report `complete=False`.
Partial matches do not establish a successful scan; exports refuse to commit.
See [table discovery](../concepts/table-discovery.md) for exact header matching,
normalization, duplicate labels, repeated headers and ordering, and
[errors](../reference/errors.md) for failure timing.

## Manual fallback with TableSource

Use explicit sources to separate neighboring tables and exclude known comments
when automatic discovery cannot establish the desired boundaries. Each source
has independent bounds; optional per-source rules replace the shared rules
rather than merge with them. The following examples intentionally configure
positions.

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

## Different rules per table

Automatic discovery uses one shared rule set. To apply different filters,
conversions or projections, declare named sources with independent `Rules`.
The coordinates below intentionally belong to explicit extraction, not automatic
discovery. This complete CSV example also works conceptually for Excel columns:

```python
from pathlib import Path

from chooong.datasift import (
    ColumnBinding, DataType, FilterMask, NumericCondition, Operator, RecordKind,
    Rules, TableSource, TypeRule, scan_batches,
)

Path("departments.csv").write_text(
    "Item,Amount,,Item,Amount\nleft,120,,right,20\nsmall,80,,large,250\n",
    encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    # A source with rules replaces this entire shared rule set.
    select=("Item",),
    sources=(
        TableSource(
            name="sales",
            columns=(ColumnBinding(name="Item", column="A"),
                     ColumnBinding(name="Amount", column="B")),
            data_start_row=2,
            data_end_row=3,
            rules=Rules(
                types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
                where=NumericCondition(column="Amount", op=Operator.GTE, value=100),
                select=("Item", "Amount"),
            ),
        ),
        TableSource(
            name="costs",
            columns=(ColumnBinding(name="Item", column="D"),
                     ColumnBinding(name="Amount", column="E")),
            data_start_row=2,
            data_end_row=3,
            rules=Rules(
                types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
                where=NumericCondition(column="Amount", op=Operator.LT, value=100),
                select=("Amount", "Item"),
            ),
        ),
    ),
)
with scan_batches("departments.csv", mask, batch_size=1) as scan:
    records = [record for batch in scan for record in batch]
    statistics = scan.statistics
assert [(record.table, record.values) for record in records
        if record.kind == RecordKind.MATCHED] == [
    ("sales", {"Item": "left", "Amount": 120}),
    ("costs", {"Amount": 20, "Item": "right"}),
]
assert [(record.table, record.row) for record in records
        if record.kind == RecordKind.REJECTED] == [("sales", 3), ("costs", 3)]
assert statistics is not None and statistics.complete
assert (statistics.matched, statistics.rejected) == (2, 2)
```

Per-source rules do not merge with shared rules, including header configuration,
defaults and row policy. Set each required rule explicitly. Use `scan_batches`
when table identity matters: matching rows alone do not add source metadata.
See [column mapping](../concepts/column-mapping.md) and
[table inspection](table-inspection.md) for source names and bindings.
