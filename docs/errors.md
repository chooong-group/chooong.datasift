# Errors and Resource Limits

Mask validation rejects unknown fields, unsupported operators and wrong types.
Initialization errors are `ValueError` (including Pydantic `ValidationError`).
Mask file reads can raise `OSError` or `UnicodeError`. Scanning errors after
initialization are `RuntimeError`; already delivered rows are not rolled back.
Invalid regexes fail before iterator return, including an empty workbook.

A named-sheet scan resolves its first schema eagerly. An all-sheet scan validates
metadata/filter first, then resolves schemas during iteration. Later tables or
sheets can fail after earlier matching batches. Prefer the CLI's `--output` for
an atomically replaced result file. Stdout may be partial on failure.

Selected malformed cell values, ambiguous selected header names and corrupt ZIP/XML
remain errors. Before the first schema is found, cell values are decoded while
searching. Afterwards, outside active columns only valid text header candidates
are considered. Unselected invalid values do not become records or headers.
Explicit sources skip conversion outside their range but still validate XML.

Current limits:

| Resource | Limit |
| --- | --- |
| Batch size | 1..65536 |
| Shared-strings XML | 512 MiB |
| Metadata XML part | 16 MiB |
| Cell text | 2 MiB |
| XML nesting | 128 |
| Expression nesting | 64 |
| Rules in one `all`/`any` group | 10000 |
| Regex UTF-8 bytes | 4096 |

There are two queued worker messages plus worker/consumer state. Active tables
have non-overlapping intervals within at most 16384 columns. XML parsing buffers
a token before the text-size check, so this is not an absolute hostile-input RAM
limit. Apply external process/RAM/time limits where needed.

Close iterators when stopping early. Do not consume/close one iterator concurrently.
There is no durable replay identifier; a repeated scan rereads the file. Atomic
rename preserves an old output on ordinary failures but does not guarantee
power-loss durability. A hard crash may leave a temporary output file.
