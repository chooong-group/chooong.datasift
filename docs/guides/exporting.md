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
parquet_statistics = export(
    "input.csv", mask, "matched.parquet", rejected_output="rejected.parquet"
)
assert parquet_statistics.complete
assert (parquet_statistics.matched, parquet_statistics.rejected) == (1, 1)
assert Path("matched.parquet").read_bytes().startswith(b"PAR1")
assert Path("rejected.parquet").read_bytes().endswith(b"PAR1")
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

### Interpreting the generated schema

Parquet output is an event envelope, not a wide table with one top-level column
per input header. For the example above the matched record has `kind="matched"`,
`sheet="csv"`, `row=2`, and two elements in `values`: ID uses its `text` payload
(`"a"`), while Amount uses `integer` (12). The rejected record retains Amount as
`text="bad"`, rather than the attempted conversion result.

| Envelope field | Arrow type / contents |
| --- | --- |
| `kind`, `file`, `sheet`, `table` | Non-null UTF-8 strings |
| `row` | Non-null Int64, physical Excel row / logical CSV record |
| `values` | Non-null list of structs, each with a non-null UTF-8 `name` and nullable typed payloads |
| `reasons`, `source_types` | Non-null UTF-8 containing JSON, not nested Arrow maps |

The fixed payload types are UTF-8 text/currency, Int64 integer, Float64 float,
Boolean, Decimal256(76,28), Date32, timestamp microseconds and Int32 remainder/offset.
Null cells retain their name with no populated payload. To analyze a column,
expand `values`, select its `name` and read the appropriate payload. DataSift
does not provide a public Parquet reader; downstream readers must handle this
envelope explicitly.

For interrupted writes, follow the existing
[commit and recovery protocol](../reference/file-safety.md#commit-protocol).
The recovery call there illustrates the public signature; it needs a real failed
commit and a separately preserved trusted digest. Do not manufacture journals or
derive trust by hashing a journal of unknown provenance.
