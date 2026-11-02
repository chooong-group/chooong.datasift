# Architecture

The public boundary is `chooong.datasift`. Python validates typed masks and adapts
native iterators into immutable rows or event models. Rust owns parsing, discovery,
classification, conversion, validation, predicates, routing, statistics and serialization.
No Python DataFrame or record serializer sits in the native export path.

## Source layout

| Path | Responsibility |
| --- | --- |
| `src/chooong/datasift/models.py` | Canonical Pydantic mask/result models and immutable value objects |
| `src/chooong/datasift/reader.py` | File/mask adapter, iterator lifetime, export and recovery |
| `src/chooong/datasift/__main__.py` | CLI composition and output-path checks |
| `src/chooong/datasift/__init__.py` | Supported public exports |
| `datasift-core/src/lib.rs` | PyO3 bridge, worker/channel and Python value conversion |
| `datasift-core/src/input.rs`, `encoding.rs`, `xlsx.rs` | Input expansion, strict CSV decoding and OOXML adapters |
| `datasift-core/src/discovery.rs`, `engine.rs` | Region discovery and shared row pipeline |
| `datasift-core/src/filter.rs`, `rules.rs`, `value.rs` | Rule compilation, exact conversion and domain values |
| `datasift-core/src/output.rs`, `recovery.rs` | Native serializers and verified journaled commit |
| `release/`, `scripts/`, `tooling/tests/` | Release preparation, artifact/documentation checks and tooling tests |

Maturin builds `datasift-core` into the internal `chooong.datasift.rust` extension
with PyO3's CPython 3.12 stable ABI. The Python package supplies stubs and `py.typed`.
Domain/filter code uses native values; file/PyO3 adapters handle outside boundaries.
Existing native implementation interfaces are not stable consumer APIs.

## Worker ownership

Each scan has a Rust worker, bounded message channel and cancellation flag.
The worker owns its archive/parser state. Python releases the GIL while waiting
for messages; matching values are converted at the bridge. Rejected records are
not constructed as Python objects in the matching-only path. Event mode serializes
both streams in Rust, then validates event models at the Python boundary.

See [streaming](../concepts/streaming.md) for memory/lifetime behavior and
[file safety](../reference/file-safety.md) for recovery authority.
The [core README][core] covers Rust tests and builds.

[core]: https://github.com/chooong-group/chooong.datasift/blob/main/datasift-core/README.md

Build details: [Maturin](https://www.maturin.rs/).
