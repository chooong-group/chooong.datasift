# Batch processing and streaming

Consume batches incrementally when results do not fit in memory. Each matching
batch contains at most `batch_size` rows and does not combine different worksheet
output schemas. A bounded native channel applies backpressure when Python is
slower than the parser. Batch size bounds transferred rows, not total RAM.

## Process each batch

```python
from pathlib import Path

from chooong.datasift import (
    DataType, FilterMask, HeaderConfig, TypeRule, iter_matching_batches,
)

Path("batches.csv").write_text("ID,Amount\na,10\nb,20\nc,30\n", encoding="utf-8")
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("ID", "Amount")),
    types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
)
count = 0
total = 0
with iter_matching_batches("batches.csv", mask, batch_size=2) as batches:
    for batch in batches:
        assert 1 <= len(batch) <= 2
        for row in batch:
            amount = row["Amount"]
            assert isinstance(amount, int)
            count += 1
            total += amount
    statistics = batches.statistics
assert (count, total) == (3, 60)
assert statistics is not None and statistics.complete
```

No list of all results is retained. Production consumers can write to their own
sink inside the loop; DataSift's [native export](exporting.md) avoids Python-side
record serialization when NDJSON or Parquet is the intended result.

## Stop early and close

The row generator must also be closed when you stop early:

```python
from contextlib import closing

from chooong.datasift import iter_matching_rows

with closing(iter_matching_rows("batches.csv", mask, batch_size=1)) as rows:
    assert dict(next(rows)) == {"ID": "a", "Amount": 10}
assert list(rows) == []
# A new scan has independent state and starts at the beginning.
assert [row["ID"] for row in iter_matching_rows("batches.csv", mask)] == ["a", "b", "c"]
```

Batch/event iterators are context managers; leaving their context also cancels
unfinished work. Do not consume or close one iterator concurrently from several
threads. Use `scan_batches` when both matches and rejections are needed; it
provides one ordered stream with per-record metadata.

A first batch does not certify the input. Late errors can follow valid results;
see [error handling](error-handling.md). Shared strings, metadata, parsed tokens,
active schemas and queued batches consume memory. The
[streaming contract](../concepts/streaming.md) and [limits](../reference/limits.md)
define those bounds and the absence of a hard process-memory cap.
