"""Public model/native interoperability and data integrity checks."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError
from test_engine import make_workbook

from chooong.datasift import (
    AllOf,
    EmptyCondition,
    FilterMask,
    MembershipCondition,
    Operator,
    ScalarCondition,
    iter_matching_batches,
    iter_matching_rows,
)


def _rewrite(path: Path, member: str, before: str, after: str) -> None:
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts[member] = parts[member].decode().replace(before, after).encode()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def _mask() -> FilterMask:
    return FilterMask(
        sheet="Daten",
        where=AllOf(
            conditions=(
                ScalarCondition(column="Land", op=Operator.EQ, value="DE"),
                MembershipCondition(column="Status", value=("Aktiv", "Offen")),
                EmptyCondition(column="Kunde", op=Operator.NOT_EMPTY),
            )
        ),
    )


def test_typed_models_roundtrip_and_immutable_rows(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsm"
    make_workbook(path)
    mask = FilterMask.model_validate_json(_mask().model_dump_json(by_alias=True))
    with iter_matching_batches(path, mask, batch_size=2) as batches:
        rows = [row for batch in batches for row in batch]
    assert len(rows) == 6
    assert rows[0]["Land"] == "DE"
    assert tuple(rows[0]) == ("Kunde", "Land", "Status")
    assert len(rows[0]) == 3
    assert not list(batches)
    with pytest.raises(TypeError):
        rows[0].cells["Kunde"] = "changed"


@pytest.mark.parametrize("batch_size", [0, -1, 65537, True, 1.5])
def test_invalid_batches_fail_before_io(batch_size: object) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        iter_matching_batches("missing.xlsx", _mask(), batch_size=batch_size)


@pytest.mark.parametrize(
    "updates",
    [
        {"sheet": " "},
        {"header_row": True},
        {"unknown": 1},
        {"where": {"column": "Land", "op": "unknown", "value": "DE"}},
        {"where": {"column": "Land", "op": "is_empty", "value": None}},
        {"where": {"column": "Umsatz", "op": "gte", "value": True}},
        {"where": {"column": "Umsatz", "op": "eq", "value": float("nan")}},
    ],
)
def test_untrusted_masks_fail_closed(updates: dict[str, object]) -> None:
    payload = _mask().model_dump(by_alias=True)
    payload.update(updates)
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)


def test_generator_close_and_replay_are_independent(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    rows = iter_matching_rows(path, _mask(), batch_size=1)
    first = next(rows)
    rows.close()
    assert list(rows) == []
    replay = list(iter_matching_rows(path, _mask()))
    assert first == replay[0]
    assert len(replay) == 6


def test_concurrent_scans_do_not_share_state(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)

    def scan(_: int) -> list[str | bool | int | float | None]:
        return [row["Kunde"] for row in iter_matching_rows(path, _mask(), batch_size=1)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(scan, range(8)))
    assert all(result == results[0] for result in results)
    assert len(results[0]) == 6


def test_iterator_can_move_between_threads(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    with iter_matching_batches(path, _mask(), batch_size=1) as batches:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(next, batches).result(timeout=10)
        assert first[0]["Kunde"] == "ABC GmbH"
        assert len([row for batch in batches for row in batch]) == 5


@pytest.mark.parametrize("part", ["xl/worksheets/data42.xml", "xl/sharedStrings.xml"])
def test_truncated_xml_is_not_success(tmp_path: Path, part: str) -> None:
    path = tmp_path / "truncated.xlsx"
    make_workbook(path)
    before = "</worksheet>" if "worksheets" in part else "</sst>"
    _rewrite(path, part, before, "")
    with pytest.raises((RuntimeError, ValueError), match="unvollständig"):
        list(iter_matching_rows(path, _mask(), batch_size=1))


def test_unindexed_duplicate_name_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "headers.xlsx"
    make_workbook(path)
    _rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t>Umsatz</t>")
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Umsatz", op=Operator.EQ, value=5000)
    )
    with pytest.raises(ValueError, match="Unbekannte Spalte"):
        iter_matching_batches(path, mask)


def test_unbound_data_is_not_extracted(tmp_path: Path) -> None:
    path = tmp_path / "unnamed.xlsx"
    make_workbook(path)
    _rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t></t>")
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Land", op=Operator.EQ, value="DE")
    )
    rows = list(iter_matching_rows(path, mask))
    assert len(rows) == 7
    assert set(rows[0]) == {"Land"}
    assert "Status" not in rows[0]
    assert rows[0]["Land"] == "DE"


def test_cli_protects_mask_and_redacts_invalid_values(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    make_workbook(path)
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    original = mask.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask), "--output", str(mask)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert mask.read_bytes() == original
    mask.write_text(json.dumps({"sheet": "private-data", "where": {"op": "private-value"}}))
    result = subprocess.run(
        [sys.executable, "-m", "chooong.datasift", str(path), str(mask)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "private" not in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("group", ["conditions", "condition"])
def test_python_field_names_are_not_wire_aliases(group: str) -> None:
    predicate = {"column": "Land", "op": "eq", "value": "DE"}
    payload = {"sheet": "Daten", "where": {group: [predicate]}}
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", payload)
    with pytest.raises(ValidationError):
        iter_matching_batches("missing.xlsx", json.dumps(payload))


@pytest.mark.parametrize(
    ("column", "op", "value", "expected"),
    [
        ("Land", "eq", "AT", ["XYZ AG"]),
        ("Land", "ne", "DE", ["XYZ AG"]),
        ("Status", "in", ["Offen", "Inaktiv"], ["ABC Hamburg", "ABC & Söhne"]),
        ("Umsatz", "gt", 3200, ["ABC GmbH", "XYZ AG"]),
        ("Umsatz", "gte", 3200, ["ABC GmbH", "XYZ AG", "ABC München"]),
        ("Umsatz", "lt", 2500, ["ABC Berlin", "ABC & Söhne"]),
        ("Umsatz", "lte", 2500, ["ABC Berlin", "ABC Hamburg", "ABC & Söhne"]),
        ("Kunde", "contains", "&", ["ABC & Söhne"]),
        ("Kunde", "starts_with", "XYZ", ["XYZ AG"]),
        ("Kunde", "ends_with", "AG", ["XYZ AG"]),
        ("Kunde", "regex", "^XYZ.*", ["XYZ AG"]),
        ("Umsatz", "is_empty", None, ["ABC Leer"]),
        (
            "Umsatz",
            "not_empty",
            None,
            [
                "ABC GmbH",
                "XYZ AG",
                "ABC Berlin",
                "ABC München",
                "ABC Hamburg",
                "ABC & Söhne",
                "ABC Bool",
            ],
        ),
    ],
)
def test_operator_wire_contract_against_native_engine(
    tmp_path: Path,
    column: str,
    op: str,
    value: object,
    expected: list[str],
) -> None:
    path = tmp_path / "operators.xlsx"
    make_workbook(path)
    condition: dict[str, object] = {"column": column, "op": op}
    if op not in {Operator.IS_EMPTY, Operator.NOT_EMPTY}:
        condition["value"] = value
    rows = iter_matching_rows(
        path,
        {"sheet": "Daten", "where": {"all": [condition, {"column": "Kunde", "op": "not_empty"}]}},
    )
    assert [row["Kunde"] for row in rows] == expected


@pytest.mark.parametrize(
    ("part", "before", "after", "error"),
    [
        (
            "xl/workbook.xml",
            "<workbook ",
            '<!DOCTYPE workbook [<!ENTITY ext SYSTEM "file:///secret">]><workbook ',
            "DTD",
        ),
        (
            "xl/_rels/workbook.xml.rels",
            'Target="worksheets/data42.xml"',
            'Target="../../outside.xml"',
            "ausbrechen",
        ),
    ],
)
def test_unsafe_xml_and_paths_fail_closed(
    tmp_path: Path,
    part: str,
    before: str,
    after: str,
    error: str,
) -> None:
    path = tmp_path / "unsafe.xlsx"
    make_workbook(path)
    _rewrite(path, part, before, after)
    with pytest.raises(ValueError, match=error):
        iter_matching_batches(path, _mask())


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
    _rewrite(path, "xl/worksheets/data42.xml", "</sheetData>", extra_row + "</sheetData>")
    expected = [dict(row) for row in iter_matching_rows(path, _mask(), batch_size=1)]
    with iter_matching_batches(path, _mask(), batch_size=batch_size) as batches:
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
    _rewrite(path, "xl/sharedStrings.xml", "<t>Kunde</t>", "<t>__column_M</t>")
    _rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t>__column_M_</t>")
    before = '<c r="D2" t="s"><v>6</v></c></row>'
    after = (
        '<c r="D2" t="s"><v>6</v></c>'
        '<c r="M2" t="inlineStr"><is><t>synthetic extra</t></is></c></row>'
    )
    _rewrite(path, "xl/worksheets/data42.xml", before, after)
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Land", op=Operator.EQ, value="DE")
    )
    rows = list(iter_matching_rows(path, mask))
    assert dict(rows[0]) == {"Land": "DE"}
    assert "__column_M__" not in rows[0]


def test_unbound_columns_are_not_filter_headers(tmp_path: Path) -> None:
    path = tmp_path / "unknown-header.xlsx"
    make_workbook(path)
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="__column_M", op=Operator.EQ, value="x")
    )
    with pytest.raises(ValueError, match="Unbekannte Spalte"):
        iter_matching_batches(path, mask)


def test_cli_extracts_only_bound_fields_in_ndjson(tmp_path: Path) -> None:
    path = tmp_path / "cli-extras.xlsx"
    make_workbook(path)
    before = '<c r="D5" t="s"><v>6</v></c></row>'
    after = '<c r="D5" t="s"><v>6</v></c><c r="M5"><v>123</v></c></row>'
    _rewrite(path, "xl/worksheets/data42.xml", before, after)
    original = path.read_bytes()
    mask = tmp_path / "mask.json"
    mask.write_text(_mask().model_dump_json(by_alias=True))
    destination = tmp_path / "result.ndjson"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chooong.datasift",
            str(path),
            str(mask),
            "--output",
            str(destination),
            "--batch-size",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert len(rows) == 6
    assert all(set(row) == {"Kunde", "Land", "Status"} for row in rows)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".result.ndjson.*.tmp"))
