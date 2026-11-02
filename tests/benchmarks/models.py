"""Validated benchmark inputs and portable measurement records."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Format(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    XLSM = "xlsm"


class Filter(StrEnum):
    SIMPLE = "simple"
    LOGIC = "logic"
    REGEX = "regex"
    VALIDATION = "validation"
    DECIMAL = "decimal"
    MONEY = "money"


class BuildProfile(StrEnum):
    RELEASE = "release"
    UNKNOWN = "unknown"


class Mode(StrEnum):
    ROWS = "rows"
    EVENTS = "events"
    NATIVE = "native"
    NDJSON = "ndjson"
    PARQUET = "parquet"


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Case(Model):
    format: Format = Format.CSV
    rows: int = Field(default=100_000, ge=1, le=2_000_000)
    hit_percent: int = Field(default=5, ge=0, le=100)
    batch_size: int = Field(default=1024, ge=1, le=65536)
    filter: Filter = Filter.SIMPLE
    mode: Mode = Mode.ROWS
    seed: int = 42

    @property
    def identifier(self) -> str:
        return (
            f"{self.format}-{self.rows}-{self.hit_percent}-"
            f"{self.batch_size}-{self.filter}-{self.mode}-{self.seed}"
        )

    @property
    def expected_matches(self) -> int:
        full, rest = divmod(self.rows, 100)
        count = full * self.hit_percent + min(rest, self.hit_percent)
        if self.filter == Filter.VALIDATION:
            count -= sum(index % 100 < self.hit_percent for index in range(18, self.rows, 20))
            count -= sum(index % 100 < self.hit_percent for index in range(19, self.rows, 20))
        return count


class Measurement(Model):
    scan_seconds: float = Field(gt=0)
    pre_scan_seconds: float = Field(ge=0)
    process_seconds: float = Field(gt=0)
    process_start_ns: int = Field(default=0, ge=0)
    peak_rss_bytes: int = Field(gt=0)
    matched: int = Field(ge=0)
    rejected: int = Field(ge=0)
    rust_scan_seconds: float = Field(ge=0)
    input_sha256: str


class Summary(Model):
    median_seconds: float
    stdev_seconds: float
    rows_per_second: float
    peak_rss_bytes: int
    samples: tuple[Measurement, ...]


class Result(Model):
    case: Case
    candidate: Summary
    baseline: Summary | None = None
    median_ratio: float | None = None


class Environment(Model):
    system: str
    os_version: str
    machine: str
    processor: str
    cpu_count: int | None
    python: str
    python_executable: str
    rust_toolchain: str
    build_profile: BuildProfile
    commit: str
    source_sha256: str
    dirty: bool


class Report(Model):
    complete: bool
    environment: Environment
    baseline_environment: Environment | None = None
    warmups: int
    repeats: int
    results: tuple[Result, ...]
