# Filter models

`FilterMask` is the canonical v1 contract; there is no version field.
Unknown fields, coercible-but-invalid scalar types and unsupported operators fail
validation. Models are frozen. Generate machine-readable contracts as described
in [JSON Schema](json-schema.md). The native engine adds semantic validation,
including regex syntax, currency codes, source bounds and schema binding.

## FilterMask and Rules

`FilterMask` extends `Rules` with these fields:

| Field | Default / constraint |
| --- | --- |
| `sheet` | Required; nonblank string selects one worksheet, null selects all |
| `source` | null; one `TableSource` |
| `sources` | null; nonempty list/tuple of `TableSource`; mutually exclusive with `source` |
| `csv` | `CsvConfig()` |
| `file_errors` | `"fail"` or `"continue"`; default `"fail"` |
| `schema_policy` | `"per_table"` or `"strict"`; default `"per_table"` |

`Rules` defines the shared rule set and optional per-source replacement:

| Field | Default / constraint |
| --- | --- |
| `where` | null; an `Expression` |
| `select` | null; nonempty ordered tuple/list of strings or `RegexSelection` |
| `required` | Empty tuple; bound column names that must be nonempty |
| `defaults` | Empty mapping; bound column names to scalar/exact literals |
| `types` | Empty mapping; bound column names to `TypeRule` |
| `header` | `HeaderConfig()` |
| `row_policy` | `RowPolicy()` |

`schema_policy="strict"` requires every bound schema to have the same names as
the first schema, including across files. `file_errors="continue"` continues
remaining files after technical failures but still ends with an error.
[Errors](../reference/errors.md) defines incomplete scans and quarantine.

## Expressions and operators

`AllOf(conditions=...)` serializes as `{"all": [...]}`; `AnyOf(conditions=...)`
as `{"any": [...]}`; `Not(condition=...)` as `{"not": ...}`. Groups contain only
their group key. `all`/`any` require 1–10000 children. Mapping/JSON inputs must
use the wire keys, not `conditions`/`condition`.

```json
{
  "sheet": null,
  "where": {"all": [
    {"column": "Amount", "op": "gte", "value": 1000},
    {"any": [
      {"column": "Country", "op": "eq", "value": "DE"},
      {"column": "Country", "op": "eq", "value": "AT"}
    ]},
    {"not": {"column": "Status", "op": "eq", "value": "Closed"}}
  ]}
}
```

A comparison has exactly `column`, `op`, `value`, except emptiness checks omit
`value`. `column` is a bound name after normalization/indexing.

| Operator | Model | Value and semantics |
| --- | --- | --- |
| `eq`, `ne` | `ScalarCondition` | Scalar or exact literal; type-aware equality/inequality |
| `in` | `MembershipCondition` | Nonempty tuple/list of scalar/exact literals; membership |
| `gt`, `gte`, `lt`, `lte` | `NumericCondition` | Finite number or exact literal; compatible numeric/temporal ordering |
| `contains`, `starts_with`, `ends_with` | `TextCondition` | String; case-sensitive match |
| `regex` | `TextCondition` | Rust regex string; `(?i)` enables case-insensitive matching |
| `is_empty`, `not_empty` | `EmptyCondition` | No value; null and empty string count as empty |
| `is_type`, `not_type` | `TypeCondition` | `DataType`; inspect effective types |

Strings and booleans are not implicitly numeric. `eq null` matches null, not
empty text. Integers/floats compare numerically, subject to numeric precision;
large i64/float equality is guarded beyond 2^53. Rust regexes do not support
lookarounds or backreferences. [Limits](../reference/limits.md) bounds size/depth;
[data types](../concepts/data-types.md) defines exact literals and currency rules.

## Projection

Omit `where` to match all valid data rows. Without `select`, return names referenced
anywhere in `where`; without both, return every bound column. Unreferenced fields
are neither converted nor returned in the simple predicate-only path.

`select` accepts literal names, `"*"` and `RegexSelection(pattern=...)`, serialized
as `{"pattern": "..."}`. Patterns are nonempty and at most 4096 characters;
native regex validation also limits UTF-8 bytes. Entries expand in list order,
regex/wildcard matches in physical/binding order; first occurrence wins.
Unknown names or a pattern with no matches are schema errors. Validation columns
need not be projected. Automatic output follows physical columns; explicit output
follows binding order unless `select` requests another order. No implicit deduplication
of records or addition of source metadata to matching rows.

## TableSource and ColumnBinding

| TableSource field | Default / constraint |
| --- | --- |
| `columns` | Empty tuple; at most 16384 `ColumnBinding` values |
| `header_start_row` | null; 1–1048576; mutually exclusive with nonempty `columns` |
| `first_column`, `last_column` | null; header-window bounds A–XFD |
| `data_start_row` | Required; 1–1048576 |
| `data_end_row` | null; inclusive, at least `data_start_row`, at most 1048576 |
| `skip_rows` | Empty tuple; physical/logical rows inside the data bounds |
| `name` | null; nonempty name, unique among named sources |
| `sheet` | null; nonempty worksheet restriction |
| `rules` | null; complete `Rules` replacement when supplied |

Supply either nonempty `columns` or `header_start_row`. A physical header window
must end before data begins; `first_column` cannot follow `last_column`.
`ColumnBinding(name=..., column=...)` requires a nonblank unique alias and an
uppercase absolute column A–XFD. Several aliases may share a physical column.
See [column mapping](../concepts/column-mapping.md) for extraction semantics.

## HeaderConfig

| Field | Default / constraint |
| --- | --- |
| `anchors` | Empty tuple; independent discovery names |
| `rows` | 1; physical header height, 1–32 |
| `trim`, `lowercase`, `collapse_whitespace`, `merged_fill` | false |
| `unicode` | null, `"NFC"` or `"NFKC"` |
| `aliases` | Empty mapping; normalized to canonical names |
| `min_columns` | 2; free-candidate minimum, 1–16384 |

Normalization, repeated-header rules and discovery modes are defined in
[table discovery](../concepts/table-discovery.md).

## Type rules

`DataType` values are `string`, `integer`, `float`, `number`, `boolean`, `null`,
`decimal`, `date`, `datetime`, `currency_code`, `money`.

`TypeRule` has required `type`, `convert=False`, `currency=None`, `locale=None`,
`format=None`. Currency is a valid uppercase ISO-4217 code and requires `money`.
Locale accepts `de-DE`/`en-US`. Format requires `date` or `datetime` and uses
chrono strftime syntax. [Data types](../concepts/data-types.md) is authoritative
for conversion, precision, nulls, currencies and date systems.

Exact literals have a discriminating `type` and strict string fields:

| Model | Wire fields |
| --- | --- |
| `DecimalLiteral` | `type="decimal"`, `value` |
| `MoneyLiteral` | `type="money"`, `amount`, `currency` (uppercase ISO-4217) |
| `DateLiteral` | `type="date"`, `value` |
| `DatetimeLiteral` | `type="datetime"`, `value` |

Native validation checks actual numeric/temporal contents before scanning.
Scalar values are strict strings, booleans, integers, finite floats or null.

## RowPolicy

`RowClass` values are `data`, `header`, `repeated_header`, `empty`, `comment`,
`total`, `separator`. `RowPolicy` has `include=(DATA,)`, `exclude=()`, `rules=()`.
`RowRule` requires `classification`, with `rows=()` and `where=None`;
at least one selector must be provided. Nonempty `rows` and `where` combine with
AND, rules match in declaration order, and exclusion takes precedence.
[Validation](../guides/validation.md#row-classification) shows the original-value
classification stage and structural-row behavior.

## CsvConfig

`CsvConfig` fields are `encoding="utf-8"`, `delimiter=","`, `quote='"'`,
`header=True`. Delimiter/quote are distinct one-byte ASCII characters. The native
encoding decoder validates the encoding label. `header=False` needs a source
declaration; it does not enforce
column-binding mode; [CSV](../guides/csv.md) defines logical record/header semantics.
