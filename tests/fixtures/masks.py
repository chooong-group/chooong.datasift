"""Reusable deterministic test fixtures."""

from __future__ import annotations

from chooong.datasift import (
    AllOf,
    AnyOf,
    ColumnBinding,
    EmptyCondition,
    FilterMask,
    MembershipCondition,
    Not,
    NumericCondition,
    Operator,
    ScalarCondition,
    TableSource,
    TextCondition,
)
from tests.fixtures.excel import _LABELS


def sheet_mask(sheet: str | None = None) -> FilterMask:
    return FilterMask(
        sheet=sheet,
        where=AllOf(
            conditions=(
                ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
                EmptyCondition(column="Value", op=Operator.NOT_EMPTY),
            )
        ),
    )


def contract_mask() -> FilterMask:
    return FilterMask(
        sheet="Data",
        where=AllOf(
            conditions=(
                ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
                MembershipCondition(column="Status", value=("Active", "Open")),
                EmptyCondition(column="Customer", op=Operator.NOT_EMPTY),
            )
        ),
    )


def indexed_mask() -> FilterMask:
    return FilterMask(
        sheet="Data",
        where=AllOf(
            conditions=(
                NumericCondition(column="Revenue_1", op=Operator.GTE, value=1000),
                ScalarCondition(column="Revenue_2", op=Operator.EQ, value="Active"),
            )
        ),
    )


def table_mask(sheet: str | None = None) -> FilterMask:
    return FilterMask(
        sheet=sheet,
        where=AllOf(
            conditions=(
                AnyOf(
                    conditions=(
                        ScalarCondition(column=_LABELS[0], op=Operator.EQ, value="HR"),
                        ScalarCondition(column=_LABELS[0], op=Operator.EQ, value="OPS"),
                    )
                ),
                NumericCondition(column=_LABELS[1], op=Operator.GTE, value=900),
                Not(
                    condition=TextCondition(column=_LABELS[2], op=Operator.CONTAINS, value="review")
                ),
            )
        ),
    )


def pipeline_mask() -> dict[str, object]:
    return {
        "sheet": None,
        "header": {"anchors": ["ID", "Amount", "Country"]},
        "required": ["ID", "Amount"],
        "defaults": {"Country": "UNKNOWN", "Amount": "0,00"},
        "types": {
            "Amount": {"type": "money", "currency": "EUR", "locale": "de-DE", "convert": True}
        },
        "select": ["Country", "Amount"],
    }


def source_mask() -> FilterMask:
    return FilterMask(
        sheet="Data",
        source=TableSource(
            columns=(
                ColumnBinding(name="Customer", column="C"),
                ColumnBinding(name="Revenue", column="D"),
                ColumnBinding(name="RevenuePreviousYear", column="E"),
            ),
            data_start_row=7,
            data_end_row=10,
            skip_rows=(8,),
        ),
        where=AllOf(
            conditions=(
                TextCondition(column="Customer", op=Operator.STARTS_WITH, value="ABC"),
                NumericCondition(column="Revenue", op=Operator.GTE, value=100),
            )
        ),
    )
