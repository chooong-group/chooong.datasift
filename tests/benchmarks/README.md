# Benchmark suite

The [benchmark guide](../../docs/development/benchmarks.md) is the canonical
reference for installed-wheel setup, workloads, baseline comparisons and report
interpretation. Tests here run real Rust-backed scans in isolated Python processes.
Normal pytest excludes expensive `benchmark` cases; select them with `-m benchmark`.

Shared workload models, generators, runner and worker live in this directory.
Do not infer platform-wide performance guarantees from one local result.
