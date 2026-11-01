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

It validates the mask and regexes before return. An anchored named-sheet scan
resolves workbook metadata and its first schema eagerly; free discovery and all-sheet scans resolve
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


## Matched and rejected streams

```python
from chooong.datasift import RecordKind, scan_batches

with scan_batches(["a.csv", "b.xlsx"], {"sheet": None}, batch_size=1024) as scan:
    for batch in scan:
        for record in batch:
            if record.kind == RecordKind.REJECTED:
                print(record.row, record.reasons)
    statistics = scan.statistics
```

`scan_batches` returns a closeable/context-managed `ScanIterator`. Each
`ScanRecord` contains `kind`, `file`, `sheet`, `table`, physical `row`, `values`,
`source_types`, and structured `reasons`. Rejected values are originals; matched
values are converted/projected. Exact event values use typed tagged models such
as `MoneyLiteral`. Multiple reasons are retained. `rejected=False` avoids building
reject records. One ordered stream avoids buffering an independently unread
second iterator. Two queued native batches enforce backpressure. Early close
cancels the worker; statistics remain unavailable until the scan finishes.
Matching iterators also expose final `.statistics`.

Paths accept a single path, a sequence or glob patterns. Exact duplicate path
strings are processed once after lexical sorting. `file_errors: "continue"`
processes remaining files after a technical file error, records `FILE_ERROR`,
sets `complete=false`, and still raises at the end. Already yielded rows remain
partial; never interpret them as a complete successful result.

Schema errors (missing projection/required/type/filter columns, normalization
collisions or ambiguous free layouts) quarantine the affected table or region.
Other tables, sheets and files continue independently of `file_errors`.
Both scan and matching iterators yield valid partial records, then raise
`RuntimeError` containing `SCHEMA_MISMATCH`. Final statistics have
`complete=false` and diagnostics, including when there were no data rows.
Matching iterators have no reject stream; consume through exhaustion and check
completion. Early `next()` success never certifies the whole input.
Exports refuse to commit either result after a schema error.

`export(paths, mask, output, *, rejected_output=None, batch_size=1024)` writes
native NDJSON or Parquet (selected by `.parquet` suffix) and returns `Statistics`.
`recover_export(output, *, journal_sha256, rejected_output=None)` rolls forward
an interrupted journaled commit. Both destination paths and the trusted journal
SHA-256 must come from the caller.
See [CLI](cli.md) for commit semantics. Public API additions are the models and
functions exported in `chooong.datasift.__all__`; internal native entry points
are not a stable consumer contract.


Table explanations include original and normalized header names, zero-based
physical bindings, actual data bounds, header settings and declared type rules.
Default diagnostics identify columns without copying configured cell values.
See `Statistics`, `TableExplanation`, `Diagnostic` and `RejectReason` for the
typed result contract.
