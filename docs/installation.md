# Installation

Requires CPython 3.12–3.14. The distribution and public Python import are both
named `chooong.datasift`; the CLI is `chooong-datasift`.

## Install with pip

<!-- check: syntax -->

```bash
python -m pip install chooong.datasift
```

Compatible prebuilt wheels do not require a Rust compiler. If no compatible wheel
is available, pip may build from a source distribution and needs the source-build
toolchain described below. Wheel compatibility depends on the interpreter,
operating system and architecture.

Pydantic 2.12 or later, below 3, is the only direct Python runtime dependency.
No server, database, Excel installation or Python DataFrame library is needed.

## Build from source

Install Rust using the toolchain specified in
[`rust-toolchain.toml`](https://github.com/chooong-group/chooong.datasift/blob/main/rust-toolchain.toml),
Cargo and a native linker. Windows source builds need MSVC build tools.
From a source checkout or an extracted source distribution:

<!-- check: syntax -->

```bash
python -m pip install .
```

Maturin builds the native `datasift-core` extension. For development, use the
locked [contributor setup](development/contributing.md).

## Compatibility and upgrades

Pin the package version in applications and validate masks and representative
inputs before upgrading. Consult the
[changelog](https://github.com/chooong-group/chooong.datasift/blob/main/CHANGELOG.md)
for compatibility changes. Internal modules and human-readable error messages
are not stable interfaces. CPython 3.12–3.14 is supported; PyPy and free-threaded
builds are not declared supported.

Continue with the [quickstart](quickstart.md).
