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

<!-- file: a.csv -->

```csv
ID,Amount
a,1
```

<!-- file: b.csv -->

```csv
ID,Amount
b,2
```

<!-- file: mask.json -->

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
