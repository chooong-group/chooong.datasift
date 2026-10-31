# Multiple Sheets and Tables

`sheet` is required. A nonempty string chooses one named worksheet; JSON `null`
scans all worksheets, including hidden ones, in workbook order. The string
`"null"` is an actual sheet name. Chart sheets without worksheet rows are skipped.
No extra sheet/table fields are added, and identical records are not deduplicated.

Each automatically detected table owns its own column bindings and compiled
predicate. A row with at least two complete groups of the mask's literal names
can describe adjacent tables; each group contains every mask name once. At least
two distinct mask columns are needed to distinguish this case from duplicate
columns. Partial patterns are not guessed. Horizontally repeated schemas using
internally indexed names may need [explicit sources](sources.md).

A later complete header replaces active areas whose intervals between the first
and last selected columns overlap it. Independent neighboring tables continue,
even when their records share a row with a new header. Blank rows/comments do
not infer the end of a table. Output follows workbook order, then row number,
then the table's leftmost selected column.

A selected sheet with no complete schema raises `ValueError`. In an all-sheet
scan, an unmatched worksheet contributes no records; a workbook with no matching
schema produces an empty result. Missing columns are not treated as empty values.

Batches never cross sheet boundaries. Tables with the same output order can share
a batch; the batch is flushed before changing output column order. This prevents
one table's values from being interpreted using another table's schema. A late
error still invalidates the CLI file output as a whole.
