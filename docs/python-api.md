# Python API

Import supported names from `chooong.datasift`. Implementation modules do not
provide additional stable import contracts. `py.typed` and a native stub are
included for static consumers.

## Masks

Readers accept a validated `FilterMask`, a mapping, JSON text, a `Path` or filename
string. Filter models are frozen; see [JSON Filters](contract.md) for operators,
wire aliases and schema generation. `TableSource` and `ColumnBinding` select
[explicit Excel sources](layouts.md#explicit-sources).

```python
from chooong.datasift import AllOf, FilterMask, NumericCondition, Operator, ScalarCondition

mask = FilterMask(
    sheet=None,
    where=AllOf(conditions=(
        ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
        NumericCondition(column="Amount", op=Operator.GTE, value=1000),
    )),
)
```

## Iterators

`iter_matching_rows(path, mask, *, batch_size=1024)` yields individual `Row` values.
It is a generator: initialization occurs at the first `next()`. Closing it closes
the underlying batch iterator. Use `contextlib.closing` when stopping early:

```python
from contextlib import closing
from chooong.datasift import iter_matching_rows

with closing(iter_matching_rows("sample.xlsx", mask)) as rows:
    first_row = next(rows, None)
```

`iter_matching_batches(path, mask, *, batch_size=1024)` returns a closeable
`BatchIterator` yielding `list[Row]`:

```python
from chooong.datasift import iter_matching_batches

with iter_matching_batches("sample.xlsx", mask) as batches:
    first_batch = next(batches, [])
```

It validates the mask, workbook metadata and regexes before return. A named-sheet
automatic scan resolves its first schema eagerly; an all-sheet scan resolves
schemas during iteration. Explicit sources validate bindings without interpreting
headers. Batches never cross worksheet boundaries and are flushed when output
column order changes. The valid batch-size range is listed in
[Limits & Errors](limits.md#resource-limits).

Close iterators after early termination. Closed/exhausted iterators remain
exhausted. Do not consume or close one iterator concurrently from several
threads; separate scans have separate workers.

## Rows

`Row` is an immutable mapping. Access values with `row["Country"]` or convert with
`dict(row)`. Its columns follow the [filter selection](contract.md#returned-columns).
Cell representations are defined in [Limits & Errors](limits.md#cell-values).
`CellValue`, `Expression` and `MaskInput` are exported type aliases.
