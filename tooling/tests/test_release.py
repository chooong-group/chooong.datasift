"""Release safety contracts using synthetic evidence, never platform claims."""

import yaml

from tooling.tests.fixtures import REPO


def test_workflows_are_read_only_for_forks_and_publication_is_hard_disabled() -> None:
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
    assert publish["if"].startswith("${{ false &&")
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    assert not (workflows / "release-gitlab-pypi.yml").exists()
    pages = yaml.load((workflows / "docs-pages.yml").read_text(), Loader=yaml.BaseLoader)
    assert pages["jobs"]["build"]["if"].startswith("${{ false &&")
    ci = yaml.load((workflows / "ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(ci["on"]) == {"push", "pull_request"}
    assert all("if" not in job for job in ci["jobs"].values())
    assert pages["jobs"]["deploy"]["if"].startswith("${{ false &&")
    assert "vars.PYPI_PUBLISH_ENABLED == 'true'" in publish["if"]
    for job in pages["jobs"].values():
        assert "vars.PAGES_DEPLOY_ENABLED == 'true'" in job["if"]
    benchmark = yaml.load((workflows / "benchmarks.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(benchmark["on"]) == {"workflow_dispatch"}
