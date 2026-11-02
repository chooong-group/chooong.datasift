"""Public contract checks using real synthetic files."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from chooong.datasift import (
    export,
    recover_export,
)
from tests.fixtures.masks import (
    pipeline_mask,
)
from tests.fixtures.results import recovery_journal


def test_journal_recovery_rolls_forward_and_refuses_replay(tmp_path: Path) -> None:
    matched = tmp_path / "matched.ndjson"
    rejected = tmp_path / "rejected.ndjson"
    stage = tmp_path / ".rejected.ndjson.datasift-123-0.tmp"
    matched.write_text("new match")
    rejected.write_text("old reject")
    stage.write_text("new reject")
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(matched),
                        "stage": str(tmp_path / ".matched.ndjson.datasift-123-0.tmp"),
                        "sha256": sha256(b"new match").hexdigest(),
                    },
                    {
                        "destination": str(rejected),
                        "stage": str(stage),
                        "sha256": sha256(b"new reject").hexdigest(),
                    },
                ],
            }
        )
    )
    trusted = sha256(journal.read_bytes()).hexdigest()
    recover_export(matched, journal_sha256=trusted, rejected_output=rejected)
    assert matched.read_text() == "new match"
    assert rejected.read_text() == "new reject"
    assert not journal.exists()
    with pytest.raises(ValueError, match="missing"):
        recover_export(matched, journal_sha256=trusted, rejected_output=rejected)


def test_commit_metadata_paths_cannot_be_result_paths(csv_file: Path, tmp_path) -> None:
    path = csv_file
    output = tmp_path / "matched.ndjson"
    for rejected in (
        tmp_path / ".matched.ndjson.datasift-commit.json",
        tmp_path / ".matched.ndjson.datasift.lock",
    ):
        with pytest.raises(RuntimeError, match="metadata"):
            export(path, pipeline_mask(), output, rejected_output=rejected)
    assert not output.exists()


def test_recovery_detects_missing_uncommitted_stage_and_tampering(tmp_path) -> None:
    output = tmp_path / "matched.ndjson"
    output.write_text("old result")
    stage = tmp_path / ".matched.ndjson.datasift-1-0.tmp"
    journal = tmp_path / ".matched.ndjson.datasift-commit.json"
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "destination": str(output),
                        "stage": str(stage),
                        "sha256": sha256(b"new result").hexdigest(),
                    }
                ],
            }
        )
    )
    trusted = sha256(journal.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="match"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "old result"
    assert journal.exists()
    stage.write_text("changed result")
    with pytest.raises(ValueError, match="match"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "old result"
    stage.write_text("new result")
    recover_export(output, journal_sha256=trusted)
    assert output.read_text() == "new result"


def test_recovery_requires_trusted_digest_and_explicit_destinations(tmp_path: Path) -> None:
    output, stage, journal, trusted = recovery_journal(tmp_path)
    victim = tmp_path / "victim.ndjson"
    victim.write_bytes(b"do not overwrite")
    payload = json.loads(journal.read_text())
    payload["entries"][0]["destination"] = str(victim)
    journal.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum"):
        recover_export(output, journal_sha256=trusted)
    with pytest.raises(ValueError, match="destination path"):
        recover_export(output, journal_sha256=sha256(journal.read_bytes()).hexdigest())
    assert victim.read_bytes() == b"do not overwrite"
    assert output.read_bytes() == b"old"
    assert stage.read_bytes() == b"new"


@pytest.mark.parametrize("path_kind", ["journal", "stage", "target", "lock"])
def test_recovery_rejects_hardlink_aliases(tmp_path: Path, path_kind: str) -> None:
    output, stage, journal, trusted = recovery_journal(tmp_path)
    lock = tmp_path / ".matched.ndjson.datasift.lock"
    lock.write_bytes(b"")
    selected = {"journal": journal, "stage": stage, "target": output, "lock": lock}[path_kind]
    alias = tmp_path / "alias"
    alias.hardlink_to(selected)
    previous = output.read_bytes()
    with pytest.raises(ValueError, match="hard link"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_bytes() == previous
    assert alias.read_bytes() == selected.read_bytes()


@pytest.mark.parametrize("path_kind", ["journal", "stage", "target", "lock"])
def test_recovery_rejects_symlink_aliases(tmp_path: Path, path_kind: str) -> None:
    output, stage, journal, trusted = recovery_journal(tmp_path)
    lock = tmp_path / ".matched.ndjson.datasift.lock"
    lock.write_bytes(b"")
    selected = {"journal": journal, "stage": stage, "target": output, "lock": lock}[path_kind]
    victim = tmp_path / "victim"
    selected.replace(victim)
    selected.symlink_to(victim)
    previous = victim.read_bytes()
    with pytest.raises(ValueError, match="safe regular path|symlink"):
        recover_export(output, journal_sha256=trusted)
    assert victim.read_bytes() == previous


def test_recovery_requires_confirmation_of_second_destination(tmp_path: Path) -> None:
    output, _, journal, _ = recovery_journal(tmp_path)
    rejected = tmp_path / "rejects.ndjson"
    rejected.write_bytes(b"old rejects")
    stage = tmp_path / ".rejects.ndjson.datasift-1-1.tmp"
    stage.write_bytes(b"new rejects")
    payload = json.loads(journal.read_text())
    payload["entries"].append(
        {
            "destination": str(rejected),
            "stage": str(stage),
            "sha256": sha256(b"new rejects").hexdigest(),
        }
    )
    journal.write_text(json.dumps(payload))
    trusted = sha256(journal.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="fully confirmed"):
        recover_export(output, journal_sha256=trusted)
    assert output.read_bytes() == b"old"
    assert rejected.read_bytes() == b"old rejects"
    recover_export(output, journal_sha256=trusted, rejected_output=rejected)
    assert output.read_bytes() == b"new"
    assert rejected.read_bytes() == b"new rejects"


@pytest.mark.parametrize("field", ["destination", "stage"])
def test_recovery_accepts_equivalent_absolute_parent_paths(tmp_path: Path, field: str) -> None:
    output, _, journal, _ = recovery_journal(tmp_path)
    spelling = tmp_path / "spelling"
    spelling.mkdir()
    payload = json.loads(journal.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    entry[field] = str(spelling / ".." / Path(entry[field]).name)
    journal.write_text(json.dumps(payload), encoding="utf-8")
    recover_export(output, journal_sha256=sha256(journal.read_bytes()).hexdigest())
    assert output.read_bytes() == b"new"
    assert not journal.exists()


@pytest.mark.parametrize("field", ["destination", "stage"])
def test_recovery_rejects_other_parent_with_the_same_filename(tmp_path: Path, field: str) -> None:
    output, stage, journal, _ = recovery_journal(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    payload = json.loads(journal.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    victim = other / Path(entry[field]).name
    victim.write_bytes(b"do not overwrite")
    entry[field] = str(victim)
    journal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="destination path"):
        recover_export(output, journal_sha256=sha256(journal.read_bytes()).hexdigest())
    assert output.read_bytes() == b"old"
    assert stage.read_bytes() == b"new"
    assert victim.read_bytes() == b"do not overwrite"
    assert journal.exists()


@pytest.mark.parametrize("field", ["destination", "stage"])
def test_recovery_rejects_relative_manifest_paths(tmp_path: Path, field: str) -> None:
    output, stage, journal, _ = recovery_journal(tmp_path)
    payload = json.loads(journal.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    entry[field] = Path(entry[field]).name
    journal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="destination path"):
        recover_export(output, journal_sha256=sha256(journal.read_bytes()).hexdigest())
    assert output.read_bytes() == b"old"
    assert stage.read_bytes() == b"new"
    assert journal.exists()
