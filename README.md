# chooong.datasift

[![CI][ci-badge]][ci]
[![Coverage: not published][coverage-badge]][ci]
[![PyPI: unreleased][pypi-badge]][installation]
[![Python versions][python-badge]][installation]
[![License: Apache-2.0][license-badge]][license]

[ci-badge]: https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml/badge.svg
[ci]: https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml
[coverage-badge]: https://img.shields.io/badge/coverage-not%20published-lightgrey
[pypi-badge]: https://img.shields.io/badge/PyPI-unreleased-lightgrey
[python-badge]: https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue
[license-badge]: https://img.shields.io/badge/license-Apache--2.0-blue
[installation]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/installation.md
[license]: https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE

Extract, validate and filter tables from XLSX/XLSM and CSV with a JSON mask.
Rust streams rows and writes NDJSON/Parquet; Python exposes typed, immutable
results. Tables may start away from A1 or sit beside other tables.

## Installation

Version 0.1.0 is unreleased. Use CPython 3.12–3.14 and install from a checkout
with Rust 1.95.0, Cargo and a native linker:

<!-- check: syntax -->

```bash
python -m pip install .
```

Compatible maintainer-built wheels need no compiler. Pydantic is the only direct
Python runtime dependency; no external service is needed.

## Example

This example creates its own input:

```python
from pathlib import Path

from chooong.datasift import (
    AllOf,
    DataType,
    FilterMask,
    HeaderConfig,
    NumericCondition,
    Operator,
    ScalarCondition,
    TypeRule,
    iter_matching_rows,
)

Path("transactions.csv").write_text(
    "Country,Amount,Note\nDE,1500,first\nAT,2000,second\nDE,900,third\n",
    encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("Country", "Amount")),
    types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
    where=AllOf(conditions=(
        ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
        NumericCondition(column="Amount", op=Operator.GTE, value=1000),
    )),
)
rows = [dict(row) for row in iter_matching_rows("transactions.csv", mask)]
assert rows == [{"Country": "DE", "Amount": 1500}]
Path("mask.json").write_text(mask.model_dump_json(by_alias=True), encoding="utf-8")
```

Run the same filter from the CLI:

```bash
chooong-datasift transactions.csv mask.json --output matches.ndjson
```

## Documentation and limits

Start with [installation](https://github.com/chooong-group/chooong.datasift/blob/main/docs/installation.md)
and the [quickstart](https://github.com/chooong-group/chooong.datasift/blob/main/docs/quickstart.md).
The [documentation](https://github.com/chooong-group/chooong.datasift/blob/main/docs/index.md)
links guides, exact Python/CLI references and the filter schema.

XLS/XLSB, encrypted workbooks, formula calculation and Excel output are unsupported.
Formula caches are read. Shared strings and metadata use memory despite row
streaming. Ambiguous layouts require anchors or explicit sources. A late scan
failure may follow partial iterator/stdout results; exported results use a
journaled commit, not a shared atomic two-file replacement. See
[file safety](https://github.com/chooong-group/chooong.datasift/blob/main/docs/reference/file-safety.md).

Public imports come from `chooong.datasift`. Python validates masks; the
[Rust core](https://github.com/chooong-group/chooong.datasift/blob/main/datasift-core/README.md)
owns parsing and the row pipeline. For development, use `uv sync --frozen` and
[Contributing](https://github.com/chooong-group/chooong.datasift/blob/main/CONTRIBUTING.md).

[Changelog](https://github.com/chooong-group/chooong.datasift/blob/main/CHANGELOG.md) ·
[Security](https://github.com/chooong-group/chooong.datasift/blob/main/SECURITY.md) ·
[Apache-2.0 license](https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE)
