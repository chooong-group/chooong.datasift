"""Check repository Markdown, local links, navigation and executable examples."""

from __future__ import annotations

import argparse
import ast
import csv
import io
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import JsonValue, RootModel
from readme_renderer.markdown import render

from chooong.datasift import (
    DateLiteral,
    DatetimeLiteral,
    DecimalLiteral,
    FilterMask,
    MoneyLiteral,
)
from tests.fixtures.excel import Sheet, worksheet_rows, write_book

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/chooong-group/chooong.datasift"
JSON = RootModel[JsonValue]
EXACT = RootModel[DecimalLiteral | MoneyLiteral | DateLiteral | DatetimeLiteral]


class Directive(StrEnum):
    FILE = "file"
    WORKBOOK = "workbook"
    CHECK = "check"


@dataclass(frozen=True, slots=True)
class Fence:
    language: str
    code: str
    directive: Directive | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    path: Path
    links: tuple[str, ...]
    anchors: frozenset[str]
    fences: tuple[Fence, ...]


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is not None:
                if name == "id":
                    self.anchors.add(value)
                elif (tag == "a" and name == "href") or (tag == "img" and name == "src"):
                    self.links.append(value)


def markdown_files(root: Path) -> tuple[Path, ...]:
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    return tuple(
        sorted({root / name for name in names if name.endswith(".md") and (root / name).is_file()})
    )


def fences(text: str) -> tuple[Fence, ...]:
    result: list[Fence] = []
    directive: Directive | None = None
    target: str | None = None
    language: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        marker = re.fullmatch(r"<!-- (file|workbook|check): (.+) -->", line)
        if language is None and marker:
            directive, target = Directive(marker[1]), marker[2]
        elif line.startswith("```"):
            if language is None:
                language = line[3:].strip()
            else:
                result.append(Fence(language, "\n".join(lines) + "\n", directive, target))
                language, directive, target = None, None, None
                lines = []
        elif language is not None:
            lines.append(line)
    if language is not None:
        raise ValueError("Unclosed code fence")
    return tuple(result)


def document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    rendered = subprocess.check_output(
        [sys.executable, "-m", "markdown", "-x", "tables", "-x", "fenced_code", "-x", "toc"],
        input=text,
        text=True,
    )
    parser = Links()
    parser.feed(rendered)
    return Document(path, tuple(parser.links), frozenset(parser.anchors), fences(text))


def local_target(root: Path, page: Path, link: str) -> Path | None:
    url = urlsplit(link)
    if link.startswith(REPOSITORY + "/blob/main/"):
        return (root / unquote(url.path.split("/blob/main/", 1)[1])).resolve()
    if url.scheme or url.netloc:
        return None
    return page if not url.path else (page.parent / unquote(url.path)).resolve()


def check_links(root: Path, documents: tuple[Document, ...]) -> tuple[str, ...]:
    external: set[str] = set()
    for page in documents:
        for link in page.links:
            target = local_target(root, page.path, link)
            if target is None:
                external.add(link)
                continue
            if not target.is_relative_to(root) or not target.exists():
                raise ValueError(f"{page.path}: missing or out-of-repository link {link}")
            fragment = unquote(urlsplit(link).fragment)
            if fragment and target.suffix == ".md":
                destination = next((doc for doc in documents if doc.path == target), None)
                if destination is None or fragment not in destination.anchors:
                    raise ValueError(f"{page.path}: missing anchor {link}")
    return tuple(sorted(external))


def check_readme(root: Path) -> None:
    html = render((root / "README.md").read_text(encoding="utf-8"))
    if html is None:
        raise ValueError("PyPI README could not be rendered as GitHub Flavored Markdown")
    links = Links()
    links.feed(html)
    if any(not urlsplit(link).scheme and not link.startswith("#") for link in links.links):
        raise ValueError("PyPI README links must be absolute")


def check_navigation(root: Path) -> None:
    config = (root / "mkdocs.yml").read_text(encoding="utf-8")
    entries = re.findall(r"^\s+- [^:]+: ([\w./-]+\.md)$", config, re.MULTILINE)
    actual = {str(path.relative_to(root / "docs")) for path in (root / "docs").rglob("*.md")}
    if len(entries) != len(set(entries)) or set(entries) != actual:
        raise ValueError(f"Navigation differs from documentation files: {set(entries) ^ actual}")


def example_path(directory: Path, target: str | None) -> Path:
    if target is None:
        raise ValueError("File/workbook directive needs a filename")
    path = directory / target
    if path.parent != directory or path.is_absolute() != directory.is_absolute():
        raise ValueError("Example filenames must stay in their temporary directory")
    return path


def workbook(path: Path, code: str) -> None:
    values: list[tuple[str | bool | int | float | None, ...]] = []
    for row in csv.reader(io.StringIO(code)):
        cells: list[str | bool | int | float | None] = []
        for cell in row:
            if not cell:
                cells.append(None)
            else:
                try:
                    value = JSON.model_validate_json(cell).root
                    cells.append(
                        value
                        if isinstance(value, (str, bool, int, float)) or value is None
                        else cell
                    )
                except ValueError:
                    cells.append(cell)
        values.append(tuple(cells))
    write_book(path, Sheet("Data", worksheet_rows(values)))


def json_block(block: Fence) -> None:
    if block.language == "jsonl":
        for line in block.code.splitlines():
            JSON.model_validate_json(line)
    elif block.language == "json":
        value = JSON.model_validate_json(block.code).root
        if isinstance(value, dict) and "type" in value:
            EXACT.model_validate_json(block.code)
        else:
            FilterMask.model_validate_json(block.code, by_name=False)


def shell_commands(code: str) -> tuple[list[str], ...]:
    return tuple(
        shlex.split(line, comments=True)
        for line in code.replace("\\\n", " ").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def shell_block(block: Fence) -> list[str]:
    commands = shell_commands(block.code)
    if block.directive == Directive.CHECK:
        if block.target != "syntax":
            raise ValueError("Only check: syntax is supported")
        subprocess.run(["bash", "-n"], input=block.code, text=True, check=True)
        return []
    lines: list[str] = []
    for command in commands:
        if not command or command[0] != "chooong-datasift":
            raise ValueError("Executable shell examples must invoke chooong-datasift")
        arguments = ["-m", "chooong.datasift", *command[1:]]
        lines.append(f"subprocess.run([sys.executable, *{arguments!r}], check=True)")
    return lines


def example_script(page: Document, directory: Path) -> str:
    lines = ["import subprocess", "import sys"]
    for block in page.fences:
        json_block(block)
        if block.directive == Directive.FILE:
            example_path(directory, block.target).write_text(block.code, encoding="utf-8")
        elif block.directive == Directive.WORKBOOK:
            workbook(example_path(directory, block.target), block.code)
        elif block.language == "python":
            ast.parse(block.code, filename=str(page.path))
            lines.append(block.code)
        elif block.language == "bash":
            lines.extend(shell_block(block))
        elif block.language not in {"text", "csv", "json", "jsonl"}:
            raise ValueError(f"Unsupported example language: {block.language}")
    return "\n".join(lines)


def check_examples(documents: tuple[Document, ...], python: Path) -> int:
    count = 0
    for page in documents:
        with tempfile.TemporaryDirectory(prefix="datasift-docs-") as temporary:
            directory = Path(temporary)
            script = directory / "example.py"
            script.write_text(example_script(page, directory), encoding="utf-8")
            result = subprocess.run(
                [str(python), "-I", str(script)],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if result.returncode:
                raise ValueError(f"{page.path}: example failed\n{result.stdout}{result.stderr}")
        count += len(page.fences)
    return count


def check_external(links: tuple[str, ...]) -> None:
    for link in links:
        if link in {REPOSITORY, REPOSITORY + "/issues"}:
            subprocess.run(
                ["gh", "api", "repos/chooong-group/chooong.datasift"],
                check=True,
                stdout=subprocess.DEVNULL,
                timeout=30,
            )
        elif urlsplit(link).scheme in {"http", "https"}:
            request = Request(link, headers={"User-Agent": "DataSift-documentation-check"})
            with urlopen(request, timeout=15) as response:
                if response.status != HTTPStatus.OK:
                    raise ValueError(f"External link returned {response.status}: {link}")
        elif urlsplit(link).scheme != "mailto":
            raise ValueError(f"Unsupported external link: {link}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--external", action="store_true")
    args = parser.parse_args()
    paths = markdown_files(ROOT)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pymarkdown",
            "--config",
            str(ROOT / ".pymarkdown.json"),
            "--strict-config",
            "scan",
            *map(str, paths),
        ],
        check=True,
        cwd=ROOT,
    )
    check_readme(ROOT)
    documents = tuple(document(path) for path in paths)
    external = check_links(ROOT, documents)
    check_navigation(ROOT)
    count = check_examples(documents, args.python.absolute())
    if args.external:
        check_external(external)
    sys.stdout.write(f"Checked {len(paths)} Markdown files, links/navigation and {count} fences.\n")


if __name__ == "__main__":
    main()
