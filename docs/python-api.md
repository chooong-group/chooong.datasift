# Python API

Import supported names from `chooong.datasift`. Implementation modules `models`,
`reader` and the native `rust` extension are not additional stable import contracts.
`py.typed` and a native stub are included for static consumers.

## Masks

`FilterMask(sheet=..., where=..., source=None)` is frozen and validated. Pass it
directly, or pass a mapping, JSON text, `Path`, or filename string to the readers.
Mapping/JSON boundaries use the wire aliases `all`, `any`, `not`.

The expression models are `ScalarCondition`, `MembershipCondition`,
`NumericCondition`, `TextCondition`, `EmptyCondition`, `AllOf`, `AnyOf`, and `Not`.
`Operator` is a `StrEnum`. Generate a schema from the canonical model with
`FilterMask.model_json_schema(by_alias=True)` instead of maintaining another schema.
See [Filter Reference](contract.md) for fields, limits and negative cases.

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

## Readers and rows

`iter_matching_batches(path, mask, *, batch_size=1024)` returns a closeable
`BatchIterator` yielding `list[Row]`. Use a context manager when stopping early:

```python
from chooong.datasift import iter_matching_batches

with iter_matching_batches("sample.xlsx", mask, batch_size=1024) as batches:
    first_batch = next(batches, [])
```

`iter_matching_rows(path, mask, *, batch_size=1024)` yields individual rows and
closes the underlying iterator when the generator is closed. Initialization
happens at its first `next()`. Early consumers should explicitly close the generator.

`Row` is an immutable mapping. `row["Country"]` and `dict(row)` are supported.
Cells are `str | bool | int | float | None`. Only mask columns are returned,
including columns referenced inside `any` or `not`. `CellValue`, `Expression` and
`MaskInput` are exported type aliases; `ColumnBinding`/`TableSource` support
[explicit sources](sources.md).

An individual iterator must not be consumed/closed concurrently from multiple
threads. Separate scans have separate workers. Closed or exhausted iterators
stay exhausted. Already delivered rows are not rolled back on a later error;
see [error handling](errors.md).
