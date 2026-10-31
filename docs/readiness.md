# Validation and Release Blockers

Status: **NOT RELEASE-READY**. The repository is private, hosted compute is gated
off, publishing/Pages are hard-disabled, and the native release matrix has not
been executed by this preparation. No publication, tag, merge, visibility change
or external account/environment configuration is claimed.

The exact final local commands, artifact identities and platform results will be
recorded here after implementation checks. Unexecuted platforms stay release
blockers; a cross-build, static workflow check or synthetic gate fixture is not a
native runtime test.

| Target | CPython 3.13 | CPython 3.14 | Release status |
| --- | --- | --- | --- |
| Linux x86_64 / manylinux 2.28 | UNVERIFIED | UNVERIFIED | BLOCKED |
| Linux aarch64 / manylinux 2.28 | UNVERIFIED | UNVERIFIED | BLOCKED |
| Windows x86_64 | UNVERIFIED | UNVERIFIED | BLOCKED |
| macOS x86_64 | UNVERIFIED | UNVERIFIED | BLOCKED |
| macOS arm64 | UNVERIFIED | UNVERIFIED | Pending local evidence |
| sdist build/install | UNVERIFIED | UNVERIFIED | Pending local evidence |

## Open acceptance items

- Native wheel and fixture runs for every platform, with matching commit/version
  and SHA-256-bound evidence, followed by a successful complete-set gate.
- Independent review of fork permissions, immutable artifact handoff, upload guard,
  matrix coverage and metadata. Self-reported implementation does not close review.
- Owner decision resolving the private-repository compute restriction without
  silently incurring charges or changing visibility.
- External PyPI Pending Trusted Publisher and protected `pypi` environment,
  including effective required-review and branch protections.
- Separate owner approval and reviewed activation before any upload or Pages
  deployment; [exact steps](releases.md) are documented, not executed.
