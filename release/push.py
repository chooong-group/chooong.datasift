"""Create one release branch and PR; never create a tag or GitHub release."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, ConfigDict, TypeAdapter

from release.shared import (
    RELEASE_FILES,
    REPOSITORY,
    ROOT,
    changed_paths,
    current_version,
    git,
    release_notes,
    run,
    validate_version,
    verify_prepared,
)


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    headRefOid: str


REQUESTS = TypeAdapter(list[PullRequest])


def ensure_branch(repo: Path, branch: str, current: str) -> None:
    remote = git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if remote and remote.split()[0] != git(repo, "rev-parse", "HEAD"):
        raise ValueError("Remote release branch already exists at another commit")
    if current != branch:
        local = git(repo, "branch", "--list", branch)
        if local:
            raise ValueError(
                "Local release branch already exists; inspect and switch to it explicitly"
            )
        git(repo, "switch", "-c", branch)


def push(repo: Path, *, dry_run: bool = False) -> str:
    version = validate_version(current_version(repo))
    verify_prepared(repo, version)
    branch = f"release/v{version}"
    current = git(repo, "branch", "--show-current")
    if current not in {"main", branch}:
        raise ValueError("Release PRs must start from main or their existing release branch")
    changes = changed_paths(repo)
    if changes - set(RELEASE_FILES):
        raise ValueError("Unrelated changes block release PR creation")
    if dry_run:
        return f"Would commit release files, push {branch} and create/reuse its PR against main"
    existing = REQUESTS.validate_json(
        run(
            repo,
            "gh",
            "pr",
            "list",
            "--repo",
            REPOSITORY,
            "--head",
            branch,
            "--base",
            "main",
            "--state",
            "open",
            "--json",
            "url,headRefOid",
        )
    )
    if len(existing) > 1:
        raise ValueError("Multiple release PRs found")
    if existing:
        if changes or existing[0].headRefOid != git(repo, "rev-parse", "HEAD"):
            raise ValueError(
                "Existing release PR differs from this checkout; inspect it before retrying"
            )
        return existing[0].url
    ensure_branch(repo, branch, current)
    if changes:
        git(repo, "add", "--", *RELEASE_FILES)
        git(repo, "commit", "-m", f"chore: prepare release v{version}")
    git(repo, "push", "--set-upstream", "origin", branch)
    with tempfile.TemporaryDirectory(prefix="datasift-release-pr-") as temporary:
        body = Path(temporary) / "notes.md"
        body.write_text(release_notes(repo, version), encoding="utf-8")
        return run(
            repo,
            "gh",
            "pr",
            "create",
            "--repo",
            REPOSITORY,
            "--head",
            branch,
            "--base",
            "main",
            "--title",
            f"Release v{version}",
            "--body-file",
            str(body),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        sys.stdout.write(push(ROOT, dry_run=args.dry_run) + "\n")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
