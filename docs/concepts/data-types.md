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
Required fields reject null/empty values; otherwise null is allowed.
Integer conversion cannot truncate fractions or exceed i64. Float conversion
rejects inexact values such as decimal 0.1. Use text/equality for identifiers whose
digits must survive beyond float precision.

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
