Release license inventory
=========================

One deduplicated inventory covers 113 Rust components potentially redistributed
across the five release targets, including the Rust standard library. Entries
retain exact versions, upstream source URLs and SHA256 hashes, original license
and NOTICE members, copyright evidence and the selected SPDX obligations.
This is a project inventory, not a catalogue of external Python packages, build
tools, operating-system libraries or their dependencies.

Each wheel is checked against its target-filtered Cargo graph and the Maturin
features used for the build. Build dependencies and procedural macros are
separate from linked Rust libraries. A missing runtime entry, unresolved license
obligation or absent/changed required legal text blocks the existing artifact
gate. Merely importing an external shared library does not redistribute it.
Additional bundled native libraries or Python modules require an assessment.

Public original legal texts are stored once in licenses/third-party/ and listed
in THIRD_PARTY_NOTICES.txt. Internal source evidence stays in texts/. Neither
this directory nor audit reports belong in wheels or source distributions.

Run the existing artifact check from the CI checkout:

    uv run --frozen --no-sync python scripts/licenses.py audit --dist bundle/dist --output bundle/licenses/audit.json

Original upstream bytes can also be replayed manually against their recorded
source hashes (not an additional CI gate):

    uv run --frozen --no-sync python scripts/licenses.py verify-sources --fetch

Existing per-artifact CI findings remain the audit record. Commit/tag binding,
checksums, immutable artifacts and publishing verification are unchanged.

Corrections to run 41477934243:
- Removed 953 Cargo entries belonging to separately installed Python packages.
- Excluded foreign targets, build/dev tools and external system imports from
  blocking wheel assessments; active runtime graph coverage remains mandatory.
- Retained zlib-rs 0.6.8's original (C) Trifecta copyright statement.
- Retained Rust 1.95.0's full original COPYRIGHT-library.html notices. Its SGX
  dependency fortanix-sgx-abi is outside every supported release target.
- Bound control files use LF on Windows; original legal bytes are not normalized.
