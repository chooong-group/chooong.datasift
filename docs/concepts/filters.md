# Filters and the row pipeline

A mask describes where to discover columns, which rows to consider, how to
validate values and what to return. Discovery and filtering are separate:
`header.anchors` locates a schema while `where` evaluates records in that schema.
With no anchors, `where` column names guide discovery. With neither, structural
[table discovery](table-discovery.md) applies.

## Processing order

1. Discover headers or bind an explicit source.
2. Classify the original row and apply `row_policy`.
3. Preserve original values for a possible rejection.
4. Replace null/empty values using configured defaults.
5. Apply explicit type rules and validate required fields.
6. Evaluate `where` against the effective values.
7. Route matches/rejects and project matched values.

Defaults cannot invent columns. Missing schema bindings are schema errors;
invalid values in an existing column are row rejections. A default never replaces
zero, false or a nonempty invalid value.

## Predicates and projection

`all`, `any` and `not` compose comparisons. Omitting `where` selects every valid
data row. `select` controls output independently of validation and filtering.
Without `select`, a predicate returns its referenced columns; without either,
all bound columns are returned.

[Filter models and operators](../api/filters.md) is the normative reference for
field names, aliases, defaults, operator semantics and projection order.
[Validation](../guides/validation.md) demonstrates the complete pipeline.
For executable workflows, use [advanced JSON filters](../guides/advanced-filtering.md)
and [column selection](../guides/column-selection.md).
