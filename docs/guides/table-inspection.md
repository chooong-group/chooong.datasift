# Table inspection and diagnostics

`scan_batches` exposes matched/rejected records and statistics from the actual
scan. It is not a separate discovery-only API: exhaust the iterator to finish
validation, filtering and schema checks. Final statistics explain each discovered
schema, its bindings and configured transformations.

## Inspect a completed scan

```python
from pathlib import Path

from chooong.datasift import (
    DataType, FilterMask, HeaderConfig, RecordKind, RejectCode, TypeRule, scan_batches,
)

Path("inspect.csv").write_text(
    "Sales report\n,ID,Amount\n,a,12\n,b,bad\n", encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("ID", "Amount")),
    types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
)
with scan_batches("inspect.csv", mask, batch_size=1) as scan:
    records = [record for batch in scan for record in batch]
    statistics = scan.statistics
assert [(record.kind, record.row, record.values) for record in records] == [
    (RecordKind.MATCHED, 3, {"ID": "a", "Amount": 12}),
    (RecordKind.REJECTED, 4, {"ID": "b", "Amount": "bad"}),
]
assert records[1].reasons[0].code == RejectCode.CONVERSION_FAILED
assert statistics is not None and statistics.complete
assert (statistics.matched, statistics.rejected, statistics.conversions) == (1, 1, 1)
assert statistics.diagnostics == ()
assert len(statistics.tables) == 1
table = statistics.tables[0]
assert table.sheet == "csv"
assert table.header_row == 2
assert table.bindings == (("ID", 1), ("Amount", 2))
assert table.raw_headers == (("ID", 1), ("Amount", 2))
assert table.type_rules["Amount"].type == DataType.INTEGER
assert (table.data_start_row, table.data_end_row) == (3, 4)
```

Binding indices are zero-based physical columns. Row numbers are physical Excel
rows or logical CSV records, including headers. `raw_headers` retain labels before
normalization; `bindings` contain final names. Record `table` identifies its
source/table; named explicit sources use the configured name.

`Statistics.complete=True` means the scan completed, even with rejected data
rows. It is not a declaration that all rows passed validation. An early stopped
or failed scan may have no statistics or incomplete statistics. See
[error handling](error-handling.md) for `FILE_ERROR`, `AMBIGUOUS_HEADER` and
`SCHEMA_MISMATCH`, including valid records from independent tables.

## CLI reports and schemas

CLI `--explain report.json` writes the same actual-run statistics after successful
consumption. It includes tables/bindings, rule configuration, counts and diagnostics;
it is not a discovery preview and is not written after a failed scan. The
[multi-file CLI example](../api/cli.md#multiple-files) checks output and report
together. `--explain` is a separate write after result commit.

A discovered table schema describes actual bindings. A generated
[JSON Schema](../api/json-schema.md) instead describes the mask contract;
it does not discover input columns. The [Python API](../api/python.md#results)
lists every result field and explains counter units. Avoid interpreting
`row_classes` as a partition of physical input rows.
