# Public Contract v1

Distribution: `chooong.datasift`. Import: `chooong.datasift`. CLI:
`chooong-datasift` or `python -m chooong.datasift`. The unreleased version remains
0.1.0. Publication and external consumer migration are not part of this preparation.

Implementation modules are `models`, `reader` and the native `rust` extension.
The explicitly supported import paths are the exports of `chooong.datasift`;
implementation-module imports are not additional stable contracts. The Python
standard modules `__init__` and `__main__` keep their names.

## JSON mask

The format is implicitly v1, without a version field. `FilterMask` is the canonical
input model. `FilterMask.model_json_schema(by_alias=True)` generates its schema.
Unknown fields, operators and incorrect value types are rejected.

```json
{"sheet":"Data","where":{"column":"Country","op":"eq","value":"DE"}}
```

`sheet` is required. A nonempty sheet name selects exactly that worksheet; JSON
`null` scans all worksheets, including hidden ones, in workbook order. Chart sheets
without worksheet rows are skipped. Missing fields, blank strings and other types
are not substitutes for `null`. The string `"null"` is a literal sheet name.
Results have no extra metadata fields and are not deduplicated: identical records
on two sheets remain two records.

Without `source`, the engine searches each sheet for complete table headers
containing every name referenced by `where`. Text cells alone are header labels;
titles, numbers and incomplete rows before a schema are skipped. Literal XML CRLF
and CR line endings become LF for shared strings, inline strings and CDATA in
headers and data. Explicit character references such as `&#13;` retain the
referenced character. Names are not stripped or case-folded. Line breaks within
one header cell are part of its exact name.

After recognition, only mask columns are converted and returned, in physical
column order. Comments and neighboring fields do not become output columns.
A repeated complete header starts a new area and is not a record for that new
area. Real records identical to all selected header texts cannot be distinguished
in automatic mode; use explicit bindings/ranges for that case.

A named worksheet without a complete header raises `ValueError`. In an all-sheet
scan, unmatched sheets contribute no records and a workbook with no matching
schema gives an empty result. All referenced columns are required, including
inside `any` and `not`; missing columns are never assumed to be empty values.
With `source`, the same explicit bindings apply on each selected sheet. Only
aliases referenced by `where` are returned, in binding order.

## Multiple automatic tables

Tables may be beside one another, below one another or offset. A row with at least
two complete groups of the mask's literal names is split left to right into
independent schemas; each group contains each mask name exactly once. This needs
at least two distinct mask columns. Incomplete repetition patterns are not guessed;
a single row schema keeps its indexed-header semantics. A repeated single name
alone cannot distinguish neighboring tables from duplicate columns. Use explicit
sources for ambiguous/partial groups or horizontal schemas using internally
indexed mask names. Formatting is not a table oracle; headers distributed across
multiple physical rows are not reconstructed.

Each area binds and evaluates its own columns. A later complete header replaces
active areas whose intervals from first to last selected column overlap it.
Non-overlapping neighbors keep running, even with records in the same row as a
new header. Blank/comment rows do not infer a table end. Output follows workbook
order, then row number, then the table's leftmost selected column. Identical
schemas may share a batch; the batch is flushed before changing output column
order. Tables never add metadata fields or deduplicate records.

Rows below a header are evaluated by `where`. A comment with the same matching
values as a business record cannot be excluded by guessed formatting. Use a
stricter rule, an explicit range or `skip_rows` as appropriate.

Invalid filters, including Rust regexes, fail before iterator return. ZIP/XML
errors, ambiguous selected headers and malformed selected values remain errors.
Before the first schema is recognized, cell values are decoded during discovery.
Afterwards, valid text header candidates outside active columns may introduce
another schema; invalid unselected values do not become candidates or records.
Schemas on later sheets/tables can fail during iteration with `RuntimeError`.
Batches never cross sheet boundaries. The CLI's file replacement is atomic across
the entire scan. Shared strings are loaded once per workbook.

**Historical Greenfield breaking change:** `header_row` was removed and is rejected
as an unknown field. Remove it from older masks. Results contain only columns
referenced by `where`, rather than every header/source alias. The open-source
preparation does not change this existing behavior or bump the version.

## Explicit sources

`source` separates the extraction scope from the predicate. A table below
single/multiple header rows can be selected without interpreting those headings:

```json
{
  "sheet": "Data",
  "source": {
    "columns": [
      {"name": "Country", "column": "C"},
      {"name": "Amount", "column": "D"},
      {"name": "PreviousAmount", "column": "E"}
    ],
    "data_start_row": 7,
    "data_end_row": 10,
    "skip_rows": [8]
  },
  "where": {"column": "Amount", "op": "gte", "value": 100}
}
```

- `ColumnBinding(name, column)` binds a unique nonblank filter/output name to an
  absolute uppercase Excel column A..XFD. Different aliases may intentionally
  reference one physical column. Only aliases used by `where` are extracted.
- `TableSource.columns` is nonempty, with at most 16384 bindings. Its order controls
  output order. Header text is not treated as a schema in this mode, so duplicate,
  merged or physically multi-row headings can be bypassed explicitly. They are
  not automatically assembled or expanded.
- `data_start_row` is required; `data_end_row` is optional and inclusive. Both are
  in 1..1048576, with the end not preceding the start. Without an end, the rest of
  the worksheet is selected.
- `skip_rows` explicitly names comment/intermediate rows inside the data interval.
  Comments above the start are excluded already. Comments inside the interval
  need explicit skips, bounds or suitable predicates.
- An explicit source selects one region; use separate masks for multiple explicit
  regions. Automatic multi-table discovery applies only without `source`.
- Values outside the source are not converted/returned. XML structure, coordinates
  and resource limits are still checked, including beyond `data_end_row`. A corrupt
  XML tail remains an error.

## Duplicate headers

Within one automatic row schema, repeated exact labels receive suffixes starting
at 1 from left to right: `Amount`, `Amount` become `Amount_1`, `Amount_2`.
All occurrences are numbered; a third becomes `Amount_3`. Unique labels are
unchanged. Indexed names are used for both filters and output; the ambiguous
base `Amount` is not a valid filter name. Blank columns do not affect numbering.

A selected-name collision with an existing suffix label, such as `Amount_1` beside
two `Amount` columns, is rejected before that area's records. Explicit source
aliases can resolve the ambiguity. Nontext cells are not header labels. No
trimming or case normalization is performed. Explicit `source.columns.name`
aliases must already be unique and do not receive automatic suffixes. Unknown
source aliases are rejected; automatic schemas must supply all selected names.

The earlier local `__column_*` extra-output behavior was removed. Unnamed extra
data is not silently added to results.

## Predicates

| Expression/operator | Value and meaning |
| --- | --- |
| `all`, `any` | Nonempty expression lists; AND / OR |
| `not` | Exactly one expression; negation |
| `eq`, `ne` | JSON scalar: null, bool, number or string; type-aware |
| `in` | Nonempty list of scalars |
| `gt`, `gte`, `lt`, `lte` | Finite number; no string/boolean conversion |
| `contains`, `starts_with`, `ends_with` | Case-sensitive string |
| `regex` | Rust regex, at most 4096 UTF-8 bytes; `(?i)` is supported |
| `is_empty`, `not_empty` | No `value` field; null and empty string are empty |

Comparisons contain exactly `column`, `op`, `value`; emptiness checks only
`column`, `op`. Groups contain only their own group key. Expression nesting is
limited to 64 levels and one AND/OR group to 10000 rules. Regexes have no
backreferences or lookarounds. They are validated up front and prepared per
recognized table schema, not compiled per data row.

Python models: `ScalarCondition`, `MembershipCondition`, `NumericCondition`,
`TextCondition`, `EmptyCondition`, `AllOf(conditions=...)`, `AnyOf(conditions=...)`,
`Not(condition=...)`, `ColumnBinding`, `TableSource`, `FilterMask`. `Operator` is
a `StrEnum`. JSON/mapping callers must use the wire aliases, not Python-only names
such as `conditions` or `condition`.

## Results and lifecycle

`iter_matching_batches(path, mask, *, batch_size=1024)` returns a `BatchIterator`
yielding `list[Row]`, with `close()` and context-manager support. Sheet/filter
validation and regex checks occur before return. A named-sheet automatic scan
reads its first header eagerly; explicit sources validate their bindings without
reading actual header text. `iter_matching_rows` is a generator that initializes
on the first `next()`. Closed/exhausted iterators remain exhausted. Independent
scans have independent workers. Do not consume/close one iterator concurrently
from several threads.

`Row` is an immutable mapping supporting `row["Column"]` and `dict(row)`. Column
names depend on the input, so there is no static per-workbook record schema.
Cells contain `str | bool | int | float | None`, without a Pandas dependency.
Empty cells are `None`; empty text stays `""`. `eq null` matches only `None`.
Excel error cells remain error strings. Numbers use i64 or IEEE-754 f64, without
decimal money arithmetic or exactness guarantees beyond those representations.
Numeric order comparisons use f64, including for integers. Use string cells and
string equality for exact large IDs beyond floating-point precision.

Initialization errors: `ValueError` (including Pydantic `ValidationError`). Mask
file reads: `OSError`, or `UnicodeError` for invalid text encoding. Errors after
scan initialization: `RuntimeError`. Already returned batches are not rolled back.
CLI exit codes: success 0, scan/file errors 1, argument errors 2. CLI stderr omits
cell values; stdout contains NDJSON.

`--output` writes a separate temporary file in the target directory, flushes/fsyncs
it and atomically replaces the target. Ordinary failures preserve the previous
target and remove the temporary file. Concurrent successful writers use
last-rename-wins. There is no persistent replay ID; repeated scans reread the
file. Rename does not promise power-loss durability; a killed process can leave
a temporary file. Input/mask cannot be the output target; aliases/symlinks are
resolved for this check.

## Resources and format boundaries

XLSX/XLSM input with UTF-8 XML and `xl/workbook.xml`; worksheet paths are resolved
through relationships. No XLS/XLSB, encryption, formula evaluation, style/date
interpretation. Cached formulas are read; no cache means `None`. Numeric dates
remain serial numbers and ISO date cells strings. Macros/links are not executed.
Missing rows are not synthesized and merged regions are not expanded.

Memory includes shared strings, active schemas/compiled filters, the largest
XML token/row and bounded batches. Active areas have non-overlapping intervals
within at most 16384 Excel columns. Shared-strings XML is capped at 512 MiB,
metadata parts at 16 MiB, cell text at 2 MiB and XML depth at 128. Parsing buffers
a token before enforcing text limits, so this is not an absolute RAM limit for
malicious archives. Use external process/RAM/time limits for untrusted workbooks.
Batch size is 1..65536, with two queued worker messages plus worker/consumer state.

## Compatibility and consumers

This is a Greenfield adoption of the former PoC. `rust_xlsx_filter` and
`extract_rows` have no compatibility promise. Expression meaning is retained;
results are immutable `Row` objects. Direct repository consumers are the CLI,
examples, tests and benchmark. The old PoC is removed and remains only in Git
history. The open-source preparation does not alter the engine or public contract.
