# Getting Started

DataSift extracts matching values from XLSX/XLSM worksheets using a JSON mask.
This example reads two adjacent tables that start away from A1, with comments
between their headers and data.

## Install

Use CPython 3.13 or 3.14. From a checkout:

```bash
python -m pip install .
# or, in an active environment:
uv pip install .
```

Source builds require Rust 1.95.0, Cargo and a native linker (MSVC build tools on
Windows). Compatible wheels need no compiler. Pydantic is the runtime dependency;
no service or database is required.

## Create the workbook

```bash
python examples/create_sample.py sample.xlsx --dirty
```

The generator refuses to overwrite an existing file. Its `Data` sheet contains
a title at A1 and the following cells; all data is synthetic:

| Excel row | C | D | E | H | I | J |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | Country | Amount | Note | Country | Amount | Note |
| 5 | Amounts pending review | | | Includes estimates | | |
| 6 | DE | 1500 | Provisional | DE | 2400 | Approved |
| 7 | AT | 2000 | | DE | 900 | |

## Filter from Python

```python
from pathlib import Path

from chooong.datasift import (
    AllOf, FilterMask, NumericCondition, Operator, ScalarCondition, iter_matching_rows,
)

mask = FilterMask(
    sheet=None,
    where=AllOf(conditions=(
        ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
        NumericCondition(column="Amount", op=Operator.GTE, value=1000),
    )),
)
rows = [dict(row) for row in iter_matching_rows("sample.xlsx", mask)]
assert rows == [
    {"Country": "DE", "Amount": 1500},
    {"Country": "DE", "Amount": 2400},
]
Path("sample-filter.json").write_text(mask.model_dump_json(by_alias=True), encoding="utf-8")
```

The complete `Country`/`Amount` groups identify both tables. The comment rows and
nonmatching records fail the predicate; `Note` is outside the selected columns.
No row number or table coordinates are needed in this mask. See
[Excel Layouts](layouts.md) for discovery rules and ambiguous layouts.

## Use the same mask from the CLI

The generated `sample-filter.json` contains these filter rules:

```json
{
  "sheet": null,
  "where": {
    "all": [
      {"column": "Country", "op": "eq", "value": "DE"},
      {"column": "Amount", "op": "gte", "value": 1000}
    ]
  }
}
```

```bash
chooong-datasift sample.xlsx sample-filter.json --output matches.ndjson
```

`matches.ndjson` contains:

```json
{"Country":"DE","Amount":1500}
{"Country":"DE","Amount":2400}
```

Next: [JSON Filters](contract.md), [Python API](python-api.md),
[CLI output and failures](cli.md), [Limits & Errors](limits.md).
