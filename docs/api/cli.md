# Command-line interface

`chooong-datasift` and `python -m chooong.datasift` invoke the same CLI.
The final positional argument is the UTF-8 JSON mask; at least one input is required.

```text
chooong-datasift [-h] [--batch-size BATCH_SIZE] [--output OUTPUT]
                [--rejected-output REJECTED_OUTPUT] [--explain EXPLAIN]
                INPUT [INPUT ...] MASK
```

| Argument | Behavior |
| --- | --- |
| `INPUT` | XLSX/XLSM/CSV paths or glob patterns, sorted/deduplicated by expanded path strings |
| `MASK` | JSON mask filename |
| `--batch-size` | Integer 1–65536; default 1024 |
| `--output` | Matched NDJSON file; exact `.parquet` suffix selects Parquet |
| `--rejected-output` | Rejected original records; requires `--output`; `.parquet` supported |
| `--explain` | Actual-run statistics/diagnostics JSON, written separately after result commit |
| `-h`, `--help` | Show usage and exit |

Quote glob patterns to let DataSift expand them consistently. An unmatched glob
is an error. No `--output` means matching NDJSON on stdout, which may contain
partial results before a late failure. There is no automatic rollback for stdout.

## Multiple files

```csv
ID,Amount
a,1
```

```csv
ID,Amount
b,2
```

```json
{"sheet": null, "header": {"anchors": ["ID", "Amount"]}}
```

```bash
chooong-datasift '*.csv' mask.json --output matches.ndjson --explain statistics.json
```

```python
import json
from pathlib import Path

assert [json.loads(line)["ID"] for line in Path("matches.ndjson").read_text().splitlines()] == ["a", "b"]
assert json.loads(Path("statistics.json").read_text())["complete"] is True
```

### Filter multiple files and inspect the report

Reuse `a.csv` and `b.csv` from above. This mask converts Amount before applying
the numeric filter, returns only ID, and records both matches and rejections:

```json
{
  "sheet": null,
  "header": {"anchors": ["ID", "Amount"]},
  "types": {"Amount": {"type": "integer", "convert": true}},
  "where": {"column": "Amount", "op": "gte", "value": 2},
  "select": ["ID"]
}
```

```bash
chooong-datasift '*.csv' filtered.json --output filtered.ndjson --rejected-output rejected.ndjson --explain filtered-report.json
```

```python
assert json.loads(Path("filtered.ndjson").read_text()) == {"ID": "b"}
rejected = json.loads(Path("rejected.ndjson").read_text())
assert rejected["values"] == {"ID": "a", "Amount": "1"}
assert rejected["reasons"] == [{"code": "FILTER_NOT_MATCHED", "column": None}]
report = json.loads(Path("filtered-report.json").read_text())
assert report["complete"] is True
assert (report["matched"], report["rejected"], report["conversions"]) == (1, 1, 2)
assert len(report["tables"]) == 2
assert report["tables"][0]["bindings"] == [["ID", 0], ["Amount", 1]]
```

Use [advanced filtering](../guides/advanced-filtering.md) for AND/OR/NOT and regex.
[Error handling](../guides/error-handling.md) shows partial multi-file results;
failed scans do not write `--explain` through this CLI.

## Exit status and diagnostics

- 0: completed successfully, including empty results or rejected data rows.
- 1: caught mask/scan/write failure; stderr reports the exception class and
  incomplete output without cell values.
- 2: argument parsing or output-path validation failed.

Uncaught failures outside these handled paths can also return nonzero; this is
not a promise that every possible failure has one redacted diagnostic.
Schema errors process independent tables then return nonzero; neither result file
is committed. `file_errors="continue"` also ends nonzero after processing other
files. [Errors](../reference/errors.md) defines partial scans.

`--explain` includes bindings, classifications, conversion/default counts,
rejection frequencies and file/schema diagnostics from the actual run, without a
second scan. It is written only after successful consumption and is not journaled
with result files. A diagnostic-write failure can therefore follow a committed
result. [File safety](../reference/file-safety.md) defines alias checks, durability
and recovery. The CLI's redacted commit failure does not expose the trusted journal
digest; use Python `export` when a separately retained recovery digest is required.
