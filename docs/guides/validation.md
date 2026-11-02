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
