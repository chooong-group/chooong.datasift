# Advanced filtering

A JSON mask uses `all` (AND), `any` (OR) and `not` to compose conditions. Anchors
locate columns independently of those conditions. CSV numeric comparisons require
explicit conversion; Excel native numbers can be compared directly.

## Combine JSON conditions

Create `orders.csv` and `orders.json`:

```csv
ID,Country,Amount,Status,Customer
one,DE,1500,Open,ABC Berlin
two,AT,2000,Open,abc Wien
three,FR,3000,Open,ABC Paris
four,DE,500,Open,ABC Small
five,DE,2500,Closed,ABC Closed
six,DE,2000,Open,XYZ Other
```

```json
{
  "sheet": null,
  "header": {"anchors": ["ID", "Country", "Amount", "Status", "Customer"]},
  "types": {"Amount": {"type": "integer", "convert": true}},
  "where": {"all": [
    {"any": [
      {"column": "Country", "op": "eq", "value": "DE"},
      {"column": "Country", "op": "eq", "value": "AT"}
    ]},
    {"column": "Amount", "op": "gte", "value": 1000},
    {"not": {"column": "Status", "op": "eq", "value": "Closed"}},
    {"column": "Customer", "op": "regex", "value": "(?i)^abc\\s"}
  ]},
  "select": ["ID", "Amount"]
}
```

```python
from chooong.datasift import iter_matching_rows

assert [dict(row) for row in iter_matching_rows("orders.csv", "orders.json")] == [
    {"ID": "one", "Amount": 1500},
    {"ID": "two", "Amount": 2000},
]
```

The final four rows each fail a different branch. `select` returns ID even though
it is not used by a predicate; Status, Country and Customer still participate in
filtering without being returned. Without `select`, only predicate columns are
returned. See [column selection](column-selection.md) for wildcard and regex output.

The same files work through the CLI:

```bash
chooong-datasift orders.csv orders.json --output orders.ndjson --explain orders-report.json
```

```python
import json
from pathlib import Path

assert [json.loads(line) for line in Path("orders.ndjson").read_text().splitlines()] == [
    {"ID": "one", "Amount": 1500}, {"ID": "two", "Amount": 2000}
]
report = json.loads(Path("orders-report.json").read_text())
assert report["complete"] is True
assert (report["matched"], report["rejected"]) == (2, 4)
```

## Operator limits

Rust regex syntax supports inline flags such as `(?i)` but no lookarounds or
backreferences. JSON needs escaped backslashes, as in `\\s` above. Equality is
type-aware; strings and booleans are not implicitly numeric. Missing/empty checks
and exact Decimal, Money and temporal literals have separate semantics.
Use the [operator reference](../api/filters.md#expressions-and-operators) for all
comparisons, membership, text, emptiness and type checks, and
[limits](../reference/limits.md) for expression/regex bounds.

Python constructors `AllOf`, `AnyOf`, `Not` and condition models serialize to the
same wire contract; [Quickstart](../quickstart.md) shows typed construction.
Apply [different rules per table](complex-layouts.md#different-rules-per-table)
through explicit sources when one shared predicate is insufficient.
