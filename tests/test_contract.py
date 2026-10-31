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
    assert rows[0]["Kunde"] == "ABC GmbH"
    assert tuple(rows[0]) == ("Kunde", "Land", "Umsatz", "Status")
    assert len(rows[0]) == 4
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


@pytest.mark.parametrize(
    ("before", "after", "error"),
    [
        ("<t>Land</t>", "<t>Kunde</t>", "Doppelter Spaltenname"),
    ],
)
def test_duplicate_headers_fail_eagerly(
    tmp_path: Path,
    before: str,
    after: str,
    error: str,
) -> None:
    path = tmp_path / "headers.xlsx"
    make_workbook(path)
    _rewrite(path, "xl/sharedStrings.xml", before, after)
    with pytest.raises(ValueError, match=error):
        iter_matching_batches(path, _mask())


def test_unnamed_data_is_never_silently_lost(tmp_path: Path) -> None:
    path = tmp_path / "unnamed.xlsx"
    make_workbook(path)
    _rewrite(path, "xl/sharedStrings.xml", "<t>Status</t>", "<t></t>")
    mask = FilterMask(
        sheet="Daten", where=ScalarCondition(column="Land", op=Operator.EQ, value="DE")
    )
    with pytest.raises(RuntimeError, match="ohne Spaltenüberschrift"):
        list(iter_matching_rows(path, mask))


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
    rows = iter_matching_rows(path, {"sheet": "Daten", "where": condition})
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
