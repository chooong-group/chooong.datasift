"""Release preparation uses real isolated Git checkouts and never touches tags."""

import io
from pathlib import Path

import pytest
from packaging.version import Version

from release import shared
from release.prepare import apply, plan
from release.push import push
from release.shared import RELEASE_FILES, git, verify_prepared


def snapshot(repo: Path) -> tuple[bytes, ...]:
    return tuple((repo / name).read_bytes() for name in RELEASE_FILES)


def test_prepare_dry_run_apply_and_replay(release_repo: Path) -> None:
    before = snapshot(release_repo)
    prepared = plan(release_repo, "0.1.0", frozenset())
    assert snapshot(release_repo) == before
    assert prepared.changes
    apply(prepared)
    verify_prepared(release_repo, "0.1.0")
    once = snapshot(release_repo)
    apply(plan(release_repo, "0.1.0", frozenset()))
    assert snapshot(release_repo) == once
    assert (release_repo / "CHANGELOG.md").read_text().count("## 0.1.0\n") == 1
    assert git(release_repo, "tag", "--list") == ""
    dry = push(release_repo, dry_run=True)
    assert "Would" in dry
    assert git(release_repo, "branch", "--show-current") == "main"
    assert snapshot(release_repo) == once


@pytest.mark.parametrize("version", ["invalid", "v0.1.0", "0.1", "0.1.0rc1", "0.1.0+local"])
def test_prepare_rejects_unsupported_versions_without_changes(
    release_repo: Path, version: str
) -> None:
    before = snapshot(release_repo)
    with pytest.raises(ValueError, match="version|Version|PEP"):
        plan(release_repo, version, frozenset())
    assert snapshot(release_repo) == before


def test_published_version_and_unrelated_changes_block_preparation(release_repo: Path) -> None:
    before = snapshot(release_repo)
    with pytest.raises(ValueError, match="published"):
        plan(release_repo, "0.1.0", frozenset({Version("0.1.0")}))
    (release_repo / "unrelated.txt").write_text("do not stage")
    with pytest.raises(ValueError, match="Unrelated"):
        plan(release_repo, "0.1.0", frozenset())
    assert snapshot(release_repo) == before


def test_wrong_branch_and_changed_plan_are_rejected(release_repo: Path) -> None:
    prepared = plan(release_repo, "0.1.0", frozenset())
    git(release_repo, "switch", "-c", "feature")
    with pytest.raises(ValueError, match="main"):
        plan(release_repo, "0.1.0", frozenset())
    (release_repo / "CHANGELOG.md").write_text("concurrent edit")
    with pytest.raises(ValueError, match="changed"):
        apply(prepared)
    assert (release_repo / "CHANGELOG.md").read_text() == "concurrent edit"
    assert git(release_repo, "tag", "--list") == ""


def test_pypi_response_is_validated_and_network_errors_are_not_empty_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def valid(url: str, timeout: int) -> io.BytesIO:
        assert url == "https://pypi.org/pypi/chooong.datasift/json"
        assert timeout > 0
        return io.BytesIO(b'{"releases":{"0.1.0":[]}}')

    monkeypatch.setattr(shared, "urlopen", valid)
    assert shared.published_versions() == frozenset({Version("0.1.0")})

    def failed(url: str, timeout: int) -> io.BytesIO:
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(shared, "urlopen", failed)
    with pytest.raises(TimeoutError):
        shared.published_versions()
