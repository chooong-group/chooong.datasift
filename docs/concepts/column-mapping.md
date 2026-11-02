# Column mapping

Automatic discovery derives names from text. Explicit sources instead make
coordinates part of the mask, useful for neighboring tables, comments and
ambiguous headers.

## Explicit bindings

`TableSource.columns` binds a nonblank output/filter alias to an uppercase Excel
column `A` through `XFD`. Aliases must be unique; several aliases can refer to one
physical column. Header text is not interpreted. `data_start_row` is required,
`data_end_row` is inclusive and optional, and `skip_rows` lies inside those bounds.

Use `source` for one region or `sources` for several. They are mutually exclusive.
Each source may have a unique name and a sheet restriction. An omitted/null source
sheet applies to every top-level selected worksheet. A source's `rules` replaces
the entire shared rule set, including defaults; it is not a partial merge.
Overlapping explicit regions intentionally emit a record for each source.

## Header-bound sources

Alternatively omit `columns` and supply `header_start_row`. Optional
`first_column`/`last_column` bound the header window. `header.rows` determines its
height; the whole header must precede `data_start_row`. This mode retains real
header names and normalization while using known row coordinates.

Values outside explicit scope are not converted. XML structure, coordinates and
resource limits are still checked throughout the worksheet, even after the end
bound. A corrupt tail remains an error.

CSV uses the same column letters for record positions and logical record numbers
for source rows. See [CSV](../guides/csv.md).
[Complex layouts](../guides/complex-layouts.md) contains a runnable example;
[filter models](../api/filters.md) lists exact constraints.
