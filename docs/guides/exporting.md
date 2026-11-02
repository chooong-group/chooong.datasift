# Exporting

Use `export` or CLI `--output` to write native NDJSON/Parquet without transferring
record serialization to Python. The exact lowercase suffix `.parquet` selects
Parquet; other suffixes select NDJSON. Inputs may be paths, sequences or globs.
Expanded path strings are deduplicated and sorted lexically, not by file identity.

## Matched and rejected files

```python
from pathlib import Path

from chooong.datasift import export

Path("input.csv").write_text("ID,Amount\na,12\nb,bad\n", encoding="utf-8")
mask = {
    "sheet": None,
    "header": {"anchors": ["ID", "Amount"]},
    "types": {"Amount": {"type": "integer", "convert": True}},
}
statistics = export("input.csv", mask, "matched.ndjson", rejected_output="rejected.ndjson")
assert statistics.complete
assert (statistics.matched, statistics.rejected) == (1, 1)
```

Matched NDJSON contains projected values. Rejected NDJSON contains the complete
record envelope, original values, reasons and source types. The same iterator
contracts are described in [Python API](../api/python.md#results).

```python
import json

assert json.loads(Path("matched.ndjson").read_text()) == {"ID": "a", "Amount": 12}
assert json.loads(Path("rejected.ndjson").read_text())["values"]["Amount"] == "bad"
export("input.csv", mask, "matched.parquet", rejected_output="rejected.parquet")
assert Path("matched.parquet").read_bytes().startswith(b"PAR1")
```

## Commit and recovery

Scan/serialization failures preserve prior result files. After successful staging,
a journal coordinates individual destination replacements; two files are not a
shared atomic filesystem transaction. Readers must honor an outstanding journal.
Recovery requires all caller-authorized destinations and a separately trusted
journal SHA-256. The complete protocol and concurrent-writer limits are defined
once in [file safety](../reference/file-safety.md).

## Parquet schema

Both Parquet streams use the envelope `kind`, `file`, `sheet`, `table`, `row`,
`values`, `reasons`, `source_types`. `values` is a list of named typed cells with
nullable fields `text`, `integer`, `float`, `boolean`, `decimal`, `currency`,
`date`, `datetime`, `nanosecond_remainder`, `utc_offset_seconds`. Null populates
none of these payload fields.

Decimal/money use Decimal256(76,28); scale is canonicalized to 28 without changing
the numeric value. Dates use Date32. Datetimes use timestamp microseconds plus a
separate nanosecond remainder. For offset datetimes, timestamps are UTC and the
original offset is retained; null offset means civil local time. Money retains
its currency. Reasons/source types are JSON stored in UTF-8 fields. The fixed
schema preserves different table shapes without inference or a full input scan;
writing uses bounded batches/row groups.
