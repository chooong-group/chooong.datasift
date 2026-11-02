"""Public contract checks using real synthetic files."""

from __future__ import annotations

from pathlib import Path

import pytest

from chooong.datasift import (
    FilterMask,
    Operator,
    RecordKind,
    ScalarCondition,
    iter_matching_batches,
    iter_matching_rows,
)
from tests.fixtures.excel import Sheet, make_workbook, rewrite, worksheet_rows, write_book
from tests.fixtures.masks import contract_mask
from tests.fixtures.results import partial_scan


def test_unbound_data_is_not_extracted(tmp_path: Path) -> None:
    path = tmp_path / "unnamed.xlsx"
    make_workbook(path)
    rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t></t>")
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Land", op=Operator.EQ, value="DE")
    )
    rows = list(iter_matching_rows(path, mask))
    assert len(rows) == 7
    assert set(rows[0]) == {"Land"}
    assert "Status" not in rows[0]
    assert rows[0]["Land"] == "DE"


@pytest.mark.parametrize("batch_size", [1, 3, 1024])
def test_sparse_unbound_columns_are_ignored_with_replay(tmp_path: Path, batch_size: int) -> None:
    path = tmp_path / "extras.xlsx"
    make_workbook(path)
    extra_row = (
        '<row r="10">'
        '<c r="A10" t="inlineStr"><is><t>ABC Extra</t></is></c>'
        '<c r="B10" t="inlineStr"><is><t>DE</t></is></c>'
        '<c r="C10"><v>5000</v></c>'
        '<c r="D10" t="inlineStr"><is><t>Aktiv</t></is></c>'
        '<c r="M10" t="s"><v>4</v></c>'
        '<c r="U10"><v>12.5</v></c>'
        '<c r="V10" t="b"><v>0</v></c>'
        '<c r="Z10"/>'
        '<c r="AA10" t="inlineStr"><is><t></t></is></c>'
        '<c r="XFD10"><v>42</v></c>'
        "</row>"
    )
    rewrite(path, "xl/worksheets/data42.xml", "</sheetData>", extra_row + "</sheetData>")
    expected = [dict(row) for row in iter_matching_rows(path, contract_mask(), batch_size=1)]
    with iter_matching_batches(path, contract_mask(), batch_size=batch_size) as batches:
        actual = [dict(row) for batch in batches for row in batch]
    assert actual == expected
    assert len(actual) == 7
    assert actual[-1] == {
        "Kunde": "ABC Extra",
        "Land": "DE",
        "Status": "Aktiv",
    }
    assert "__column_M" not in actual[0]


def test_unbound_cells_do_not_overwrite_named_columns(tmp_path: Path) -> None:
    path = tmp_path / "collision.xlsx"
    make_workbook(path)
    rewrite(path, "xl/sharedStrings.xml", "<t>Kunde</t>", "<t>__column_M</t>")
    rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t>__column_M_</t>")
    before = '<c r="D2" t="s"><v>6</v></c></row>'
    after = (
        '<c r="D2" t="s"><v>6</v></c>'
        '<c r="M2" t="inlineStr"><is><t>synthetic extra</t></is></c></row>'
    )
    rewrite(path, "xl/worksheets/data42.xml", before, after)
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Land", op=Operator.EQ, value="DE")
    )
    rows = list(iter_matching_rows(path, mask))
    assert dict(rows[0]) == {"Land": "DE"}
    assert "__column_M__" not in rows[0]


@pytest.mark.parametrize("selection", [["*"], [{"pattern": "^(ID|Amount)$"}], ["Country", "ID"]])
def test_optional_where_and_regex_projection(
    csv_file: Path, tmp_path: Path, selection: list[object]
) -> None:
    path = csv_file
    rows = list(iter_matching_rows(path, {"sheet": None, "select": selection}))
    assert len(rows) == 3
    assert list(rows[0]) == (
        ["ID", "Amount", "Country"]
        if selection == ["*"]
        else ["ID", "Amount"]
        if isinstance(selection[0], dict)
        else ["Country", "ID"]
    )


def test_projection_can_select_columns_before_filter_and_validation_is_independent(
    tmp_path,
) -> None:
    path = tmp_path / "projection.csv"
    path.write_text("ID,Amount,Country\nfirst,12,DE\nsecond,bad,DE\n")
    mask = {
        "sheet": None,
        "where": {"column": "Country", "op": "eq", "value": "DE"},
        "select": ["ID"],
        "types": {"Amount": {"type": "integer", "convert": True}},
    }
    assert [dict(r) for r in iter_matching_rows(path, mask)] == [{"ID": "first"}]


@pytest.mark.parametrize("selection", [["missing"], [{"pattern": "^missing$"}]])
def test_missing_projection_fails_without_silent_loss(csv_file: Path, tmp_path, selection) -> None:
    path = csv_file
    with pytest.raises((ValueError, RuntimeError), match="SCHEMA_MISMATCH"):
        list(iter_matching_rows(path, {"sheet": None, "select": selection}))


@pytest.mark.parametrize("selection", [["C"], [{"pattern": "^C$"}]])
def test_missing_projection_in_first_sheet_does_not_hide_second_sheet(
    tmp_path: Path, selection: list[object]
) -> None:
    path = tmp_path / "schemas.xlsx"
    write_book(
        path,
        Sheet("Bad", worksheet_rows([("A", "B"), ("bad", 1)])),
        Sheet("Good", worksheet_rows([("A", "C"), ("good", 2)])),
    )
    records, statistics = partial_scan(path, {"sheet": None, "select": selection}, 1)
    assert [r.values for r in records if r.kind == RecordKind.MATCHED] == [{"C": 2}]
    assert statistics.diagnostics[0].code == "SCHEMA_MISMATCH"
