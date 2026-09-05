#!/usr/bin/env python3
"""Materialize AppWorld Benign/Poison corpora from editable body-only payloads."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from r2sp.appworld_preliminary import materialize_content_addressed

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPWORLD_ROOT = EXPERIMENT_ROOT / "data" / "appworld-0.1.0"
DEFAULT_PAYLOAD_DIRECTORY = EXPERIMENT_ROOT / "injections"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or verify an immutable, payload-hash-addressed AppWorld corpus. "
            "This phase does not retrieve, compile, or deploy."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--appworld-root",
        type=Path,
        default=DEFAULT_APPWORLD_ROOT,
        help="existing AppWorld 0.1.0 data root",
    )
    parser.add_argument(
        "--payload-directory",
        type=Path,
        default=DEFAULT_PAYLOAD_DIRECTORY,
        help="directory containing the two exact UTF-8 injection body files",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="parent directory for payload-set-<sha256>",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    import json

    result = materialize_content_addressed(
        appworld_root=args.appworld_root,
        payload_directory=args.payload_directory,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
