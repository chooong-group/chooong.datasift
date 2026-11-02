# Python API

Import the names documented here from `chooong.datasift`. Implementation modules
`models`, `reader` and `rust` do not define additional stable import paths.
The package includes `py.typed` and native stubs.

## Readers and writers

```text
iter_matching_rows(xlsx_path: PathInput, mask: MaskInput, *, batch_size: int = 1024)
    -> Generator[Row, None, None]
iter_matching_batches(xlsx_path: PathInput, mask: MaskInput, *, batch_size: int = 1024)
    -> BatchIterator
scan_batches(paths: PathInput, mask: MaskInput, *, batch_size: int = 1024,
             rejected: bool = True) -> ScanIterator
export(paths: PathInput, mask: MaskInput, output: str | Path, *,
       rejected_output: str | Path | None = None, batch_size: int = 1024) -> Statistics
recover_export(output: str | Path, *, journal_sha256: str,
               rejected_output: str | Path | None = None) -> None
```

`PathInput` is `str | Path | Sequence[str | Path]`. Strings can include glob patterns.
`MaskInput` is `FilterMask | Mapping[str, object] | str | Path`: strings beginning
with `{` after whitespace are JSON; other strings are filenames. Mask files use UTF-8.
Validated models are revalidated at the reader boundary; constructed/copied invalid
models cannot bypass validation. Mapping/JSON input uses wire aliases.

`iter_matching_rows` initializes on its first `next()`. The other iterators
validate mask/regex configuration before return and wait for native readiness.
First-schema/file validation can occur before return or during iteration,
depending on named/all-sheet, source, free-discovery and multi-file modes.
Use [error timing](../reference/errors.md) when handling partial output.

`BatchIterator` yields `list[Row]`; `ScanIterator` yields `list[ScanRecord]`.
Both expose `close()`, a context manager, and read-only `.statistics`
(`Statistics | None`). `rejected=False` suppresses rejected event records while
retaining rejection statistics. `export` returns completed statistics or raises.
Recovery semantics and its required digest are in [file safety](../reference/file-safety.md).

## Early termination

```python
from contextlib import closing
from pathlib import Path

from chooong.datasift import iter_matching_batches, iter_matching_rows

Path("data.csv").write_text("ID,Amount\na,1\nb,2\n", encoding="utf-8")
with closing(iter_matching_rows("data.csv", {"sheet": None})) as rows:
    first = next(rows)
    assert first["ID"] == "a"
with iter_matching_batches("data.csv", {"sheet": None}, batch_size=1) as batches:
    assert next(batches)[0] == first
```

See [streaming](../concepts/streaming.md) for cancellation, backpressure, schema
boundaries and thread ownership.

## Results

For a complete workflow inspecting actual records, schemas, bindings and counters,
see [table inspection and diagnostics](../guides/table-inspection.md).

`Row(cells: Mapping[str, CellValue])` is a frozen immutable mapping. Use
`row["ID"]`, `len(row)`, iteration over keys or `dict(row)`. It copies the supplied
mapping and exposes a read-only view. Column selection/order is defined in
[filter models](filters.md#projection).

| Public value/model | Fields |
| --- | --- |
| `Money` | `amount: Decimal`, `currency: str` |
| `PreciseDateTime` | `value: str`, an ISO civil/offset datetime retaining nanoseconds |
| `ScanRecord` | `kind`, `file`, `sheet`, `table`, `row`, `values`, `reasons=()`, `source_types` |
| `RejectReason` | `code: RejectCode`, `column: str \| None = None` |
| `Diagnostic` | `code`, `file`, optional `sheet`, `table`, `complete` |
| `Statistics` | `rows_read`, `matched`, `rejected`, `defaults`, `conversions`, `reasons`, `tables`, `diagnostics`, `complete`, `seconds`, `row_classes` |
| `TableExplanation` | `file`, `sheet`, `table`, `header_row`, `bindings`, `defaults`, `types`, `type_rules`, `header`, `raw_headers`, `data_start_row`, `data_end_row` |

`RecordKind` is `matched | rejected`. `RejectCode` values and diagnostic codes are
listed in [errors](../reference/errors.md). Rejected values are original; matched
values are converted/projected. Event `values` use validated tagged literal models
for exact types. `source_types` describes originals; `row` is a physical Excel row
or a logical CSV record. Table bindings use zero-based physical column indices.

### Statistics counters

Counters accumulate across input files, worksheets and tables in one scan.
They describe processing, including rejected records, rather than just exported
matches. Missing keys in `reasons` and `row_classes` mean zero occurrences.

| Counter | Counting unit and scope |
| --- | --- |
| `rows_read` | Input rows delivered by the parser, including structural rows; missing Excel rows are not synthesized |
| `matched`, `rejected` | Records per eligible table/source; overlapping sources can count one physical row more than once |
| `defaults` | Default assignments to empty cells, before conversion and filtering; includes later rejected records |
| `conversions` | Successful type-rule applications that change a cell value/type; failures and already-compatible unchanged values do not increment it |
| `reasons` | Occurrences of each rejection code; several columns can contribute the same code to one rejected record |
| `row_classes` | Classified table/source rows before include/exclude filtering; structural header counts also depend on discovery mode |
| `seconds` | Worker processing time including channel backpressure, rather than isolated CPU time |

Defaults and conversions count cells, not rows, and are not limited to projected
columns. A default followed by a successful conversion increments both counters.
Summed reason counts can exceed `rejected`; they are not counts of distinct rows.
`rejected=False` suppresses rejected events, without changing these counters.

`row_classes` includes excluded classifications. Its sum need not equal
`rows_read`: overlapping sources count independently, discovery can consume rows
before classification, and quarantined regions emit schema rejects outside the
normal classification path. Header accounting varies between automatic discovery
and explicit sources; these counters are not a partition of physical input rows.

For example, the first row below receives a default and converts it before
another column fails. The second row performs two successful conversions; the
third fails in two columns with the same rejection code:

```python
from pathlib import Path

from chooong.datasift import RejectCode, scan_batches

Path("counters.csv").write_text("ID,A,B\na,,bad\nb,0,1\nc,bad,bad\n", encoding="utf-8")
mask = {
    "sheet": None,
    "header": {"anchors": ["ID", "A", "B"]},
    "defaults": {"A": "2"},
    "types": {
        "A": {"type": "integer", "convert": True},
        "B": {"type": "integer", "convert": True},
    },
}
with scan_batches("counters.csv", mask, rejected=False) as scan:
    matches = [record for batch in scan for record in batch]
    statistics = scan.statistics
assert len(matches) == 1
assert statistics is not None and statistics.complete
assert (statistics.matched, statistics.rejected) == (1, 2)
assert (statistics.defaults, statistics.conversions) == (1, 3)
assert statistics.reasons[RejectCode.CONVERSION_FAILED] == 3
```

Statistics availability and incomplete scans follow the
[streaming contract](../concepts/streaming.md#completion-and-cancellation).

### Value types

`CellValue` is `str | bool | int | float | None | Decimal | Money | date | datetime |
PreciseDateTime`. `Expression` and `MaskInput` are also public type aliases.
[Data types](../concepts/data-types.md) defines representations and precision.

## Filter constructors

The supported filter constructors are `FilterMask`, `Rules`, `TableSource`,
`ColumnBinding`, `HeaderConfig`, `CsvConfig`, `RowPolicy`, `RowRule`, `TypeRule`,
`RegexSelection`, `ScalarCondition`, `MembershipCondition`, `NumericCondition`,
`TextCondition`, `EmptyCondition`, `TypeCondition`, `AllOf`, `AnyOf`, `Not`,
`DecimalLiteral`, `MoneyLiteral`, `DateLiteral` and `DatetimeLiteral`.
Enums are `Operator`, `DataType` and `RowClass`. Their exact fields and defaults
are documented in [filter models](filters.md).
