"""Alternating baseline/candidate runs with fresh process RSS per sample."""

import hashlib
import os
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from scripts.artifacts import PROBE, Probe
from tests.benchmarks.generate import generate
from tests.benchmarks.models import (
    BuildProfile,
    Case,
    Environment,
    Measurement,
    Report,
    Result,
    Summary,
)

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def processor() -> str:
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    if platform.system() == "Linux":
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or "unknown"


def environment(
    executable: Path, profile: BuildProfile, reference: str | None = None
) -> Environment:
    probe = Probe.model_validate_json(
        subprocess.check_output([str(executable), "-I", "-c", PROBE], text=True)
    )
    if not probe.native_origin.endswith((".so", ".pyd")):
        raise ValueError("Benchmark interpreter must load an installed native extension")
    digest = hashlib.sha256()
    paths = (
        _git("ls-tree", "-r", "--name-only", reference, "src", "datasift-core")
        if reference
        else _git("ls-files", "src", "datasift-core", "tests/benchmarks")
    ).splitlines()
    for name in sorted(paths):
        path = ROOT / name
        content = (
            subprocess.check_output(["git", "show", f"{reference}:{name}"], cwd=ROOT)
            if reference
            else path.read_bytes()
        )
        digest.update(name.encode())
        digest.update(content)
    return Environment(
        system=platform.system(),
        os_version=platform.platform(),
        machine=platform.machine(),
        processor=processor(),
        cpu_count=os.cpu_count(),
        python=probe.python,
        python_executable=str(executable),
        rust_toolchain=_git("show", "HEAD:rust-toolchain.toml"),
        build_profile=profile,
        commit=_git("rev-parse", reference or "HEAD"),
        source_sha256=digest.hexdigest(),
        dirty=bool(_git("status", "--porcelain")) if reference is None else False,
    )


def summarize(case: Case, samples: list[Measurement]) -> Summary:
    seconds = [sample.scan_seconds for sample in samples]
    median = statistics.median(seconds)
    return Summary(
        median_seconds=median,
        stdev_seconds=statistics.stdev(seconds),
        rows_per_second=case.rows / median,
        peak_rss_bytes=max(sample.peak_rss_bytes for sample in samples),
        samples=tuple(samples),
    )


class Session:
    def __init__(
        self,
        directory: Path,
        candidate: Path,
        baseline: Path | None,
        baseline_ref: str | None,
        repeats: int = 3,
        warmups: int = 1,
        profile: BuildProfile = BuildProfile.UNKNOWN,
    ) -> None:
        if repeats < 3 or warmups < 1:
            raise ValueError("At least one warmup and three measured runs are required")
        if (baseline is None) != (baseline_ref is None):
            raise ValueError("Baseline interpreter and released commit must be supplied together")
        self.directory = directory
        self.candidate = candidate
        self.baseline = baseline.absolute() if baseline else None
        if self.baseline == candidate.absolute():
            raise ValueError("Baseline must be installed in a separate interpreter environment")
        self.repeats = repeats
        self.warmups = warmups
        self.environment = environment(candidate, profile)
        self.baseline_environment = (
            environment(baseline, profile, baseline_ref) if baseline else None
        )
        if self.baseline_environment is not None:
            base = self.baseline_environment
            if (base.system, base.machine, base.python) != (
                self.environment.system,
                self.environment.machine,
                self.environment.python,
            ):
                raise ValueError(
                    "Baseline and candidate must use the same OS, architecture and Python version"
                )
        self.results: list[Result] = []
        directory.mkdir(parents=True, exist_ok=True)

    def _sample(self, executable: Path, case: Case, source: Path) -> Measurement:
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            suffix = ".parquet" if case.mode == "parquet" else ".ndjson"
            output = Path(temporary) / ("matched" + suffix)
            started = time.perf_counter()
            process_start_ns = time.time_ns()
            environment = {
                name: os.environ[name]
                for name in ("PATH", "SystemRoot", "TEMP", "TMP", "TMPDIR")
                if name in os.environ
            }
            result = subprocess.check_output(
                [
                    str(executable),
                    "-m",
                    "tests.benchmarks.worker",
                    case.model_dump_json(),
                    str(source),
                    str(output),
                ],
                cwd=ROOT,
                env=environment,
                text=True,
            )
            elapsed = time.perf_counter() - started
            measured = Measurement.model_validate_json(result)
            return measured.model_copy(
                update={"process_seconds": elapsed, "process_start_ns": process_start_ns}
            )

    def measure(self, case: Case) -> Result:
        existing = next((result for result in self.results if result.case == case), None)
        if existing is not None:
            return existing
        generator_hash = hashlib.sha256(
            Path(__file__).with_name("generate.py").read_bytes()
        ).hexdigest()
        name = (
            f"{generator_hash[:16]}-{case.format}-{case.rows}-"
            f"{case.hit_percent}-{case.filter}-{case.seed}.{case.format}"
        )
        source = self.directory / name
        if not source.exists():
            generate(source, case)
        executables = [self.candidate] if self.baseline is None else [self.candidate, self.baseline]
        for _ in range(self.warmups):
            for executable in executables:
                self._sample(executable, case, source)
        candidate_samples: list[Measurement] = []
        baseline_samples: list[Measurement] = []
        for repeat in range(self.repeats):
            for executable in executables if repeat % 2 == 0 else reversed(executables):
                sample = self._sample(executable, case, source)
                (candidate_samples if executable == self.candidate else baseline_samples).append(
                    sample
                )
        candidate = summarize(case, candidate_samples)
        baseline = summarize(case, baseline_samples) if baseline_samples else None
        result = Result(
            case=case,
            candidate=candidate,
            baseline=baseline,
            median_ratio=candidate.median_seconds / baseline.median_seconds if baseline else None,
        )
        self.results.append(result)
        return result

    def write(self, complete: bool) -> None:
        report = Report(
            complete=complete,
            environment=self.environment,
            baseline_environment=self.baseline_environment,
            warmups=self.warmups,
            repeats=self.repeats,
            results=tuple(self.results),
        )
        status = "complete" if complete else "incomplete (a benchmark failed)"
        (self.directory / "results.json").write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        lines = [
            "# DataSift performance measurements",
            "",
            f"Status: {status}.",
            f"Platform: {self.environment.system} {self.environment.machine}; "
            f"Python {self.environment.python}.",
            f"Commit: {self.environment.commit}; "
            f"source SHA-256: {self.environment.source_sha256}; dirty: {self.environment.dirty}.",
            "One warmup and at least three isolated runs per case; generation excluded. "
            "Peak RSS includes interpreter/imports.",
            "Rust scan time includes channel backpressure. "
            "Native mode includes the PyO3 bridge and serialization.",
            "Ratios describe this machine and interpreter only; "
            "no automatic performance thresholds are inferred.",
            "Initial baseline; no released comparison supplied."
            if self.baseline is None
            else "Baseline/candidate runs alternate on this machine.",
            "",
            "| Case | Rows/s | Median s | Stddev s | Peak RSS MiB | Candidate/baseline time |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for result in self.results:
            value = result.candidate
            ratio = f"{result.median_ratio:.3f}" if result.median_ratio is not None else "n/a"
            lines.append(
                f"| {result.case.identifier} | {value.rows_per_second:.0f} | "
                f"{value.median_seconds:.6f} | {value.stdev_seconds:.6f} | "
                f"{value.peak_rss_bytes / 1024**2:.2f} | {ratio} |"
            )
        (self.directory / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
