#!/usr/bin/env python3
"""Run the AppWorld preliminary protocol's deterministic offline regression."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the four-corpus AppWorld body-only BM25 boundary regression. "
            "This offline check exposes search_web/open_page semantics, never "
            "select_docs, and does not run model acquisition, Skill compilation, "
            "reset, or deployment."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--appworld-root",
        type=Path,
        required=True,
        help="existing AppWorld 0.1.0 data root",
    )
    parser.add_argument(
        "--bundle-directory",
        type=Path,
        required=True,
        help="materialized four-corpus AppWorld bundle root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new write-once offline regression output directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    # Keep the AppWorld adapter out of help/startup paths and make this entrypoint's
    # experiment boundary explicit. The adapter itself imports no tau runtime.
    from r2sp.appworld_preliminary import main as appworld_preliminary_main

    return appworld_preliminary_main(
        [
            "--appworld-root",
            str(args.appworld_root),
            "--bundle-directory",
            str(args.bundle_directory),
            "--output",
            str(args.output),
        ]
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
