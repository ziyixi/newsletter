"""Offline bundle build/validation; no credentials, providers or service state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from newsletter.content_config import _atomic_json, build_directory, read_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--revision", required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            snapshot = build_directory(args.source, args.revision)
            output = args.output.absolute()
            if any(part.is_symlink() for part in (output, *output.parents)):
                raise ValueError()
            if not output.parent.is_dir():
                raise ValueError()
            _atomic_json(output, snapshot)
        else:
            snapshot = read_snapshot(args.bundle)
    except (OSError, ValueError, UnicodeError, RecursionError):
        print("CONTENT_CONFIG_INVALID", file=sys.stderr)
        return 1
    print(json.dumps({key: snapshot[key] for key in ("revision", "digest", "editorial")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
