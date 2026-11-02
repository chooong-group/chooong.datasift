"""Release safety contracts using synthetic evidence, never platform claims."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from release.shared import git
from tooling.tests.fixtures import REPO


def test_workflows_are_read_only_for_forks_and_publication_requires_authorization() -> None:
    workflows = REPO / ".github/workflows"
    for path in workflows.glob("*.yml"):
        text = path.read_text()
        assert "pull_request_target" not in text
        assert "self-hosted" not in text
        assert "secrets." not in text
        assert "github.event.repository.private" not in text
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        assert workflow["permissions"] == {"contents": "read"}
    release = yaml.load((workflows / "release.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(release["on"]) == {"workflow_dispatch"}
    publish = release["jobs"]["publish"]
    assert set(publish["needs"]) == {"release-identity", "distributions"}
    assert publish["if"] == (
        "${{ inputs.publish && vars.PYPI_PUBLISH_ENABLED == 'true' && "
        "startsWith(github.ref, 'refs/tags/v') }}"
    )
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    assert not (workflows / "release-gitlab-pypi.yml").exists()
    pages = yaml.load((workflows / "docs-pages.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(pages["on"]) == {"workflow_dispatch"}
    ci = yaml.load((workflows / "ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(ci["on"]) == {"push", "pull_request"}
    assert all("if" not in job for job in ci["jobs"].values())
    for job in pages["jobs"].values():
        assert job["if"] == (
            "${{ vars.PAGES_DEPLOY_ENABLED == 'true' && github.ref == 'refs/heads/main' }}"
        )
    benchmark = yaml.load((workflows / "benchmarks.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(benchmark["on"]) == {"workflow_dispatch"}


@pytest.mark.parametrize("publish", [False, True])
@pytest.mark.parametrize("enabled", ["", "false", "true"])
@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/other", "refs/tags/v0.1.0"])
def test_publish_gate_requires_every_authorization(publish: bool, enabled: str, ref: str) -> None:
    release = yaml.load(
        (REPO / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    # Translate only the three contracted predicates; unexpected expressions fail in bash.
    condition = release["jobs"]["publish"]["if"].removeprefix("${{ ").removesuffix(" }}")
    condition = condition.replace("inputs.publish", '[ "$PUBLISH" = true ]')
    condition = condition.replace("vars.PYPI_PUBLISH_ENABLED == 'true'", '[ "$ENABLED" = true ]')
    condition = condition.replace(
        "startsWith(github.ref, 'refs/tags/v')", '[[ "$GITHUB_REF" == refs/tags/v* ]]'
    )
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", condition],
        env=os.environ | {"PUBLISH": str(publish).lower(), "ENABLED": enabled, "GITHUB_REF": ref},
        capture_output=True,
        text=True,
        check=False,
    )
    expected = publish and enabled == "true" and ref == "refs/tags/v0.1.0"
    assert result.returncode == (0 if expected else 1), result.stderr


@pytest.mark.parametrize(
    "failure", [None, "tag", "commit", "missing_approval", "moved_tag", "off_main"]
)
def test_release_identity_rejects_unapproved_tags_and_commits(
    release_repo: Path, failure: str | None
) -> None:
    release = yaml.load(
        (REPO / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    identity = release["jobs"]["release-identity"]["steps"][-1]
    assert identity["if"] == "inputs.publish"
    assert identity["env"] == {
        "VERSION": "${{ inputs.version }}",
        "APPROVED_COMMIT": "${{ inputs.approved-commit }}",
    }
    commit = git(release_repo, "rev-parse", "HEAD")
    git(release_repo, "update-ref", "refs/remotes/origin/main", commit)
    git(
        release_repo,
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "Other synthetic commit",
    )
    other = git(release_repo, "rev-parse", "HEAD")
    git(release_repo, "update-ref", "refs/tags/v0.1.0", other if failure == "moved_tag" else commit)
    if failure == "off_main":
        commit = other
        git(release_repo, "update-ref", "refs/tags/v0.1.0", commit)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", identity["run"]],
        cwd=release_repo,
        env=os.environ
        | {
            "VERSION": "0.1.0",
            "GITHUB_REF": "refs/tags/v0.2.0" if failure == "tag" else "refs/tags/v0.1.0",
            "GITHUB_SHA": commit,
            "APPROVED_COMMIT": ""
            if failure == "missing_approval"
            else (other if failure == "commit" else commit),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (failure is None), result.stderr


def test_publication_keeps_authenticated_bytes_and_release_ordering() -> None:
    release = yaml.load(
        (REPO / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = release["jobs"]["publish"]["steps"]
    before, upload, after = steps[-3:]
    expected = "${{ needs.distributions.outputs.checksums-sha256 }}"
    assert before["env"]["EXPECTED_SHA256"] == expected
    assert before["run"] == 'python scripts/verify_publish.py verified "$EXPECTED_SHA256"'
    assert upload["uses"].startswith("pypa/gh-action-pypi-publish@")
    assert upload["with"] == {"packages-dir": "verified/dist/", "skip-existing": "false"}
    assert after["env"] == {"EXPECTED_SHA256": expected, "VERSION": "${{ inputs.version }}"}
    assert after["run"] == (
        'python scripts/verify_publish.py verified "$EXPECTED_SHA256" --pypi-version "$VERSION"'
    )
    github_release = release["jobs"]["github-release"]
    assert github_release["needs"] == "publish"
    assert github_release["if"] == "${{ needs.publish.result == 'success' }}"
    command = github_release["steps"][-1]["run"]
    assert 'gh release create "v$VERSION" --verify-tag' in command
    assert "--target" not in command
