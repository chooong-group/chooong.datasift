# JSON Schema

Generate schemas from the installed Pydantic models rather than maintaining a
second hand-written schema. Wire aliases must be enabled:

```python
import json
from pathlib import Path

from chooong.datasift import FilterMask

schema = FilterMask.model_json_schema(by_alias=True)
assert "sheet" in schema["required"]
assert "all" in schema["$defs"]["AllOf"]["properties"]
Path("filter.schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
```

Pydantic emits JSON Schema Draft 2020-12. Recursive groups live under `$defs`.
Schema generation describes structural fields/types, not every native constraint:
regex syntax, actual ISO currency membership, exact temporal/numeric literals,
resolved column names and cross-field source bounds still require runtime validation.

## Validate a mask

```python
payload = '{"sheet":null,"where":{"column":"Country","op":"eq","value":"DE"}}'
mask = FilterMask.model_validate_json(payload, by_name=False)
assert mask.model_dump(by_alias=True)["where"]["op"] == "eq"
```

Use public `FilterMask` input plus a real reader/export to validate native semantics.
`model_construct` and unchecked copies are not validation APIs; readers revalidate
model instances. Mapping/JSON readers reject Python-only group keys such as
`conditions`, and unknown fields fail closed.

The contract is v1 without a version field. [Filter models](filters.md) is its
human-readable reference. Changes to the canonical models change generated schemas;
consumers should pin a compatible package version and test their masks when upgrading.
