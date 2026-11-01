# JSON Filters

A mask contains `sheet`, `where` and an optional `source`. `FilterMask` is the
canonical input model; `FilterMask.model_json_schema(by_alias=True)` generates its
JSON schema. The format is v1 with no version field. Unknown fields, invalid types
and unsupported operators are rejected.

| Field | Required | Value |
| --- | --- | --- |
| `sheet` | Yes | Nonblank worksheet name, or `null` for all worksheets |
| `where` | Yes | One expression, defined below |
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

Only columns referenced anywhere in `where` are returned, including those inside
`any` and `not`. All referenced names must be available in a table; a missing
column is not treated as an empty value. Unreferenced columns are not converted
or returned.

Automatic tables return columns in physical order. An explicit source returns
selected aliases in binding order. No sheet/table metadata is added; identical
records are not deduplicated. Cell types and numeric precision are described in
[Limits & Errors](limits.md#cell-values).

## Python models

Use public imports from `chooong.datasift`:
`ScalarCondition`, `MembershipCondition`, `NumericCondition`, `TextCondition`,
`EmptyCondition`, `AllOf(conditions=...)`, `AnyOf(conditions=...)`,
`Not(condition=...)` and `FilterMask`. `Operator` is a `StrEnum`.
See [Python API](python-api.md) for readers and results.
