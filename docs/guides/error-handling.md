# Error handling

Rejected data rows, schema failures and technical file failures have different
outcomes. Rejected rows alone allow a completed scan. Schema/file failures can
yield partial records and still raise; neither `next()` nor accumulated matches
certify completion. Use final statistics and the exception together.

## Continue across file failures

This example deliberately creates one malformed UTF-8 CSV and two valid files.
Even when paths are supplied out of order, expanded path strings are sorted and
deduplicated. The continue policy processes the valid files and ultimately raises.

```python
from pathlib import Path

from chooong.datasift import FilterMask, HeaderConfig, ScanRecord, scan_batches

Path("00-broken.csv").write_bytes(b"ID,Amount\ninvalid,\xff\n")
Path("10-valid.csv").write_text("ID,Amount\na,1\n", encoding="utf-8")
Path("20-valid.csv").write_text("ID,Amount\nb,2\n", encoding="utf-8")
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("ID", "Amount")),
    file_errors="continue",
)
records: list[ScanRecord] = []
with scan_batches(["20-valid.csv", "00-broken.csv", "10-valid.csv"], mask) as scan:
    try:
        for batch in scan:
            records.extend(batch)
    except RuntimeError:
        statistics = scan.statistics
    else:
        raise AssertionError("A failed input must not produce successful completion")
assert [record.values for record in records] == [
    {"ID": "a", "Amount": "1"}, {"ID": "b", "Amount": "2"},
]
assert statistics is not None and not statistics.complete
assert statistics.matched == 2
assert [diagnostic.code for diagnostic in statistics.diagnostics] == ["FILE_ERROR"]
assert statistics.diagnostics[0].file == "00-broken.csv"
```

These are partial results for deliberate caller handling. Do not publish them
as a complete dataset. With the default `file_errors="fail"`, the first technical
file error stops processing. Early technical failures can leave statistics
unavailable. Catch errors around iterator creation as well as consumption.

## Schema failures preserve independent regions

A text-only Free Discovery candidate is ambiguous. The independent numeric table
still produces a record, then the scan fails with incomplete statistics:

```python
from chooong.datasift import RecordKind

Path("ambiguous.csv").write_text(
    "Name,State,,ID,Amount\nAlice,Open,,ok,2\n", encoding="utf-8",
)
partial: list[ScanRecord] = []
with scan_batches("ambiguous.csv", FilterMask(sheet=None), batch_size=1) as scan:
    try:
        for batch in scan:
            partial.extend(batch)
    except RuntimeError:
        statistics = scan.statistics
    else:
        raise AssertionError("An ambiguous region must fail the scan")
assert [record.values for record in partial if record.kind == RecordKind.MATCHED] == [
    {"ID": "ok", "Amount": "2"},
]
assert statistics is not None and not statistics.complete
assert {diagnostic.code for diagnostic in statistics.diagnostics} == {
    "SCHEMA_MISMATCH", "AMBIGUOUS_HEADER",
}
```

`file_errors` does not control schema quarantine. Independent tables continue
under either file policy. Use anchors for this text-only table, or explicit
sources for known boundaries. `schema_policy="strict"` additionally requires
the same bound column names across tables/files; the default `"per_table"`
allows different shapes. See [discovery](automatic-table-discovery.md) and
[error codes and timing](../reference/errors.md).

## Preserve previous exports

Export consumes the full scan before committing staged output. The same failed
input set cannot replace a previous result, even though it contains valid rows:

```python
from chooong.datasift import export

output = Path("previous.ndjson")
output.write_text('previous result\n', encoding="utf-8")
try:
    export(["00-broken.csv", "10-valid.csv"], mask, output)
except RuntimeError:
    pass
else:
    raise AssertionError("Export must fail when any input is incomplete")
assert output.read_text(encoding="utf-8") == "previous result\n"
```

Commit interruption is a different failure phase: multiple output replacements
are not a shared atomic transaction. Recovery needs a separately trusted journal
digest and all authorized destinations. Follow the
[file-safety protocol](../reference/file-safety.md), not a guessed retry.
CLI stdout may already contain partial results after failure; it cannot roll back.
