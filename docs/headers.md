# Automatic Header Detection

Without `source`, the mask's exact column names drive header detection. A complete
header must supply every referenced name, including names in `any` and `not`.
Titles, numeric cells and incomplete rows before a schema do not define a table.
There is no fixed `header_row` setting; that removed field is rejected.

Line breaks within a cell belong to the name: `"Amount\nEUR"` is a valid mask
column. Literal XML CRLF/CR line endings are normalized to LF when reading shared
strings, inline strings and CDATA. Explicit character references preserve the
referenced character. Names are not trimmed or case-folded.

Within one row schema, duplicate labels receive indices from left to right:
`Amount`, `Amount` become `Amount_1`, `Amount_2`; all occurrences are numbered.
Unique names remain unchanged. Referencing the ambiguous base name is invalid.
A selected name collision after indexing is rejected rather than overwriting a value.

Repeated complete groups of the mask's literal names can instead describe
[independent neighboring tables](tables.md). A later complete header can start a
new table. Such header values are structural, not records of the new table; real
records identical to all selected header texts are indistinguishable in automatic
mode and need explicit source bounds.

The engine does not reconstruct headings spread across multiple physical rows,
expand merged cells, or infer arbitrary business semantics from formatting.
Use [explicit column bindings](sources.md) for those cases. The detailed rules
and ambiguous cases are defined in the [canonical contract](contract.md).
