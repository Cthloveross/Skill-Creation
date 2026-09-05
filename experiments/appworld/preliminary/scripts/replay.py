#!/usr/bin/env python3
"""Verify and print a completed AppWorld run without rerunning any agent."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from r2sp.cli import main as r2sp_main


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the existing immutable-artifact verifier for one completed "
            "AppWorld run. No model, retriever, compiler, or deployment is executed."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--run-directory",
        type=Path,
        required=True,
        help="completed write-once run directory",
    )
    parser.add_argument(
        "--expected-complete-sha256",
        required=True,
        help="externally recorded SHA-256 of complete.json",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "csv"),
        default="json",
        help="verified report representation to print",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return r2sp_main(
        [
            "report",
            "--run-directory",
            str(args.run_directory),
            "--expected-complete-sha256",
            args.expected_complete_sha256,
            "--format",
            args.format,
        ]
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
