# chooong.datasift

[![CI][ci-badge]][ci]
[![PyPI version][pypi-badge]][pypi]
[![Python versions][python-badge]][installation]
[![License: Apache-2.0][license-badge]][license]

[ci-badge]: https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml/badge.svg
[ci]: https://github.com/chooong-group/chooong.datasift/actions/workflows/ci.yml
[pypi-badge]: https://img.shields.io/pypi/v/chooong.datasift.svg
[pypi]: https://pypi.org/project/chooong.datasift/
[python-badge]: https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue
[license-badge]: https://img.shields.io/badge/license-Apache--2.0-blue
[installation]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/installation.md
[license]: https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE

Extract, validate and filter tables from XLSX/XLSM and CSV with a JSON mask.
Rust streams rows and writes NDJSON/Parquet; Python exposes typed, immutable
results. Automatic table discovery finds headers away from A1 and multiple table
regions in Excel and CSV without fixed coordinates in the mask. Start with the
[discovery guide][discovery-guide] for Named-column and Free Discovery examples.

[discovery-guide]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/automatic-table-discovery.md

## Installation

Requires CPython 3.12–3.14.

```bash
python -m pip install chooong.datasift
```

Compatible prebuilt wheels do not require a Rust compiler.
Building from source requires Rust, Cargo and a native linker.

See the [installation guide][installation] for details.
Pydantic is the only direct Python runtime dependency; no external service is needed.

## Features

### Input formats

- Read **XLSX, XLSM and CSV** files without loading entire worksheets into a DataFrame.
- Process multiple files and wildcard paths in deterministic order.
- Scan individual Excel worksheets or all worksheets in a workbook.
- Configure CSV encodings, delimiters and quoting, including multiline fields.
- Read cached Excel formula results without executing formulas or macros.

### Table discovery

- Automatically discover tables that do not start at A1.
- Detect multiple tables within a worksheet, including adjacent and vertically separated tables.
- Join a configured number of physical header rows, recognize repeated headers and optionally fill
  actual Excel merged ranges; [discovery limits][discovery-limits] depend on the mode.
- Normalize column names with trimming, case conversion, Unicode normalization, whitespace handling
  and aliases.
- Resolve duplicate column names with deterministic suffixes.
- Locate tables using header anchors independently of filter conditions.
- Define explicit table sources with column mappings, row ranges and excluded rows.
- Apply independent rules to different table sources.
- Detect ambiguous layouts instead of silently guessing table boundaries.

Named-column Discovery uses anchors or filter column names, including for text-only data.
Free Discovery needs scalar evidence immediately after each candidate header.
Comments and totals require explicit row rules or predicates; their meaning is not inferred.
CSV table discovery does not sniff delimiters or encodings.

[discovery-limits]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/complex-layouts.md#supported-layouts-and-limits

### Filtering and column selection

- Define filters using JSON or typed Python models.
- Combine conditions with **AND, OR and NOT**.
- Compare values using equality, inequality, ordering and list membership.
- Filter text using substring, prefix, suffix and regular-expression matching.
- Check for empty values and specific data types.
- Select output columns independently of filter conditions.
- Select columns by name, wildcard or regular expression.
- Control output column order without modifying the source.
- Filter and select data directly in the native Rust engine.

### Validation and data types

- Enforce **required fields** and reject records with missing values.
- Replace missing values with configurable defaults.
- Validate column types and optionally convert values.
- Support strings, integers, floats, booleans, Decimal, money, dates and datetimes.
- Parse localized numeric and monetary values.
- Preserve exact decimal and monetary values without implicit rounding.
- Handle Excel date systems, ISO dates and timezone-aware datetimes.
- Apply validation independently of output column selection.
- Preserve original values and detailed rejection reasons for invalid records.

### Row processing and streaming

- Classify rows as data, headers, repeated headers, empty rows, comments, totals or separators.
- Include or exclude row classes using configurable rules.
- Stream results in bounded batches with backpressure.
- Iterate over matching rows or receive matched and rejected records in a single ordered stream.
- Return immutable, typed Python row objects.
- Support early cancellation and explicit iterator cleanup.
- Report row counts, conversions, defaults, rejections and discovered table schemas.

### Export and reliability

- Export matching and rejected records to **NDJSON or Parquet**.
- Write output directly from Rust without Python-side row serialization.
- Preserve source metadata in rejected NDJSON and both Parquet outputs; matched NDJSON contains
  projected values only. Rejected outputs also retain rejection details.
- Preserve existing output files when scanning or serialization fails.
- Use journaled commits and verified recovery for interrupted file replacements.
- Continue processing independent tables after schema errors.
- Optionally continue processing remaining input files after file errors while reporting incomplete results.
- Enforce documented parser, schema, expression and resource limits.

### Python API and CLI

- Use the same filter configuration through Python and the command-line interface.
- Validate JSON masks with Pydantic and generate JSON Schema.
- Access matching rows, batches, detailed scan records and scan statistics.
- Inspect discovered tables, column bindings and diagnostics.
- Use CLI output files, stdout streaming and JSON execution reports.
- Support CPython **3.12, 3.13 and 3.14** with a native Rust extension.

## Example

This example creates its own input:

```python
from pathlib import Path

from chooong.datasift import (
    AllOf,
    DataType,
    FilterMask,
    HeaderConfig,
    NumericCondition,
    Operator,
    ScalarCondition,
    TypeRule,
    iter_matching_rows,
)

Path("transactions.csv").write_text(
    "Country,Amount,Note\nDE,1500,first\nAT,2000,second\nDE,900,third\n",
    encoding="utf-8",
)

mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("Country", "Amount")),
    types={"Amount": TypeRule(type=DataType.INTEGER, convert=True)},
    where=AllOf(conditions=(
        ScalarCondition(column="Country", op=Operator.EQ, value="DE"),
        NumericCondition(column="Amount", op=Operator.GTE, value=1000),
    )),
)

rows = [dict(row) for row in iter_matching_rows("transactions.csv", mask)]
assert rows == [{"Country": "DE", "Amount": 1500}]

Path("mask.json").write_text(
    mask.model_dump_json(by_alias=True),
    encoding="utf-8",
)
```

Run the same filter from the CLI:

```bash
chooong-datasift transactions.csv mask.json --output matches.ndjson
```

## Column selection and validation

DataSift separates row filtering, column selection and validation. Use `select` to choose output
columns, `types` to convert values and `required` to reject records with missing values.

```python
from pathlib import Path

from chooong.datasift import (
    DataType,
    FilterMask,
    HeaderConfig,
    NumericCondition,
    Operator,
    TypeRule,
    iter_matching_rows,
)

Path("orders.csv").write_text(
    "Country,Amount,Reference\n"
    "DE,1500,INV-001\n"
    "DE,2200,\n"
    "AT,1900,INV-003\n"
    "DE,900,INV-004\n",
    encoding="utf-8",
)

mask = FilterMask(
    sheet=None,
    header=HeaderConfig(anchors=("Country", "Amount", "Reference")),
    select=("Reference", "Amount"),
    required=("Reference",),
    types={
        "Amount": TypeRule(type=DataType.INTEGER, convert=True),
    },
    where=NumericCondition(
        column="Amount",
        op=Operator.GTE,
        value=1000,
    ),
)

rows = [dict(row) for row in iter_matching_rows("orders.csv", mask)]

assert rows == [
    {"Reference": "INV-001", "Amount": 1500},
    {"Reference": "INV-003", "Amount": 1900},
]
```

The mask applies three independent operations:

- **Column selection:** `select` returns only `Reference` and `Amount`, in that order. `Country` is excluded.
- **Type conversion:** `types` converts CSV text in `Amount` to integers before numeric comparison.
- **Required fields:** `required` rejects records where `Reference` is missing or empty.

The `where` condition matches amounts greater than or equal to 1000.

The record with amount 2200 is rejected because its reference is missing. The record with amount 900
does not match the filter. Neither appears in the matching results.

Rejected records remain available through `scan_batches`, including their original values and
rejection reasons.

See the [filter reference][filter-reference] for the complete configuration and the
[validation guide][validation-guide] for handling rejected records.

[filter-reference]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/api/filters.md
[validation-guide]: https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/validation.md

## Documentation and limits

Start with [installation](https://github.com/chooong-group/chooong.datasift/blob/main/docs/installation.md)
and the [quickstart](https://github.com/chooong-group/chooong.datasift/blob/main/docs/quickstart.md).
The [documentation](https://github.com/chooong-group/chooong.datasift/blob/main/docs/index.md)
links guides, exact Python/CLI references and the filter schema. Practical workflows:

- [JSON filters](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/advanced-filtering.md)
  and [column selection](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/column-selection.md).
- [Per-table rules](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/complex-layouts.md#different-rules-per-table)
  and [inspection/diagnostics](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/table-inspection.md).
- [Batch processing](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/batch-processing.md)
  and [partial results](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/error-handling.md).
- [Export formats](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/exporting.md)
  and [resource use](https://github.com/chooong-group/chooong.datasift/blob/main/docs/guides/performance.md).

XLS/XLSB, encrypted workbooks, formula calculation and Excel output are unsupported.
Formula caches are read. Shared strings and metadata use memory despite row
streaming. Ambiguous layouts require anchors or explicit sources. A late scan
failure may follow partial iterator/stdout results; exported results use a
journaled commit, not a shared atomic two-file replacement. See
[file safety](https://github.com/chooong-group/chooong.datasift/blob/main/docs/reference/file-safety.md).

Public imports come from `chooong.datasift`. Python validates masks; the
[Rust core](https://github.com/chooong-group/chooong.datasift/blob/main/datasift-core/README.md)
owns parsing and the row pipeline. For development, use `uv sync --frozen` and
[Contributing](https://github.com/chooong-group/chooong.datasift/blob/main/CONTRIBUTING.md).

[Changelog](https://github.com/chooong-group/chooong.datasift/blob/main/CHANGELOG.md) ·
[Security](https://github.com/chooong-group/chooong.datasift/blob/main/SECURITY.md) ·
[Apache-2.0 license](https://github.com/chooong-group/chooong.datasift/blob/main/LICENSE) ·
[Third-party notices][third-party-notices] ·
[Support development](https://github.com/sponsors/marcus-steinbach)

[third-party-notices]: https://github.com/chooong-group/chooong.datasift/blob/main/THIRD_PARTY_NOTICES.txt
