# Limits & Errors

## Formats

DataSift reads XLSX/XLSM ZIP archives with UTF-8 XML and `xl/workbook.xml`.
There is no XLS/XLSB, encryption or formula calculation. Formula caches are used; no cache means null. Explicit temporal/money rules support numeric styles and workbook date systems. Without type configuration the existing scalar output is preserved. Macros and external links
are not executed. Missing rows are not synthesized.

For header/layout ambiguity and comment handling, see [Excel Layouts](layouts.md).

## Cell values

Without type configuration cells are `str | bool | int | float | None`. Configured exact types are described in [JSON Filters](contract.md#types-and-exact-values). Empty cells become `None`; empty text
stays `""`. Excel error cells remain error strings. Numbers use i64 integers or
IEEE-754 f64, not decimal money arithmetic. Legacy numeric ordering retains its numeric semantics; explicit decimal/money ordering is exact. Use string cells and equality for exact IDs beyond floating-point
precision. Strings and booleans are not implicitly converted to numbers.

## Errors

Invalid masks raise `ValueError`, including Pydantic `ValidationError`; reading
mask files can raise `OSError` or `UnicodeError`. Regexes are validated at reader
initialization, even for an empty workbook; the row generator initializes lazily.
See [Python API](python-api.md#iterators).

Scan failures after initialization raise `RuntimeError`. These include malformed
selected cell values, ambiguous selected headers, corrupt ZIP/XML and late errors
in another table or worksheet. Already delivered rows are not rolled back.
For file output that preserves a previous result on scan failure, use
[CLI `--output`](cli.md#file-output).

During automatic discovery, cell values are decoded until the first schema is
found. Afterwards, valid text outside active columns can identify new headers;
unselected invalid values do not become header candidates. Explicit sources skip
conversion outside their scope but still check XML structure.

## Resource limits

| Resource | Limit |
| --- | --- |
| Batch size | 1..65536 |
| Shared-strings XML | 512 MiB |
| Metadata XML part | 16 MiB |
| Cell text | 2 MiB |
| XML nesting | 128 |
| Expression nesting | 64 |
| Rules in one `all`/`any` | 10000 |
| Regex UTF-8 bytes | 4096 |

Whole worksheets are not materialized, but shared strings are held in memory.
Memory also includes active schemas/filters, the largest XML token/row, batches
and two queued worker messages. Automatic tables have non-overlapping intervals within 16384 columns; explicit
sources may intentionally overlap. Compressed file size does not bound RAM use. The parser
buffers a token before enforcing text size, so these checks do not provide an
absolute hostile-input memory bound. Apply external process/RAM/time limits
when processing untrusted workbooks.


Additional limits: at most 16384 table explanations and diagnostics per scan,
32 physical header rows, and 16384 merged ranges per worksheet. These limits fail
with a technical error rather than discard evidence. CSV transcoding uses an
8 KiB input buffer; individual CSV records and XML tokens are checked after the
format parser reads them. These are controlled streaming limits, not an absolute
hostile-input process memory cap. Parquet schema is fixed and independent of table
count. Native date/time conversion is exact to nanoseconds; Python datetime alone
cannot represent the last three nanosecond digits, so those matching values use
`PreciseDateTime`.
