"""Prepare synchronized versions and changelog; never create tags or publish."""

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packaging.version import Version

from release.shared import (
    RELEASE_FILES,
    ROOT,
    FileChange,
    Plan,
    changed_paths,
    git,
    lock_change,
    published_versions,
    validate_version,
    verify_prepared,
    version_change,
)


def plan(repo: Path, version: str, published: frozenset[Version]) -> Plan:
    validate_version(version)
    if Version(version) in published:
        raise ValueError("Version is already published on PyPI")
    branch = git(repo, "branch", "--show-current")
    if branch not in {"main", f"release/v{version}"}:
        raise ValueError("Prepare releases on main or their matching release branch")
    dirty = changed_paths(repo)
    if dirty - set(RELEASE_FILES):
        raise ValueError("Unrelated working-tree changes block release preparation")
    changelog = repo / "CHANGELOG.md"
    before = changelog.read_text(encoding="utf-8")
    if f"## {version}\n" in before:
        verify_prepared(repo, version)
        return Plan(version, ())
    if dirty:
        raise ValueError("A clean working tree is required before initial preparation")
    if before.count("## Unreleased\n") != 1:
        raise ValueError("Exactly one Unreleased section is required")
    notes = before.split("## Unreleased\n", 1)[1].split("\n## ", 1)[0]
    if not notes.strip():
        raise ValueError("Unreleased notes must not be empty")
    after = before.replace("## Unreleased\n", f"## Unreleased\n\n## {version}\n", 1)
    changes = (
        version_change(repo / "pyproject.toml", "project", version),
        version_change(repo / "datasift-core/Cargo.toml", "package", version),
        lock_change(repo / "datasift-core/Cargo.lock", "datasift-core", version),
        lock_change(repo / "uv.lock", "chooong-datasift", version),
        FileChange(changelog, before, after),
    )
    return Plan(version, tuple(change for change in changes if change.before != change.after))


def apply(prepared: Plan) -> None:
    written: list[FileChange] = []
    try:
        for change in prepared.changes:
            if change.path.read_text(encoding="utf-8") != change.before:
                raise ValueError("Release input changed after preparation")
        for change in prepared.changes:
            change.path.write_text(change.after, encoding="utf-8")
            written.append(change)
    except OSError:
        for change in reversed(written):
            change.path.write_text(change.before, encoding="utf-8")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=validate_version)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        prepared = plan(ROOT, args.version, published_versions())
        if not args.dry_run:
            apply(prepared)
        action = "Would update" if args.dry_run else "Prepared"
        sys.stdout.write(f"{action} v{prepared.version}: {len(prepared.changes)} changed files\n")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
