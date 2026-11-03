# Benchmarks

The benchmark suite measures real Rust-backed scans in isolated Python processes.
Inputs are generated once with seed 42, outside the timed scan. XLSX/XLSM fixtures
split data across worksheets before Excel's row limit. CSV and ZIP/XML generation
stream records without collecting the dataset.

Build a release wheel and install it into a separate environment before measuring:

```bash
uv build --wheel --out-dir candidate-dist
uv export --frozen --no-dev --no-emit-project --output-file candidate-dist/runtime-requirements.txt
uv venv --python 3.13 candidate-env
uv pip install --python candidate-env/bin/python --require-hashes -r candidate-dist/runtime-requirements.txt
uv pip install --python candidate-env/bin/python --no-deps candidate-dist/*.whl
uv pip check --python candidate-env/bin/python
uv run pytest tests/benchmarks/ -m benchmark \
  --benchmark-python "$PWD/candidate-env/bin/python" --benchmark-output benchmark-results --benchmark-build-profile release
```

On Windows use `candidate-env/Scripts/python.exe`. Normal `pytest` runs exclude
the `benchmark` marker; the command above runs the performance cases explicitly.

The suite sweeps 10k, 100k, 1M and 2M rows; 0/5/50/100% selectivity; batches of
64/1024/65536; XLSX, XLSM and CSV; simple, logical and regex filters; validation,
Decimal and Money; matched/rejected streams; and NDJSON/Parquet exports.
One warmup precedes three measured repetitions. Counts, completeness and output
integrity are checked. Reports contain median throughput, sample standard
deviation, peak process RSS, process launch timestamp, pre-scan/scan/process times,
native scan elapsed time,
input hashes, OS/hardware, Python, build profile and Git/source identity.

`results.json` and `results.md` are written to the selected output directory,
including partial results when a test fails. RSS includes interpreter and imports;
Rust scan elapsed time includes channel backpressure. Native mode measures the
PyO3 boundary and JSON serialization; it is not an isolated Rust CPU benchmark.
The memory sweep checks for growth large enough to retain the complete input's
row-pointer array; review sample ranges as well as throughput before concluding
that memory use is bounded. No universal timing threshold is applied.

For a previous released baseline, build and install its exact wheel into a second
environment with the same Python version, then add both options:

```text
--benchmark-baseline-python /absolute/path/to/baseline-env/bin/python \
--benchmark-baseline-ref vX.Y.Z
```

Baseline and candidate runs alternate on the same machine. Reports expose time
ratios without inventing regression thresholds. Without a released baseline the
report is an initial baseline, not a before/after comparison. Do not compare
measurements from different platforms. The manual **Performance measurements**
workflow follows the same procedure and uploads both reports; it never runs on
normal pushes or PRs. It is available in both private and public repositories.
