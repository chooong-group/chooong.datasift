"""Documentation checks execute real examples and reject broken contracts/links."""

from pathlib import Path

import pytest
from packaging.version import Version

from chooong.datasift import DataType, FilterMask, Operator, RowClass
from release.prepare import apply, plan
from release.shared import release_notes, verify_prepared
from scripts.docs import (
    ROOT,
    Directive,
    Fence,
    check_examples,
    check_external,
    check_links,
    check_navigation,
    check_readme,
    document,
    example_path,
    fences,
    markdown_files,
    shell_block,
)


def test_documented_examples_execute_against_real_native_engine() -> None:
    import sys

    pages = tuple(document(path) for path in markdown_files(ROOT))
    check_links(ROOT, pages)
    check_navigation(ROOT)
    check_examples(pages, Path(sys.executable))


def test_filter_reference_covers_public_model_fields_and_enums() -> None:
    from chooong.datasift import (
        ColumnBinding,
        CsvConfig,
        HeaderConfig,
        RowPolicy,
        RowRule,
        Rules,
        TableSource,
        TypeRule,
    )

    reference = (ROOT / "docs/api/filters.md").read_text()
    for model in (
        FilterMask,
        Rules,
        TableSource,
        ColumnBinding,
        HeaderConfig,
        CsvConfig,
        TypeRule,
        RowPolicy,
        RowRule,
    ):
        for name in model.model_fields:
            assert f"`{name}`" in reference or f"`{name}=" in reference, (model, name)
    for enum in (Operator, DataType, RowClass):
        for value in enum:
            assert f"`{value.value}`" in reference


def test_links_validate_existing_files_and_heading_anchors(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    target.write_text("# Target\n\n## Exact heading\n")
    source.write_text("# Source\n\n[Target](target.md#exact-heading)\n")
    pages = (document(source), document(target))
    assert check_links(tmp_path, pages) == ()
    source.write_text("# Source\n\n[Target](target.md#missing)\n")
    with pytest.raises(ValueError, match="missing anchor"):
        check_links(tmp_path, (document(source), document(target)))
    source.write_text("# Source\n\n[Target](missing.md)\n")
    with pytest.raises(ValueError, match="missing.*link"):
        check_links(tmp_path, (document(source), document(target)))


def test_bad_native_example_fails_and_does_not_change_its_source(tmp_path: Path) -> None:
    import sys

    path = tmp_path / "bad.md"
    path.write_text("""# Example

```python
from pathlib import Path
from chooong.datasift import iter_matching_rows
Path("bad.csv").write_text("A,B\\na,1\\n")
assert list(iter_matching_rows("bad.csv", {"sheet": None})) == []
```
""")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="example failed"):
        check_examples((document(path),), Path(sys.executable))
    assert path.read_bytes() == before


def test_example_inputs_cannot_escape_temporary_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="temporary directory"):
        example_path(tmp_path, "../outside.csv")
    with pytest.raises(ValueError, match="filename"):
        example_path(tmp_path, None)
    with pytest.raises(ValueError, match="Executable shell"):
        shell_block(Fence("bash", "curl https://example.invalid\n"))
    assert shell_block(Fence("bash", "uv build\n", Directive.CHECK, "syntax")) == []
    with pytest.raises(ValueError, match="Unclosed"):
        fences("```python\nassert False\n")


def test_navigation_rejects_orphan_and_missing_pages(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Index\n")
    config = tmp_path / "mkdocs.yml"
    config.write_text("nav:\n  - Home: index.md\n")
    check_navigation(tmp_path)
    (docs / "orphan.md").write_text("# Orphan\n")
    with pytest.raises(ValueError, match="Navigation differs"):
        check_navigation(tmp_path)
    config.write_text("nav:\n  - Home: index.md\n  - Missing: missing.md\n")
    with pytest.raises(ValueError, match="Navigation differs"):
        check_navigation(tmp_path)


def test_current_changelog_prepares_and_replays_without_docs_or_tooling_notes(
    release_repo: Path,
) -> None:
    notes = (release_repo / "CHANGELOG.md").read_text()
    assert "## Unreleased\n" in notes
    assert "## 0.1.0\n" not in notes
    prepared = plan(release_repo, "0.1.0", frozenset[Version]())
    apply(prepared)
    verify_prepared(release_repo, "0.1.0")
    assert "Streaming XLSX/XLSM" in release_notes(release_repo, "0.1.0")
    assert not plan(release_repo, "0.1.0", frozenset[Version]()).changes


def test_pypi_readme_renders_and_rejects_relative_links(tmp_path: Path) -> None:
    check_readme(ROOT)
    (tmp_path / "README.md").write_text("# Project\n\n[Guide](docs/index.md)\n")
    with pytest.raises(ValueError, match="must be absolute"):
        check_readme(tmp_path)


def test_external_link_check_accepts_contact_links_without_sending_mail() -> None:
    check_external(("mailto:github@chooong.com",))
    with pytest.raises(ValueError, match="Unsupported external link"):
        check_external(("file:///not-an-external-link",))
