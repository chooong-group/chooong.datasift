# chooong.datasift

Filter XLSX and XLSM worksheets with a JSON mask or typed Python models.
Rust streams worksheet XML and evaluates predicates; Python receives only
matching values as immutable rows. The CLI emits NDJSON and can replace a file
atomically after a successful complete scan.

The package is **unreleased**. CPython 3.13 and 3.14 are the declared Python
versions. The five native wheel targets must pass their runtime tests before a
release is eligible; see [validation and release blockers](readiness.md).

Start with [Getting Started](getting-started.md). The
[JSON filter reference](contract.md) is the canonical public contract. Learn when
to use [automatic headers](headers.md) or [explicit sources](sources.md), and read
[limits](limits.md) before processing unfamiliar workbooks.

The documentation site is prepared for GitHub Pages. Deployment is disabled;
these Markdown files are usable directly in the repository meanwhile.
