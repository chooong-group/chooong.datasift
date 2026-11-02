# Releasing

No automated publishing workflow is configured. CI runs source checks, Python and
Rust tests, documentation checks and wheel/sdist builds on Linux. It does not
validate a complete cross-platform release set.

Before an approved release, synchronize the Python/Cargo versions and release
notes, build distributions from a clean reviewed commit and run `twine check`.
Install and test the exact distributions in clean environments on every intended
platform under Python 3.13 and 3.14. Record the tested files and results in the PR.
Publishing requires a separate release decision and a reviewed publishing process.

GitHub Pages deployment remains disabled in `docs-pages.yml`.
