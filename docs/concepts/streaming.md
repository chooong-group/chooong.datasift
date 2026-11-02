# Streaming and iterator lifetime

Rust parses input rows and evaluates rules. Matching iterators transfer only
matched values to Python; `scan_batches` transfers matched/rejected event records
through one ordered stream. A worker channel holds at most two queued messages;
a slow consumer applies backpressure.

## Memory

Whole worksheets are not materialized. Memory still includes workbook metadata,
shared strings, active schemas and filters, the largest parsed token/record,
current batches and queued messages. Compressed file size does not bound RAM.
Parsers may allocate a complete token before its size is checked; streaming is
not an absolute memory cap for hostile inputs. See [limits](../reference/limits.md).

`merged_fill` needs a streaming metadata pass before the worksheet data pass
because merge records may follow `sheetData`. Exports also need disk space for
stages and verified private copies; see [file safety](../reference/file-safety.md).

## Completion and cancellation

Use batch/event iterators as context managers. Close a row generator explicitly
when stopping early, for example with `contextlib.closing`. Close cancels its
worker; closed/exhausted iterators remain exhausted. Separate scans have separate
state. Do not consume or close the same iterator concurrently from several threads.

A first successful `next()` does not certify the whole file. A late failure can
follow valid records. Final statistics become available only when the worker has
sent them; a normal exhausted scan has `complete=True`. Schema failures and
`file_errors="continue"` retain final incomplete statistics and then raise.
Other early technical failures may leave statistics unavailable.

Matching batches flush before worksheet/schema order changes, so a batch does
not combine different worksheet output schemas. Event batches carry per-record
source metadata and may span such boundaries. [Python API](../api/python.md)
defines both iterator interfaces; [errors](../reference/errors.md) defines failure timing.
