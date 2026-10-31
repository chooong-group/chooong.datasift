# Known Limits

Supported input is XLSX/XLSM ZIP/XML with UTF-8 and `xl/workbook.xml`. Worksheet
paths are resolved through relationships. There is no XLS/XLSB reader,
encryption support, formula calculation, style interpretation or date detection.
Formula caches are read; without a cache the value is `None`. Numeric Excel dates
remain serial numbers; ISO date cells remain strings. Macros/links are not executed.

The engine does not reconstruct headers spread over multiple physical rows,
expand merged cells, or recognize all possible table layouts. Complete literal
mask schemas drive detection. A repeated single name alone does not distinguish
adjacent tables from duplicate columns. Use explicit sources for ambiguous layouts.

Comment lines below a header are evaluated by `where`. If a comment has values
that satisfy the same business rules as a record, it cannot be distinguished by
formatting alone. Specify `skip_rows`, a data range or a stricter predicate.

Cells use i64 integers or IEEE-754 f64 numbers, not decimal money arithmetic.
Numeric ordering comparisons use f64, including integers. For exact large IDs
beyond floating-point precision use string cells and string equality. There is
no implicit string/boolean-to-number conversion.

Whole worksheets are not materialized, but shared strings, active schema/filter
state, the largest XML token/row and bounded batches consume memory. An XLSX
file's compressed size is not a reliable RAM bound. Read [resource limits](errors.md)
and isolate hostile inputs at process level.
