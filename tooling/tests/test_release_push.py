"""Use real Git push to a local bare remote and a strict fake GitHub boundary."""

import json
import subprocess
from pathlib import Path

import pytest

from release import push as command
from release.prepare import apply, plan
from release.shared import git


@pytest.fixture
def prepared_repo(release_repo: Path, tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git(release_repo, "remote", "add", "origin", str(remote))
    git(release_repo, "config", "user.name", "Synthetic")
    git(release_repo, "config", "user.email", "fixture@example.invalid")
    git(release_repo, "push", "origin", "main")
    apply(plan(release_repo, "0.1.0", frozenset()))
    return release_repo


def test_release_push_creates_one_branch_and_pr_and_replays_safely(
    prepared_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    def github(repo: Path, *args: str) -> str:
        assert args[0] == "gh"
        if args[2] == "list":
            return (
                json.dumps([{"url": created[0], "headRefOid": git(repo, "rev-parse", "HEAD")}])
                if created
                else "[]"
            )
        assert args[2] == "create"
        assert "--body-file" in args
        notes = Path(args[args.index("--body-file") + 1]).read_text()
        assert "Added" in notes
        created.append("https://github.com/chooong-group/chooong.datasift/pull/999999")
        return created[0]

    monkeypatch.setattr(command, "run", github)
    url = command.push(prepared_repo)
    assert command.push(prepared_repo) == url
    assert len(created) == 1
    assert git(prepared_repo, "branch", "--show-current") == "release/v0.1.0"
    assert git(prepared_repo, "rev-parse", "HEAD") in git(
        prepared_repo, "ls-remote", "--heads", "origin", "release/v0.1.0"
    )
    assert git(prepared_repo, "tag", "--list") == ""
    assert not git(prepared_repo, "status", "--porcelain")


def test_release_push_never_stages_unrelated_files(prepared_repo: Path) -> None:
    (prepared_repo / "unrelated.txt").write_text("preserve")
    with pytest.raises(ValueError, match="Unrelated"):
        command.push(prepared_repo)
    assert git(prepared_repo, "branch", "--show-current") == "main"
    assert git(prepared_repo, "diff", "--cached", "--name-only") == ""
