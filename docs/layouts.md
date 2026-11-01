# Excel Layouts

## Worksheets

A nonblank `sheet` string selects one worksheet; `null` scans all worksheets,
including hidden ones, in workbook order. The string `"null"` names a worksheet.
Chart sheets without worksheet rows are skipped.

A named sheet without a complete schema raises `ValueError`. With `sheet: null`,
unmatched worksheets contribute no rows; no matching schema anywhere means an
empty result. Explicit bindings apply unchanged on each selected worksheet.

## Automatic headers

Without `source`, the legacy default searches for every name referenced by
`where`. Independent anchors and fully automatic discovery are described under
[Extended discovery](#extended-discovery). Only text cells are header labels.
No top-level `header_row` setting is accepted.

Names match exactly by default; normalization is opt-in. A line break inside one cell
is part of the name, for example `"Amount\nEUR"`. Literal XML CRLF/CR becomes LF
in shared strings, inline strings and CDATA; character references preserve their
referenced character. Use `header.rows` for physical multiline headers and `merged_fill` for actual
merged header ranges, or explicit bindings.

Within one schema, duplicate labels receive indices from left to right:
`Amount`, `Amount` become `Amount_1`, `Amount_2`; unique names stay unchanged.
Use indexed names in the mask. The ambiguous base name and selected collisions
with an existing suffix label are rejected. Blank cells do not affect numbering.

## Multiple tables

A header row with at least two complete groups of the mask's literal names
identifies adjacent tables. Each group contains every referenced name once;
at least two distinct mask columns are needed. For example, the
[quickstart](index.md) selects `Country` and `Amount` from both C/D and H/I.
A repeated single name alone cannot distinguish adjacent tables from duplicate
columns. Partial groups or horizontal groups using indexed names may require
explicit bindings.

A later complete header replaces active tables whose intervals from first to
last selected column overlap it. Other neighboring tables continue, including
records on the same row as a new header. Blank rows and comments do not end a
table. Output follows worksheet order, row number, then leftmost selected column.

A complete header is structural, not a record for the table it starts. Records
identical to all selected header labels are indistinguishable in automatic mode;
use explicit bounds. Comments below a header are evaluated by `where`, just like
records. A comment that satisfies the predicate requires a stricter mask,
`skip_rows` or explicit bounds to exclude it.

## Explicit sources

Use `source` when positions are known or automatic discovery is ambiguous:

```json
{
  "sheet": "Data",
  "source": {
    "columns": [
      {"name": "Country", "column": "C"},
      {"name": "Amount", "column": "D"}
    ],
    "data_start_row": 5,
    "data_end_row": 7,
    "skip_rows": [5]
  },
  "where": {"column": "Amount", "op": "gte", "value": 1000}
}
```

On the quickstart workbook, this selects the first table, skips its comment and
returns amounts 1500 and 2000. Header text is not interpreted in this mode.

`ColumnBinding(name, column)` binds a nonblank, unique alias to an uppercase
absolute column A..XFD. Several aliases may refer to one physical column. There
must be 1..16384 bindings. Aliases referenced by the filter must exist in them;
[returned-column rules](contract.md#returned-columns) still apply.

`data_start_row` is required. `data_end_row` is optional and inclusive; omitting it
selects the remainder of the sheet. Row indices are 1..1048576, the end cannot
precede the start, and `skip_rows` must be inside those bounds. One source selects
one region; use `sources` for several explicit regions.

Values outside the selected scope are not converted. XML structure, coordinates
and resource limits are checked throughout the worksheet, even beyond the end
bound. A corrupt XML tail still fails the scan.


## Extended discovery

`header.anchors` explicitly defines the discovery schema independently of filters,
validation and projection. With no anchors and an existing `where`, the legacy
filter-name discovery remains. Without either, the first contiguous run of at
least `header.min_columns` (default 2) nonblank text cells establishes a schema.
Later exact repeated schemas are headers. This structural heuristic cannot
identify the semantic difference between an all-text record and a header;
use anchors or explicit bounds for ambiguous reports. Blank gaps separate
neighboring fully automatic schemas. Anchored schemas can also be recognized
side by side using repeated complete anchor groups. No names are invented.

Header options are `trim`, `lowercase`, `unicode` (`NFC`/`NFKC`),
`collapse_whitespace` (including line breaks), and `aliases` (normalized label to
canonical name), applied in that order except Unicode normalization comes first.
Rules refer to final canonical names. Normalization collisions fail closed.
`header.rows` (1..32) joins physical header rows with a space. In automatic mode
these are bounded sliding windows before the first table. Use header-bound
sources for independent multiline tables. `merged_fill: true` fills only actual
OOXML merged header ranges from their top-left values. It needs a streaming
metadata pass over worksheet XML before the data pass because merges can occur
after `sheetData`. It does not materialize worksheets.

## Multiple explicit sources

`source` and `sources` are mutually exclusive. Each source can have a unique
`name`, a `sheet` (null/omitted applies to every selected worksheet), and a full
`rules` object. Omitting `rules` uses common rules; providing it replaces the
complete common rule set with that object and its defaults. No implicit merge.
Explicit `columns` bind aliases without inspecting header text.

Alternatively omit `columns`, specify `header_start_row` and `data_start_row`,
and optionally `first_column`/`last_column` to bind a physical header window:

```json
{
  "sheet": null,
  "sources": [{
    "name": "sales",
    "sheet": "Data",
    "header_start_row": 3,
    "data_start_row": 5,
    "first_column": "C",
    "last_column": "E",
    "rules": {"header": {"rows": 2, "merged_fill": true}, "select": ["*"]}
  }]
}
```

Files sort lexically; worksheets follow workbook order, rows their physical
order, explicit sources their declaration order. Automatic tables sort left to
right. Overlapping explicit regions intentionally emit a record for each source;
identical records are retained. One worksheet stream serves all sources.

## Row classification

`row_policy.include` defaults to `["data"]`; `exclude` takes precedence.
Classes: `data`, `header`, `repeated_header`, `empty`, `comment`, `total`,
`separator`. Header and empty classifications are structural. Comments, totals
and separators require explicit rules; no business meaning is guessed.
`rules` are ordered, first match wins, and each contains `classification` plus
`rows` (physical row numbers), `where`, or both (AND). Conditions inspect original
values before defaults/conversion. Example:

```json
{"row_policy":{"rules":[{"classification":"comment","rows":[5]},
 {"classification":"total","where":{"column":"Name","op":"starts_with","value":"TOTAL:"}}]}}
```

Excluded structural rows do not enter the matched/rejected streams. Invalid
included data rows do enter rejects. Explain counts classifications separately.

## CSV

CSV uses the same bindings, row pipeline and rules. Cells initially contain text
or null; numeric/date conversions are explicit. `csv` accepts `encoding` (an
encoding_rs label, default UTF-8), `delimiter` (default comma), `quote` (default
ASCII double quote), and `header` (default true). BOM removal, quoted delimiters,
escaped quotes and embedded line breaks stream natively. Malformed encoding is
a technical error. `header: false` requires explicit source columns. CSV row
numbers are logical records, starting at 1, including a header. Excel limits do
not constrain the number of CSV records; explicit source bounds remain Excel
compatible. CSV uses the synthetic worksheet name `csv`.
