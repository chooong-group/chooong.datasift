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
`rows_read` counts input rows, including structural rows; matches/rejections count
per eligible table/source. Overlapping sources can therefore count a physical row
more than once as matched/rejected. `seconds` includes worker
processing and channel backpressure, not an isolated CPU measurement.

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
