# CLI

```bash
chooong-datasift INPUT.xlsx MASK.json [--batch-size 1024] [--output OUTPUT.ndjson]
python -m chooong.datasift INPUT.xlsx MASK.json
```

XLSM uses the same command. `MASK.json` is a UTF-8 [JSON filter](contract.md).
The default batch size is 1024; see [valid limits](limits.md#resource-limits).
Without `--output`, records are written to stdout as NDJSON. Errors use stderr
and omit cell values.

## File output

`--output` writes a temporary file alongside the destination, flushes/fsyncs it,
and atomically replaces the destination after the complete scan succeeds.
A scan failure preserves the previous destination and removes the temporary
file. Input and mask cannot be used as the output path; aliases are resolved.

Concurrent successful writers use last-rename-wins. A hard process crash can
leave a temporary file, and replacement is not a power-loss durability guarantee.
There is no persistent replay identifier; repeating the command scans again.
Stdout can contain partial results on failure.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Filter, scan or file error |
| 2 | Invalid command-line arguments |

`Filterfehler (...)` is a generic error message that avoids exposing input values.
Python callers receive the underlying [exception](limits.md#errors).
