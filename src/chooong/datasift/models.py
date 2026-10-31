"""Validated v1 filter contract and immutable result values."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
CellValue = StrictStr | StrictBool | StrictInt | FiniteFloat | None


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


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ScalarCondition(_Model):
    column: StrictStr
    op: Literal[Operator.EQ, Operator.NE]
    value: CellValue


class MembershipCondition(_Model):
    column: StrictStr
    op: Literal[Operator.IN] = Operator.IN
    value: Annotated[tuple[CellValue, ...], Field(min_length=1)]


class NumericCondition(_Model):
    column: StrictStr
    op: Literal[Operator.GT, Operator.GTE, Operator.LT, Operator.LTE]
    value: StrictInt | FiniteFloat


class TextCondition(_Model):
    column: StrictStr
    op: Literal[Operator.CONTAINS, Operator.STARTS_WITH, Operator.ENDS_WITH, Operator.REGEX]
    value: StrictStr


class EmptyCondition(_Model):
    column: StrictStr
    op: Literal[Operator.IS_EMPTY, Operator.NOT_EMPTY]


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
    ScalarCondition | MembershipCondition | NumericCondition | TextCondition | EmptyCondition,
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


class TableSource(_Model):
    """Explicit extraction scope, independent of workbook header formatting."""

    columns: Annotated[tuple[ColumnBinding, ...], Field(min_length=1, max_length=16384)]
    data_start_row: RowNumber
    data_end_row: RowNumber | None = None
    skip_rows: tuple[RowNumber, ...] = ()

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
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


class FilterMask(_Model):
    sheet: Annotated[StrictStr, Field(min_length=1, pattern=r"\S")] | None
    where: Expression
    source: TableSource | None = None


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
