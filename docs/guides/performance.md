# Performance and resource use

Rust performs parsing, discovery, conversion, filtering, projection and native
export. Matching iterators transfer only matched values into Python; event
iterators also transfer rejected records and source metadata. Throughput depends
on input format, worksheet shared strings, rule complexity, output and consumer
speed. There is no universal rows-per-second guarantee.

## Choose the processing path

| Need | API / guide | Tradeoff |
| --- | --- | --- |
| Write NDJSON or Parquet | [Native export](exporting.md) | Avoids Python-side record serialization; needs disk for staged output |
| Transform matches in Python | [Batch processing](batch-processing.md) | Larger batches reduce crossings but retain more rows at once |
| Inspect originals and rejections | [Table inspection](table-inspection.md) | Event envelopes carry more data than matching rows |
| Stop after a sample | [Iterator cleanup](batch-processing.md#stop-early-and-close) | Saves further work but does not certify complete input |

Start with the default `batch_size=1024`; supported values are 1–65536. Measure
your own workload before changing it. Reducing batch size does not cap total
RAM: workbook metadata, shared strings, active schemas and parser allocations
remain. Backpressure limits queued messages when the consumer is slow, not the
size of a parser token. See [streaming](../concepts/streaming.md) and
[enforced limits](../reference/limits.md).

Use the [benchmark procedure](../development/benchmarks.md) for reproducible
throughput, memory, scalability and export workloads. That page defines how to
run measurements; its workloads are not performance promises for user files.
`Statistics.seconds` includes worker backpressure and is not isolated CPU time.
