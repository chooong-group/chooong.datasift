# chooong.datasift

[![CI](https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml/badge.svg)](https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Extract, validate and filter tabular data from XLSX/XLSM and CSV using a JSON mask. Rust streams
worksheet rows; Python receives typed, immutable results without loading whole
sheets into a DataFrame. DataSift finds tables beyond A1 and handles repeated
headers and neighboring tables. It does not calculate formulas or write Excel files.

Requires CPython 3.13 or 3.14 and Pydantic. No external service is needed.
The package is currently unreleased; install from a checkout with Rust 1.95.0:

```bash
python -m pip install .
# or, in an active environment:
uv pip install .
```

## Example

Generate synthetic data with a title, two tables at C4 and H4, and comments
between the headers and records:

```bash
python examples/create_sample.py sample.xlsx --dirty
```

```python
from pathlib import Path

from chooong.datasift import AllOf, FilterMask, NumericCondition, Operator, ScalarCondition, iter_matching_rows

mask = FilterMask(
    sheet=None,
    where=AllOf(conditions=(
        ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
        NumericCondition(column="Amount", op=Operator.GTE, value=1000),
    )),
)
for row in iter_matching_rows("sample.xlsx", mask):
    print(dict(row))
# {'Country': 'DE', 'Amount': 1500}
# {'Country': 'DE', 'Amount': 2400}

Path("sample-filter.json").write_text(mask.model_dump_json(by_alias=True), encoding="utf-8")
```

Run the same filter from the CLI:

```bash
chooong-datasift sample.xlsx sample-filter.json --output matches.ndjson
```

[Getting Started](docs/index.md) shows the workbook layout and filter JSON.
See [JSON Filters](docs/contract.md), [Excel Layouts](docs/layouts.md),
[Python API](docs/python-api.md), [CLI](docs/cli.md) and
[Limits & Errors](docs/limits.md) for the supported behavior.

Python validates masks with Pydantic; Rust handles parsing, discovery, types,
filtering, matched/rejected routing and NDJSON/Parquet writing. Public imports come from `chooong.datasift`, including
`FilterMask`, `TableSource`, `Row`, the matching iterators, `scan_batches`
for matched/rejected records, and `export` for native file output.
Schema failures preserve valid partial records but finish with an error; exports
keep previous files. Free layouts require structural evidence, otherwise use
anchors or explicit sources. Comments/totals/separators use explicit rules.
Recovery requires caller-confirmed destinations and a trusted journal hash;
see the [commit and recovery contract](docs/cli.md#file-output).

The Rust core lives in `datasift-core/`; Python sources are in `src/chooong/datasift/`.
For development, run `uv sync --frozen`; checks and build commands are in
[Contributing](CONTRIBUTING.md).
[Changelog](CHANGELOG.md) · [License](LICENSE)
