# CLI

```bash
chooong-datasift INPUT.xlsx MASK.json [--batch-size 1024] [--output OUTPUT.ndjson]
python -m chooong.datasift INPUT.xlsx MASK.json
```

XLSM input is supported through the same path. `MASK.json` is a UTF-8 file using
the [JSON filter contract](contract.md). The batch size is an integer from 1 to
65536. Without `--output`, matching records are written to stdout as NDJSON.
Warnings/errors use stderr; cell values are excluded from CLI error messages.

With `--output`, the CLI writes a temporary file in the destination directory,
flushes/fsyncs it and atomically replaces the destination after success. A scan
failure preserves the previous target and removes its temporary file. Input and
mask cannot be the output destination; aliases are resolved for this check.

Exit codes: 0 for success, 1 for filter/scan/file failures, 2 for command-line
argument errors. A generic `Filterfehler (...)` message deliberately omits
potentially sensitive input values. Python callers receive the exception directly.

Stdout may contain partial results on failure. Already returned Python batches
are likewise not transactional. Concurrent successful writers to the same output
use last-rename-wins; there is no durable replay key. A hard process crash can
leave a temporary file, and atomic replacement is not a power-loss durability
promise. See [errors and resource limits](errors.md).
