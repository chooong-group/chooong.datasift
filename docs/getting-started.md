# Getting Started

For the current unreleased package, use a checkout and the source-installation
instructions in [Installation](installation.md). No registry release is claimed.

Create a workbook containing synthetic data:

```bash
python examples/create_sample.py sample.xlsx
```

The script uses exclusive creation and refuses to overwrite an existing file.
The workbook contains a `Data` worksheet with `Country` and `Amount` columns:
DE/1500, AT/2000, DE/900.

```python
from chooong.datasift import FilterMask, Operator, ScalarCondition, iter_matching_rows

mask = FilterMask(
    sheet=None,
    where=ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
)
rows = list(iter_matching_rows("sample.xlsx", mask))
assert [dict(row) for row in rows] == [{"Country": "DE"}, {"Country": "DE"}]
```

The same mask is shipped as `examples/quickstart-filter.json`:

```bash
chooong-datasift sample.xlsx examples/quickstart-filter.json --output matches.ndjson
```

The result contains two lines, each `{"Country":"DE"}`. `Amount` is absent because
it is not referenced by the mask. To filter amounts as well, use an `all` group
containing both the country rule and an amount rule. Group and operator details
are in the [filter reference](contract.md).

Do not infer table identity from duplicate results: records are not deduplicated.
A mask with `sheet: null` is applied to every worksheet independently.
