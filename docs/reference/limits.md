# Limits

## Supported inputs

XLSX/XLSM must be ZIP archives with UTF-8 XML and `xl/workbook.xml`.
CSV supports the [configured encodings and quoting](../guides/csv.md).
XLS, XLSB, encrypted workbooks, formula calculation and writing Excel files are
unsupported. Macros/external links are not executed. Formulas supply cached
results only; missing caches are null. Missing worksheet rows are not synthesized.

## Enforced bounds

| Resource | Limit |
| --- | --- |
| Batch size | 1–65536 |
| Excel columns / maximum CSV record width | 16384 |
| Excel row number / explicit source row bounds | 1–1048576 |
| CSV logical record counter | u32 (maximum 4294967295) |
| Physical header rows | 1–32 |
| Shared-strings XML | 512 MiB |
| Workbook metadata XML part | 16 MiB |
| Cell text | 2 MiB |
| XML nesting | 128 |
| Expression nesting | 64; compilation rejects depth 64 |
| Children in one `all`/`any` | 10000 |
| Regex UTF-8 bytes | 4096 |
| Compiled regex size | 8 MiB |
| Table explanations per scan | 16384 |
| Diagnostics per scan | 16384 |
| Merged ranges per worksheet | 16384 |
| Recovery journal bytes | 16384 |

Exceeding a bound produces an error rather than silently dropping data.
Free-discovery header windows and non-overlapping automatic regions are bounded
by worksheet width. Explicit sources may overlap intentionally.

CSV transcoding has an 8 KiB input buffer. CSV records and XML tokens can be
allocated by the format parser before size checks, so these are not an absolute
hostile-input process/RAM cap. Use external process memory/time limits for
untrusted files. Shared strings, metadata, active schemas, the largest parsed
record and queued batches all consume memory; see [streaming](../concepts/streaming.md).

Exports require disk for staged results and one additional complete output set
while verified private snapshots are prepared. Recovery copies stream from file
handles; output files are not loaded into RAM. See [file safety](file-safety.md).

Numeric, currency and temporal ranges are defined in
[data types](../concepts/data-types.md), without implying decimal precision for
unconfigured floating-point values.
