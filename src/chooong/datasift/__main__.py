"""CLI composition root; all record serialization stays in Rust."""

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from chooong.datasift import export, rust
from chooong.datasift.reader import _load_mask, _validate_batch_size


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    xlsx: list[Path]
    mask: Path
    batch_size: int
    output: Path | None
    rejected_output: Path | None
    explain: Path | None


def _validate_outputs(args: _Arguments, parser: argparse.ArgumentParser) -> list[Path]:
    destinations = [p for p in (args.output, args.rejected_output, args.explain) if p is not None]
    resolved = [p.resolve() for p in destinations]
    if len(set(resolved)) != len(resolved):
        parser.error("Output paths must be different")
    expanded = [Path(path) for path in rust.expand_inputs([str(path) for path in args.xlsx])]
    inputs = [args.mask, *expanded]
    reserved = {
        path.with_name(f".{path.name}.datasift.lock").resolve()
        for path in (args.output, args.rejected_output)
        if path is not None
    }
    if args.output is not None:
        reserved.add(args.output.with_name(f".{args.output.name}.datasift-commit.json").resolve())
    if any(path in reserved for path in resolved):
        parser.error("Outputs must not overwrite commit/lock metadata")
    for destination in destinations:
        if destination.is_symlink():
            parser.error("Output must not be a symlink")
        for source in inputs:
            if destination.resolve() == source.resolve() or (
                destination.exists() and source.exists() and destination.samefile(source)
            ):
                parser.error("Outputs must not overwrite inputs or the filter file")
    if args.rejected_output is not None and args.output is None:
        parser.error("--rejected-output requires --output")
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description="Process Excel/CSV with the native Rust pipeline")
    parser.add_argument("xlsx", nargs="+", help="XLSX/XLSM/CSV files or glob patterns")
    parser.add_argument("mask", help="JSON filter file")
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--output", type=Path, help="NDJSON or .parquet")
    parser.add_argument("--rejected-output", type=Path, help="Rejected original records")
    parser.add_argument("--explain", type=Path, help="Statistics and diagnostics as JSON")
    args = _Arguments.model_validate(vars(parser.parse_args()))
    statistics: str | None
    try:
        expanded = _validate_outputs(args, parser)
        if args.output is not None:
            statistics = export(
                expanded,
                args.mask,
                args.output,
                rejected_output=args.rejected_output,
                batch_size=args.batch_size,
            ).model_dump_json()
        else:
            spec = _load_mask(args.mask)
            _validate_batch_size(args.batch_size)
            batches = rust.iter_json(
                [str(path) for path in expanded],
                spec.model_dump_json(by_alias=True),
                args.batch_size,
            )
            try:
                for batch in batches:
                    for line in batch:
                        sys.stdout.write(line + "\n")
                statistics = batches.statistics_json()
            finally:
                batches.close()
        if args.explain is not None and statistics is not None:
            args.explain.write_text(statistics + "\n", encoding="utf-8")
    except (ValueError, RuntimeError, OSError) as error:
        sys.stderr.write(f"Filter error ({type(error).__name__}); output incomplete.\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
