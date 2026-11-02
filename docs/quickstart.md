# Quickstart

This example creates its own CSV input, selects German transactions worth at
least 1000, and writes a reusable JSON mask. No example download is needed.

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

CSV starts with text cells, so the numeric rule enables explicit integer
conversion. Without `select`, only columns referenced by `where` are returned;
`Note` is omitted. The [filter reference](api/filters.md) defines these rules.

## Run the CLI

Use the files created above:

```bash
chooong-datasift transactions.csv mask.json --output matches.ndjson
```

The file contains:

```jsonl
{"Country":"DE","Amount":1500}
```

```python
import json

assert [json.loads(line) for line in Path("matches.ndjson").read_text().splitlines()] == rows
```

For XLSX/XLSM, pass the workbook path and its worksheet name, or `sheet=None`
for all worksheets. [Excel](guides/excel.md) shows tables outside A1;
[validation](guides/validation.md) adds defaults and rejected records;
[exporting](guides/exporting.md) explains durable output.
