# Errors and incomplete scans

## Configuration and initialization

Invalid masks raise `ValueError`, including Pydantic `ValidationError`.
Mask-file reads can raise `OSError` or `UnicodeError`. Native regex syntax and
structural configuration are checked before batch/event iterators return.
Row generators initialize lazily at their first `next()`.

File opening, ZIP/XML metadata or initial schema failures can occur at readiness
or during iteration. Multi-file, all-sheet and free-discovery modes may return
an iterator before the failing file/schema is reached. Do not rely on every file
error being eager. Later scan failures raise `RuntimeError`; delivered rows
remain partial and are not rolled back.

## Row rejections

Invalid data in a bound column can reject a record without failing the scan.
Multiple reasons are retained; matching iterators omit rejects and event
iterators expose them unless `rejected=False`.

| `RejectCode` | Meaning |
| --- | --- |
| `REQUIRED_MISSING` | Required value is null or empty after defaults |
| `TYPE_MISMATCH` | Incompatible type or currency comparison |
| `CONVERSION_FAILED` | Requested conversion failed or would lose precision |
| `FILTER_NOT_MATCHED` | Predicate did not match |
| `SCHEMA_MISMATCH` | Table/region cannot bind its required schema |

Rejected event values preserve originals. A rejected data row alone does not
make `Statistics.complete` false.

## Schema failures

Missing projection/required/type/filter bindings, normalization/index collisions,
strict-schema mismatches and ambiguous free layouts quarantine affected tables
or regions. Independent regions continue, irrespective of `file_errors`.
Matching/event iterators can yield valid partial records, then raise `RuntimeError`
containing `SCHEMA_MISMATCH`. Final statistics have `complete=False`, including
when no data rows were available. Exports commit neither result after any schema
failure. A successful first batch never establishes complete success.

## File failures and diagnostics

`file_errors="fail"` stops on the first technical file error.
`file_errors="continue"` processes remaining files, records `FILE_ERROR`, sends
incomplete statistics and still raises at the end. No file failure is silently
turned into successful completion.

Diagnostic codes currently emitted are:

| Code | Meaning |
| --- | --- |
| `NO_SCHEMA` | No matching schema in a worksheet/input; can be a successful empty result |
| `AMBIGUOUS_HEADER` | Free discovery cannot safely identify a region |
| `SCHEMA_MISMATCH` | Invalid schema binding; scan incomplete |
| `FILE_ERROR` | Technical file failure under continue policy; scan incomplete |

Named-column discovery on a named worksheet without any complete header can fail
at initialization. With all-sheet scans, unrelated worksheets are skipped; no
matching schema can mean an empty result. Free discovery reports ambiguity rather
than inventing a schema. A header-only unconfirmed free candidate is ambiguous.

Structured reject/diagnostic codes are the programmatic interface; do not parse
human-readable exception text as a stable wire format. Diagnostic metadata includes
file/sheet/table identifiers; handle it according to the sensitivity of those names.
CLI exit behavior is defined in [CLI](../api/cli.md#exit-status-and-diagnostics).
[File safety](file-safety.md) defines what remains after a failed export/commit.
