# Installation

## Current source installation

The project has not been published by this preparation. Install from a checkout:

```bash
python -m pip install .
# or:
uv pip install .
```

Use an active environment with CPython 3.13 or 3.14. Source builds require Rust
1.95.0, Cargo, and the platform's native C linker/toolchain. Windows source builds
need the MSVC build tools. Python installs the pinned Maturin build backend.
The toolchain is fixed by `rust-toolchain.toml`; Cargo dependencies are locked.

For development use `uv sync --frozen`, which includes the locked test, lint and
documentation dependencies. No external service, database or environment
configuration is needed for filtering.

## Wheels and future registry installation

A wheel compatible with your interpreter/platform can be installed without Rust:

```bash
python -m pip install path/to/the-built-wheel.whl
# or:
uv pip install path/to/the-built-wheel.whl
```

Replace the path with an actual built artifact. The runtime dependency is
Pydantic, installed by pip/uv. Registry commands `pip install chooong.datasift` and
`uv pip install chooong.datasift` are only appropriate after the first approved
release exists. There is currently no verified public PyPI version badge.

## Release targets

| Platform | Candidate wheel tag | Native runtime required |
| --- | --- | --- |
| Linux x86_64 | `cp313-abi3-manylinux_2_28_x86_64` | Linux x86_64 |
| Linux aarch64 | `cp313-abi3-manylinux_2_28_aarch64` | Linux aarch64 |
| Windows x86_64 | `cp313-abi3-win_amd64` | Windows x86_64 |
| macOS x86_64 | `cp313-abi3-macosx_11_0_x86_64` | Intel macOS |
| macOS arm64 | `cp313-abi3-macosx_11_0_arm64` | Apple Silicon macOS |

These are targets, not blanket compatibility guarantees. The Linux baseline is
glibc 2.28; musl is not targeted. Native tests under **both** Python 3.13 and 3.14
are required for each wheel despite the common ABI3 tag. An sdist is additionally
built and installed under both versions. See [actual results](readiness.md).
