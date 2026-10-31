"""Validated v1 filter contract and immutable result values."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

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


class FilterMask(_Model):
    sheet: Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]
    header_row: Annotated[StrictInt, Field(ge=1, le=1048576)] = 1
    where: Expression


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
