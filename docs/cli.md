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
nonzero and stderr omits cell values. Schema errors also return nonzero after
processing independent tables; neither result file is committed. No file errors are silently skipped.

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
recover_export(
    "matched.ndjson",
    journal_sha256=trusted_sha256,  # from the failed export error, stored separately
    rejected_output="rejected.ndjson",  # required if the commit includes rejects
)
```

Recovery requires a trusted SHA-256 of the complete journal and explicit caller
paths for **all** destinations. The native commit error includes
`journal_sha256=<hex>` after a journal was created. Store that value separately;
computing a hash from a possibly manipulated journal does not establish trust.
After an abrupt process crash with no independently preserved digest, automatic
recovery is refused: restore/re-export from the trusted input after inspecting
the incomplete output set. The old `recover_export(output)` call is incompatible.

Recovery checks manifest size/fields, exact destination bindings, reserved stage
names and byte hashes before committing. Regular files with exactly one link are
required for stages, journal, targets and locks. Symlinks, hardlinks and special
files are refused. Open directory capabilities pin the output directories;
private snapshots are hashed while copying from held file descriptors. Only
these snapshots are renamed, so replacing a stage path after checking cannot
substitute committed bytes. Source stages remain after recovery for inspection;
successful ordinary export removes its own stages.

Destination contents/identity, parent directories, locks and journal are checked
again before installation. A changed destination fails closed and the journal
remains. Completed destinations without a stage must already match the manifest.
A new export refuses an outstanding journal; repeating recovery after journal
removal fails. Stable `.OUTPUT.datasift.lock` sidecars serialize cooperative
writers and may remain after success.

Use caller-owned output directories protected against untrusted writers. Locks
are advisory; there is no portable compare-and-rename transaction against a
hostile process with the same filesystem authority. A final target symlink or
hardlink substitution is replaced as a directory entry, never followed to write
its linked victim. Multi-file commits can still be interrupted between installs;
readers must honor the journal. Private snapshots use mode 0700 directories on
Unix and inherited directory ACLs on Windows. Directory durability on Windows
is platform dependent and needs native testing. Inputs, mask and outputs must
be distinct; input aliases are refused.
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
