# Validation and rejected records

Create `transactions.csv`:

<!-- file: transactions.csv -->

```csv
CustomerID,Amount,Country
C1,"1.234,56",DE
,invalid,AT
C3,,
```

This mask requires IDs and amounts, defaults missing values, converts localized
money and returns all three columns:

<!-- file: validation.json -->

```json
{
  "sheet": null,
  "header": {"anchors": ["CustomerID", "Amount", "Country"]},
  "select": ["CustomerID", "Amount", "Country"],
  "required": ["CustomerID", "Amount"],
  "defaults": {"Amount": "0,00", "Country": "UNKNOWN"},
  "types": {
    "Amount": {"type": "money", "convert": true, "currency": "EUR", "locale": "de-DE"}
  }
}
```

```python
from chooong.datasift import RecordKind, RejectCode, scan_batches

with scan_batches("transactions.csv", "validation.json", batch_size=1) as scan:
    records = [record for batch in scan for record in batch]
    statistics = scan.statistics
assert [record.kind for record in records] == [
    RecordKind.MATCHED, RecordKind.REJECTED, RecordKind.MATCHED
]
assert {reason.code for reason in records[1].reasons} == {
    RejectCode.REQUIRED_MISSING, RejectCode.CONVERSION_FAILED
}
assert records[1].values == {"CustomerID": None, "Amount": "invalid", "Country": "AT"}
assert statistics is not None and statistics.complete
assert (statistics.matched, statistics.rejected, statistics.defaults) == (2, 1, 2)
```

Rejected records retain original values. Defaults and conversions apply to
matched values only in the output; multiple rejection reasons are retained.
The final row becomes exact EUR 0.00 with country UNKNOWN. A missing bound column
instead causes a [schema failure](../reference/errors.md#schema-failures).
[Data types](../concepts/data-types.md) defines conversion precision and locales.

## Row classification

Row rules inspect original values before defaults and conversion. First matching
rule wins; `rows` and `where` together mean AND. `exclude` overrides `include`.
Create `classified.csv`:

<!-- file: classified.csv -->

```csv
ID,Amount
a,1
TOTAL:,1
```

```python
from chooong.datasift import iter_matching_rows

mask = {
    "sheet": None,
    "header": {"anchors": ["ID", "Amount"]},
    "row_policy": {"rules": [{
        "classification": "total",
        "where": {"column": "ID", "op": "starts_with", "value": "TOTAL:"},
    }]},
}
assert [dict(row) for row in iter_matching_rows("classified.csv", mask)] == [
    {"ID": "a", "Amount": "1"}
]
```

The default policy includes only data. Excluded structural rows enter neither
match nor reject streams; statistics count their classifications separately.
Comments/totals/separators require explicit rules. Free discovery consumes blank
region boundaries before classification; explicit sources can include physical
empty records. See [RowPolicy](../api/filters.md#rowpolicy) for every class and field.

## Exact values and dates in Python

This standalone example converts CSV text to exact Decimal and Money values,
a civil date and a nanosecond datetime. The invalid amount in the second record
is rejected; it is not rounded or replaced. Anchors keep discovery independent
of the data types and filters.

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from chooong.datasift import (
    DataType, FilterMask, HeaderConfig, Money, PreciseDateTime, TypeRule,
    iter_matching_rows,
)

Path("exact.csv").write_text(
    "ID,Ratio,Price,Booked,Observed\n"
    "a,0.100000000000000000000001,12.50,02.11.2026,2026-11-02T12:00:00.123456789\n"
    "b,invalid,20.00,03.11.2026,2026-11-03T12:00:00\n",
    encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("ID", "Ratio", "Price", "Booked", "Observed")),
    types={
        "Ratio": TypeRule(type=DataType.DECIMAL, convert=True),
        "Price": TypeRule(type=DataType.MONEY, convert=True, currency="EUR"),
        "Booked": TypeRule(type=DataType.DATE, convert=True, format="%d.%m.%Y"),
        "Observed": TypeRule(type=DataType.DATETIME, convert=True),
    },
)
assert [dict(row) for row in iter_matching_rows("exact.csv", mask)] == [{
    "ID": "a",
    "Ratio": Decimal("0.100000000000000000000001"),
    "Price": Money(Decimal("12.50"), "EUR"),
    "Booked": date(2026, 11, 2),
    "Observed": PreciseDateTime("2026-11-02T12:00:00.123456789"),
}]
```

Matching rows expose Python values; `scan_batches` and NDJSON represent exact
values using tagged literal models/objects. Decimal supports scale 0–28 and a
96-bit coefficient. Money requires an unambiguous currency; no exchange conversion
occurs. Datetime offsets are preserved when present; no timezone is invented.
Excel date systems, serial-day restrictions and native style handling are defined
in [data types](../concepts/data-types.md), together with every conversion limit.
