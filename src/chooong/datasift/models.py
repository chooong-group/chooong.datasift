"""Validated v1 filter contract and immutable result values."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
ScalarValue = StrictStr | StrictBool | StrictInt | FiniteFloat | None


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class PreciseDateTime:
    """An ISO civil datetime retaining nanoseconds beyond Python datetime precision."""

    value: str


CellValue = ScalarValue | Decimal | Money | date | datetime | PreciseDateTime


class Operator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"
    IS_EMPTY = "is_empty"
    NOT_EMPTY = "not_empty"
    IS_TYPE = "is_type"
    NOT_TYPE = "not_type"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class DecimalLiteral(_Model):
    type: Literal["decimal"] = "decimal"
    value: StrictStr


class MoneyLiteral(_Model):
    type: Literal["money"] = "money"
    amount: StrictStr
    currency: Annotated[StrictStr, Field(pattern=r"^[A-Z]{3}$")]


class DateLiteral(_Model):
    type: Literal["date"] = "date"
    value: StrictStr


class DatetimeLiteral(_Model):
    type: Literal["datetime"] = "datetime"
    value: StrictStr


ExactLiteral = Annotated[
    DecimalLiteral | MoneyLiteral | DateLiteral | DatetimeLiteral, Field(discriminator="type")
]
InputValue = ScalarValue | ExactLiteral


class ScalarCondition(_Model):
    column: StrictStr
    op: Literal[Operator.EQ, Operator.NE]
    value: InputValue


class MembershipCondition(_Model):
    column: StrictStr
    op: Literal[Operator.IN] = Operator.IN
    value: Annotated[tuple[InputValue, ...], Field(min_length=1)]


class NumericCondition(_Model):
    column: StrictStr
    op: Literal[Operator.GT, Operator.GTE, Operator.LT, Operator.LTE]
    value: StrictInt | FiniteFloat | ExactLiteral


class TextCondition(_Model):
    column: StrictStr
    op: Literal[Operator.CONTAINS, Operator.STARTS_WITH, Operator.ENDS_WITH, Operator.REGEX]
    value: StrictStr


class EmptyCondition(_Model):
    column: StrictStr
    op: Literal[Operator.IS_EMPTY, Operator.NOT_EMPTY]


class DataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    CURRENCY_CODE = "currency_code"
    MONEY = "money"


class TypeCondition(_Model):
    column: StrictStr
    op: Literal[Operator.IS_TYPE, Operator.NOT_TYPE]
    value: DataType


class AllOf(_Model):
    conditions: Annotated[
        tuple[Expression, ...], Field(alias="all", min_length=1, max_length=10000)
    ]


class AnyOf(_Model):
    conditions: Annotated[
        tuple[Expression, ...], Field(alias="any", min_length=1, max_length=10000)
    ]


class Not(_Model):
    condition: Expression = Field(alias="not")


Condition = Annotated[
    ScalarCondition
    | MembershipCondition
    | NumericCondition
    | TextCondition
    | EmptyCondition
    | TypeCondition,
    Field(discriminator="op"),
]
Expression = Condition | AllOf | AnyOf | Not
AllOf.model_rebuild()
AnyOf.model_rebuild()
Not.model_rebuild()


RowNumber = Annotated[StrictInt, Field(ge=1, le=1048576)]
ExcelColumn = Annotated[
    StrictStr, Field(pattern=r"^(?:[A-Z]{1,2}|[A-W][A-Z]{2}|X[A-E][A-Z]|XF[A-D])$")
]


class ColumnBinding(_Model):
    """An output/filter name bound to an absolute Excel column, A through XFD."""

    name: Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]
    column: ExcelColumn


class TypeRule(_Model):
    type: DataType
    convert: StrictBool = False
    currency: Annotated[StrictStr, Field(pattern=r"^[A-Z]{3}$")] | None = None
    locale: Literal["de-DE", "en-US"] | None = None
    format: StrictStr | None = None


class RegexSelection(_Model):
    pattern: Annotated[StrictStr, Field(min_length=1, max_length=4096)]


class HeaderConfig(_Model):
    anchors: tuple[StrictStr, ...] = ()
    rows: Annotated[StrictInt, Field(ge=1, le=32)] = 1
    trim: StrictBool = False
    lowercase: StrictBool = False
    unicode: Literal["NFC", "NFKC"] | None = None
    collapse_whitespace: StrictBool = False
    aliases: dict[StrictStr, StrictStr] = Field(default_factory=dict)
    min_columns: Annotated[StrictInt, Field(ge=1, le=16384)] = 2
    merged_fill: StrictBool = False


class RowClass(StrEnum):
    DATA = "data"
    HEADER = "header"
    REPEATED_HEADER = "repeated_header"
    EMPTY = "empty"
    COMMENT = "comment"
    TOTAL = "total"
    SEPARATOR = "separator"


class RowRule(_Model):
    classification: RowClass
    rows: tuple[RowNumber, ...] = ()
    where: Expression | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> Self:
        if not self.rows and self.where is None:
            raise ValueError("Zeilenregel benötigt rows oder where")
        return self


class RowPolicy(_Model):
    include: tuple[RowClass, ...] = (RowClass.DATA,)
    exclude: tuple[RowClass, ...] = ()
    rules: tuple[RowRule, ...] = ()


class CsvConfig(_Model):
    encoding: StrictStr = "utf-8"
    delimiter: Annotated[StrictStr, Field(min_length=1, max_length=1)] = ","
    quote: Annotated[StrictStr, Field(min_length=1, max_length=1)] = '"'
    header: StrictBool = True


class Rules(_Model):
    where: Expression | None = None
    select: Annotated[tuple[StrictStr | RegexSelection, ...], Field(min_length=1)] | None = None
    required: tuple[StrictStr, ...] = ()
    defaults: dict[StrictStr, InputValue] = Field(default_factory=dict)
    types: dict[StrictStr, TypeRule] = Field(default_factory=dict)
    header: HeaderConfig = Field(default_factory=HeaderConfig)
    row_policy: RowPolicy = Field(default_factory=RowPolicy)


class TableSource(_Model):
    """Explicit extraction scope, independent of workbook header formatting."""

    columns: Annotated[tuple[ColumnBinding, ...], Field(max_length=16384)] = ()
    header_start_row: RowNumber | None = None
    first_column: ExcelColumn | None = None
    last_column: ExcelColumn | None = None
    data_start_row: RowNumber
    data_end_row: RowNumber | None = None
    skip_rows: tuple[RowNumber, ...] = ()
    name: Annotated[StrictStr, Field(min_length=1)] | None = None
    sheet: Annotated[StrictStr, Field(min_length=1)] | None = None
    rules: Rules | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if not self.columns and self.header_start_row is None:
            raise ValueError("source benötigt columns oder header_start_row")
        if self.columns and self.header_start_row is not None:
            raise ValueError("columns und header_start_row sind gegenseitig ausgeschlossen")
        if self.header_start_row is not None and self.header_start_row >= self.data_start_row:
            raise ValueError("Header muss vor dem Datenstart liegen")
        if self.data_end_row is not None and self.data_end_row < self.data_start_row:
            raise ValueError("data_end_row muss mindestens data_start_row sein")
        names = [binding.name for binding in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Ausgabenamen in source.columns müssen eindeutig sein")
        if any(
            row < self.data_start_row or (self.data_end_row is not None and row > self.data_end_row)
            for row in self.skip_rows
        ):
            raise ValueError("skip_rows müssen innerhalb des Datenbereichs liegen")
        return self


class FilterMask(Rules):
    sheet: Annotated[StrictStr, Field(min_length=1, pattern=r"\S")] | None
    source: TableSource | None = None
    sources: Annotated[tuple[TableSource, ...], Field(min_length=1)] | None = None
    csv: CsvConfig = Field(default_factory=CsvConfig)
    file_errors: Literal["fail", "continue"] = "fail"
    schema_policy: Literal["per_table", "strict"] = "per_table"

    @model_validator(mode="after")
    def validate_sources(self) -> Self:
        if self.source is not None and self.sources is not None:
            raise ValueError("source und sources sind gegenseitig ausgeschlossen")
        names = [source.name for source in self.sources or () if source.name is not None]
        if len(names) != len(set(names)):
            raise ValueError("Quellnamen müssen eindeutig sein")
        return self


@dataclass(frozen=True, slots=True)
class Row(Mapping[str, CellValue]):
    """A read-only row keyed by the actual workbook headers."""

    cells: Mapping[str, CellValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", MappingProxyType(dict(self.cells)))

    def __getitem__(self, key: str) -> CellValue:
        return self.cells[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.cells)

    def __len__(self) -> int:
        return len(self.cells)


class RecordKind(StrEnum):
    MATCHED = "matched"
    REJECTED = "rejected"


class RejectCode(StrEnum):
    REQUIRED_MISSING = "REQUIRED_MISSING"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    CONVERSION_FAILED = "CONVERSION_FAILED"
    FILTER_NOT_MATCHED = "FILTER_NOT_MATCHED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"


class RejectReason(_Model):
    code: RejectCode
    column: str | None = None


class ScanRecord(_Model):
    kind: RecordKind
    file: str
    sheet: str
    table: str
    row: int
    values: dict[str, InputValue]
    reasons: tuple[RejectReason, ...] = ()
    source_types: dict[str, DataType]


class TableExplanation(_Model):
    file: str
    sheet: str
    table: str
    header_row: int
    bindings: tuple[tuple[str, int], ...]
    defaults: tuple[str, ...]
    types: tuple[str, ...]
    type_rules: dict[str, TypeRule]
    header: HeaderConfig
    raw_headers: tuple[tuple[str, int], ...]
    data_start_row: int
    data_end_row: int | None


class Diagnostic(_Model):
    code: str
    file: str
    sheet: str | None = None
    table: str | None = None
    complete: bool | None = None


class Statistics(_Model):
    rows_read: int
    matched: int
    rejected: int
    defaults: int
    conversions: int
    reasons: dict[RejectCode, int]
    tables: tuple[TableExplanation, ...]
    diagnostics: tuple[Diagnostic, ...]
    complete: bool
    seconds: float
    row_classes: dict[RowClass, int]
