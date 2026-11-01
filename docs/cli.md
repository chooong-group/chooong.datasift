# CLI

```bash
chooong-datasift 'input/*.xlsx' other.csv mask.json --output matched.ndjson \
  --rejected-output rejected.ndjson --batch-size 1024 --explain statistics.json
```

Inputs may be CSV/XLSX/XLSM paths or glob patterns, sorted lexically. The final
positional argument is the JSON mask. With no `--output`, native serialized
matching NDJSON is written to stdout. Stdout can contain partial results after
a late failure. `--rejected-output` requires `--output`. Both accept `.parquet`
for native Parquet. No Python DataFrame or serializer processes records.

`--explain` writes actual-run JSON statistics, table bindings, classifications,
conversion/default counts, reject frequencies and schema/file diagnostics.
It performs no second data scan. Diagnostics contain no record values.
Exit 0 means complete success; technical scan, validation or write errors return
nonzero and stderr omits cell values. No file errors are silently skipped.

## File output

Scan and serialization finish into staged files, then each is flushed/fsynced.
Until that succeeds, prior destinations remain intact. A durable
`.OUTPUT.datasift-commit.json` journal binds each prepared stage to its SHA-256 checksum. Destinations
are renamed individually, with directory fsync on Unix, then the journal is
removed. These renames are **not** a shared atomic filesystem transaction.
Readers requiring both outputs must check that the commit journal is absent.
An interrupted commit can expose one new and one old destination; the journal
makes that state explicit. Preserve the journal and staged files, then run:

```python
from chooong.datasift import recover_export
recover_export("matched.ndjson")
```

Recovery rolls forward remaining staged files; completed renames stay in place only when their destination checksum matches. Missing or changed bytes fail closed.
A new export refuses an outstanding journal. A second recovery after journal
removal fails closed. Stable `.OUTPUT.datasift.lock` sidecars use OS file locks to
serialize concurrent writers/recovery; they can remain after success. Inputs,
mask and outputs must be distinct; symlink outputs and input aliases are refused.
Directory durability on Windows is platform dependent and needs native testing.
`--explain` is a separate diagnostic write after result commit; it is not part
of the two-result commit protocol.

## Parquet schema

Parquet has a fixed heterogeneous-record envelope: `kind`, `file`, `sheet`,
`table`, `row`, `values`, `reasons` and `source_types`. `values` is a list of named typed cells
with nullable `text`, `integer`, `float`, `boolean`, `decimal`, `currency`,
`date`, `datetime`, `nanosecond_remainder`, `utc_offset_seconds` fields. Null has no populated payload.
Decimal/money use native Decimal256(76,28), dates Date32, civil datetimes timestamp
microseconds with the remaining nanoseconds in a separate integer. For offset
datetimes the timestamp is UTC and the original offset is retained separately;
null offset means civil local time. Money pairs
the exact decimal with its currency. This fixed schema preserves independently
shaped tables without inference, coercion or a full input scan. Input decimal
scale is canonicalized to 28; its numeric value remains exact. Reasons and source types are
structured JSON in UTF-8 fields. Data is written in bounded batches/row groups.


## Runnable validation example

```bash
chooong-datasift examples/transactions.csv examples/validation-filter.json \
  --output matched.ndjson --rejected-output rejected.ndjson --explain statistics.json
```

This produces two matched records and one rejected original record containing
both `REQUIRED_MISSING` and `CONVERSION_FAILED`. The empty amount defaults to exact
EUR 0.00 and the empty country to UNKNOWN. Change the output suffixes to `.parquet`
to use the same scan with native typed columnar output.
