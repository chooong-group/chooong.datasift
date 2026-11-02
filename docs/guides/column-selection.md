# Column selection

`select` controls output independently of filtering and validation. Entries can
be names, `"*"` or regex selections. Expansion follows list order; wildcard/regex
matches follow physical column order (explicit sources use binding order).
The first occurrence of a name wins.

## Names, regex and wildcard together

```python
from pathlib import Path

from chooong.datasift import (
    FilterMask, HeaderConfig, Operator, RegexSelection, ScalarCondition,
    iter_matching_rows,
)

Path("columns.csv").write_text(
    "ID,Country,Revenue_EUR,Revenue_USD,Note\na,DE,12,15,first\nb,AT,20,25,second\n",
    encoding="utf-8",
)
mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("ID", "Country")),
    where=ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
    select=("Note", RegexSelection(pattern="^Revenue_"), "*", "ID"),
)
rows = list(iter_matching_rows("columns.csv", mask))
assert [dict(row) for row in rows] == [{
    "Note": "first", "Revenue_EUR": "12", "Revenue_USD": "15", "ID": "a", "Country": "DE",
}]
assert list(rows[0]) == ["Note", "Revenue_EUR", "Revenue_USD", "ID", "Country"]
```

Here `"*"` adds ID and Country after the revenue fields. The final ID does not
repeat it. The wire equivalent of `RegexSelection(pattern="^Revenue_")` is
`{"pattern": "^Revenue_"}`; these are Rust regular expressions, not shell globs.
A string such as `"Revenue_*"` is a literal column name, not a wildcard pattern.

Omit `select` with `where` to return only names referenced in the filter. Omit
both to return every discovered/bound column. This does not turn `select` into a
discovery schema: use anchors when column names should guide discovery.

Unknown names or regex selections with no matches cause schema errors, rather
than silently omitting requested output. Required/default/type rules can reject
a row even when those columns are not selected. See the
[projection reference](../api/filters.md#projection) and
[validation guide](validation.md).
