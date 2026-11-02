# JSON Filters

A mask contains `sheet` and optional rules and sources. `FilterMask` is the
canonical input model; `FilterMask.model_json_schema(by_alias=True)` generates its
JSON schema. The format is v1 with no version field. Unknown fields, invalid types
and unsupported operators are rejected.

| Field | Required | Value |
| --- | --- | --- |
| `sheet` | Yes | Nonblank worksheet name, or `null` for all worksheets |
| `where` | No | One expression, defined below |
| `source` | No | Explicit column bindings and row bounds; see [Excel Layouts](layouts.md#explicit-sources) |

For worksheet selection, header discovery and duplicate column names, see
[Excel Layouts](layouts.md).

## AND, OR and NOT

```json
{
  "sheet": null,
  "where": {
    "all": [
      {"column": "Amount", "op": "gte", "value": 1000},
      {
        "any": [
          {"column": "Country", "op": "eq", "value": "DE"},
          {"column": "Country", "op": "eq", "value": "AT"}
        ]
      },
      {"not": {"column": "Status", "op": "eq", "value": "Cancelled"}}
    ]
  }
}
```

`all` and `any` take nonempty lists; `not` takes exactly one expression. Groups
contain only their group key. JSON/mapping input uses these wire names, not the
Python constructor names `conditions` or `condition`.

## Operators

| `op` | `value` | Meaning |
| --- | --- | --- |
| `eq`, `ne` | null, boolean, finite number or string | Type-aware equality/inequality |
| `in` | Nonempty scalar list | Membership |
| `gt`, `gte`, `lt`, `lte` | Finite number | Numeric ordering; strings/booleans are not converted |
| `contains`, `starts_with`, `ends_with` | String | Case-sensitive text match |
| `regex` | String | Rust regex; `(?i)` enables case-insensitive matching |
| `is_empty`, `not_empty` | Omit `value` | Null and empty string are empty |

Comparisons have exactly `column`, `op`, `value`; emptiness checks have only
`column`, `op`. `eq null` matches only null, not empty text. Regexes do not support
backreferences or lookarounds. Regex validation happens before a scan starts.
See [Limits & Errors](limits.md) for nesting, rule and regex size limits.

## Returned columns

Without `select`, columns referenced anywhere in `where` are returned, including those inside
`any` and `not`. All referenced names must be available in a table; a missing
column is not treated as an empty value. Unreferenced columns are not converted
or returned.

Automatic tables return columns in physical order. An explicit source returns
selected aliases in binding order. Matching iterators add no metadata; event records identify file/sheet/table.
Identical records are not deduplicated. Cell types and numeric precision are described in
[Limits & Errors](limits.md#cell-values).

## Python models

Use public imports from `chooong.datasift`:
`ScalarCondition`, `MembershipCondition`, `NumericCondition`, `TextCondition`,
`EmptyCondition`, `AllOf(conditions=...)`, `AnyOf(conditions=...)`,
`Not(condition=...)` and `FilterMask`. `Operator` is a `StrEnum`.
See [Python API](python-api.md) for readers and results.


## Projection and validation

```json
{
  "sheet": null,
  "header": {"anchors": ["CustomerID", "Amount", "Country"]},
  "select": ["Country", {"pattern": "^Amount"}],
  "required": ["CustomerID", "Amount"],
  "defaults": {"Country": "UNKNOWN", "Amount": "0.00"},
  "types": {"Amount": {"type": "decimal", "convert": true}}
}
```

`where` can be omitted: all valid data rows match. Without both `where` and
`select`, all detected columns are returned. `select: ["*"]` returns every
bound column; literal names and `{ "pattern": "..." }` entries can be mixed.
Entries expand in list order, regex/wildcard matches in physical/binding order;
first occurrence wins. Unknown literal names and regexes without matches fail
schema binding: the affected table is quarantined, independent tables continue,
and the scan ends with `SCHEMA_MISMATCH` and `complete=false`. An explicit
source uses its aliases. Filter columns need not
appear in output.

The pipeline binds headers, classifies rows, preserves originals, applies defaults,
converts configured types, validates required/type rules, evaluates `where`, routes
matched/rejected records, then projects matches. Defaults replace only null and
empty strings; zero and false remain intact. Missing columns are schema errors,
not empty cells. Defaults cannot invent unbound columns. Row errors never replace
nonempty invalid values or stop the scan.

`schema_policy` is `per_table` (independent schemas, default) or `strict` (each
bound schema must have the same names as the first schema; mismatches quarantine
that table and make the final scan incomplete).

## Types and exact values

Types are `string`, `integer`, `float`, `number`, `boolean`, `null`, `decimal`,
`date`, `datetime`, `currency_code`, and `money`. `is_type` and `not_type` use a
`value` containing one of those names and compose with all boolean operators.
They inspect effective values after configured conversions.

Each entry in `types` has `type`, optional `convert` (default false), `currency`
(ISO-4217), `locale` (`de-DE`/`en-US`), and `format` (chrono strftime for temporal
text). Conversion must be enabled explicitly. Native styled dates retain their
source type. Raw OOXML numbers use invariant decimal syntax, regardless of the
text locale. Money can obtain currency from an explicit ISO code in text or a
cell format, or a configured code. Symbols alone never choose a currency.
Grouping separators must have three-digit groups. Integer conversion cannot
truncate; float conversion rejects inexact representations such as decimal 0.1.
Null is allowed unless the column is required.

Decimal uses an exact 96-bit coefficient with scale 0..28. Values outside that
range reject, rather than round. OOXML numeric lexemes are retained for explicit
conversion; precision already lost when Excel stored a numeric value cannot be
recovered. Use text cells for higher precision at the source.

NDJSON and comparison literals use tagged objects:

```json
{"type": "decimal", "value": "1234.560000000000000000000001"}
```

```json
{"type": "money", "amount": "1234.56", "currency": "EUR"}
```

Dates use `{"type":"date","value":"2026-11-01"}`; datetime uses
`{"type":"datetime","value":"2026-11-01T12:30:00.123456789"}`.
Equality/membership and ordering accept these objects. Money ordering/equality
requires identical currencies; no exchange-rate conversion occurs. Decimal and
money never use floating point arithmetic. Python matching rows expose `Decimal`,
`Money(amount: Decimal, currency: str)`, `date`, and `datetime` values.

Date conversion accepts ISO text, explicit text formats or Excel serials using
the workbook's 1900/1904 system. Excel's fictitious serial day 60 in the 1900
system rejects. Fractional days are exact to nanoseconds or reject; `date` rejects
a nonzero time. Excel datetimes represent local civil time, not UTC instants;
no timezone is invented. RFC3339 offsets are preserved; comparisons between offset datetimes compare
instants. Local and offset datetimes are not implicitly mixed. Python matching
rows use `PreciseDateTime(value: str)` when nanoseconds exceed datetime precision;
event records and file exports also preserve them.
