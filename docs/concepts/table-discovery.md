# Table discovery

DataSift has two automatic discovery modes. Use explicit
[column mapping](column-mapping.md) when neither describes your layout.

## Named-column discovery

With `header.anchors`, the anchor names define the discovery schema independently
of `where`. Otherwise, names referenced anywhere in `where` define that schema.
Only nonblank text cells are header labels; matching is exact unless normalized.
The old top-level `header_row` field is not accepted.

A row containing at least two complete groups of the literal required names can
start adjacent tables. Each group must contain every name once, with at least two
distinct names. A repeated single name cannot distinguish tables from duplicate
columns. Partial groups and horizontally repeated indexed names need explicit sources.

A later complete header replaces overlapping active column intervals; independent
neighbors continue. Blank rows do not end these tables. Comments are ordinary
rows unless explicit rules or predicates exclude them. A record identical to a
complete header is structural, not data; use explicit sources to retain it.
Output is ordered by file, worksheet, physical row, then leftmost selected column.

## Free discovery

Without anchors or `where`, a contiguous run of at least `header.min_columns`
nonempty text cells is a candidate (default 2). `header.rows` physical rows form
its header. The immediately following physical record must contain a native
non-text scalar or text parseable as a finite number, ISO date or ISO datetime.
This is evidence, not implicit type conversion.

Blank column gaps separate regions. A fully empty physical row in a region
closes it; missing worksheet row numbers are not synthesized as blank rows.
The same confirmation rule applies to first, later and adjacent regions.
Repeated physical headers are structural rows. Text-only candidates, unconfirmed
EOF candidates and unexpected all-text rows inside a confirmed region are
ambiguous. They produce `AMBIGUOUS_HEADER` and `SCHEMA_MISMATCH`, quarantine that
region and make the scan fail after independent regions finish.

Use anchors or sources for text-only tables, comments in free layouts, titles
spanning several text columns or schemas without blank boundaries. Cell content
does not establish business meaning.

## Header names

Within one schema, repeated labels become `Amount_1`, `Amount_2`, from left to
right; unique labels stay unchanged. Blank cells do not affect indices. Selected
collisions with existing suffixed names fail. Explicit source aliases are not
indexed automatically.

Normalization applies Unicode (`NFC`/`NFKC`), whitespace collapsing, trimming,
lowercasing, then aliases. Rules refer to final names. Distinct labels that
normalize to one name quarantine their region. Untrustworthy-schema rejects use
physical column keys such as `A` and `B`, preserving original values.

`header.rows` joins physical header lines with spaces. Free discovery retains a
bounded window per region; named-column discovery uses a sliding window before
its first table. Later physical multiline headers in named-column mode are not
reconstructed generally; use header-bound sources for known windows.

[Excel](../guides/excel.md) covers worksheet selection and line endings;
[complex layouts](../guides/complex-layouts.md) shows source windows and merged headers.
