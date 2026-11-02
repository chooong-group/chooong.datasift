# Data types and precision

Unconfigured Excel cells become `str`, `bool`, i64-backed `int`, IEEE-754 `float`
or `None`. Empty text remains `""`; Excel error cells remain strings. Formula
cells use cached results, or null when no cache exists. CSV cells initially
contain text or null. Neither strings nor booleans become numbers implicitly.

## Explicit conversion

`types` binds columns to a `TypeRule`; conversion requires `convert=True`.
Without conversion, incompatible values are rejected. Native styles can identify
dates/money when a corresponding type rule exists. Raw OOXML numeric lexemes use
invariant decimal syntax even when a rule specifies a text locale.

Supported targets are listed in [filter models](../api/filters.md#type-rules).
`is_type` and `not_type` inspect effective values after configured conversions.
Values already matching the target type are retained. Conversion does not make
native floating-point values exact. For non-null targets, null and empty text
remain empty; `required` rejects them unless a default supplies a value first.

### Conversion inputs

The following rules apply when `convert=True`. Text is trimmed for conversion
except when the target is `string`, which preserves existing text unchanged.

| Target | Accepted inputs | Rejected examples / limits |
| --- | --- | --- |
| `string` | Text, or numeric values represented as text | Existing boolean and money values are not stringified |
| `integer` | Integral numeric values or numeric text | `"1.5"`; values outside signed i64 |
| `float` | Numeric values or numeric text exactly representable as a float | Text `"0.1"`; `"NaN"`; infinity |
| `number` | Existing integer, float or Decimal; numeric text converts to float | Text `"0.1"` fails the same exactness check as `float` |
| `boolean` | Native booleans; text `"true"` or `"false"` | `"TRUE"`, `"False"`, `"1"`, `"0"`, numeric 1/0 |
| `null` | Actual null only | Empty text and nonempty values are not converted to null |
| `decimal` | Numeric values or numeric text | Precision/range beyond the 96-bit coefficient and scale 0–28 |
| `currency_code` | Valid uppercase ISO-4217 text, such as `"EUR"` | `"eur"`; unknown codes |
| `money` | Numeric values or localized numeric text with an unambiguous currency | A symbol alone; a text code conflicting with configured currency |
| `date` | Numeric Excel serials; ISO `YYYY-MM-DD` text; text matching `format` | Invalid dates; serial 60 in the 1900 system; nonzero time of day |
| `datetime` | Numeric Excel serials; ISO local/RFC3339 text; text matching `format` | Invalid/out-of-range dates; serial fractions losing nanoseconds |

`locale` applies to numeric text. Native OOXML numbers retain invariant syntax.
Boolean conversion is case-sensitive and does not treat numeric flags as booleans.
Integer conversion cannot truncate fractions; float conversion cannot silently
round decimal text. Use text/equality for identifiers whose digits must survive
beyond float precision. Decimal/money and temporal details follow below.

### Conversion example

This example includes a rejected boolean flag and an explicit date format:

```python
from datetime import date
from pathlib import Path

from chooong.datasift import RecordKind, RejectCode, scan_batches

Path("typed.csv").write_text(
    "ID,Enabled,Booked\na,true,02.11.2026\nb,false,03.11.2026\nc,1,04.11.2026\n",
    encoding="utf-8",
)
mask = {
    "sheet": None,
    "header": {"anchors": ["ID", "Enabled", "Booked"]},
    "types": {
        "Enabled": {"type": "boolean", "convert": True},
        "Booked": {"type": "date", "convert": True, "format": "%d.%m.%Y"},
    },
}
with scan_batches("typed.csv", mask) as scan:
    records = [record for batch in scan for record in batch]
assert [record.kind for record in records] == [
    RecordKind.MATCHED, RecordKind.MATCHED, RecordKind.REJECTED
]
assert records[0].values["Enabled"] is True
assert records[1].values["Enabled"] is False
assert records[0].values["Booked"].value == date(2026, 11, 2).isoformat()
assert records[2].values["Enabled"] == "1"
assert records[2].reasons[0].code == RejectCode.CONVERSION_FAILED
```

Event records retain tagged date literals; matching-row iterators expose `date`
objects. A conversion failure is a row rejection, not a fatal scan error.

## Decimal and money

Decimal uses a 96-bit coefficient and scale 0–28. Excess precision/range rejects
instead of rounding. Use text cells when Excel has already lost numeric precision;
DataSift cannot recover digits that were not stored.

Money couples an exact Decimal amount with an ISO-4217 currency. Currency comes
from an explicit ISO code in text, a compatible cell format or configuration.
A symbol alone does not choose a currency. Conflicting codes reject; no exchange
conversion occurs. Text locales `de-DE` and `en-US` select decimal/group separators;
groups must contain three digits.

NDJSON and exact comparison literals use tagged objects. For example:

```json
{"type": "money", "amount": "1234.56", "currency": "EUR"}
```

Python matching rows expose `Decimal` and `Money`; event records use validated
literal models such as `MoneyLiteral`. The [validation guide](../guides/validation.md)
shows conversion and rejections. [Exporting](../guides/exporting.md) describes Parquet.

## Dates and datetimes

Conversions accept ISO text, an explicit chrono strftime `format`, or Excel serials
using the workbook's 1900/1904 date system. Fictitious serial day 60 in the 1900
system rejects. Fractional days must be exact to nanoseconds. A `date` target
rejects a nonzero time of day. Supported years are 0001–9999.

Excel datetimes are civil local times; no timezone is invented. RFC3339 offsets
are retained, and comparisons of offset datetimes compare instants. Local and
offset datetimes are not implicitly mixed. Matching values use `PreciseDateTime`
when Python `datetime` would lose nanoseconds; event records and exports retain
the full value. Decimal/money equality and ordering are exact; money requires the
same currency. Ordering of the default unconfigured numeric values retains float
semantics when floats are involved.
