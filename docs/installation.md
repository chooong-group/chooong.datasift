# Installation

DataSift 0.1.0 is unreleased. There is no published package to install from PyPI.
Use a checkout or a wheel supplied by a maintainer. The distribution and public
Python import are both named `chooong.datasift`; the CLI is `chooong-datasift`.

## From source

Use CPython 3.12, 3.13 or 3.14, Rust 1.95.0, Cargo and a native linker.
Windows source builds need MSVC build tools. From the repository root:

<!-- check: syntax -->

```bash
python -m pip install .
```

For development, use the locked [contributor setup](development/contributing.md).
Maturin builds the native `datasift-core` extension. The only direct Python
runtime dependency is Pydantic 2.12 or later, below 3.

## From a wheel

A wheel matching your operating system and architecture needs no Rust compiler.
The build targets CPython's 3.12 stable ABI; supported interpreters remain
CPython 3.12–3.14. From a directory containing exactly the intended wheel:

<!-- check: syntax -->

```bash
python -m pip install ./chooong_datasift-0.1.0-cp312-abi3-macosx_11_0_arm64.whl
```

This filename is for Apple Silicon macOS; use the actual artifact for your machine.
The release configuration targets Linux x86_64/ARM64, macOS x86_64/ARM64 and
Windows x86_64. A configured target is not evidence of a published or tested wheel.

Continue with the [quickstart](quickstart.md). No server, database, Excel
installation or Python DataFrame library is needed.
