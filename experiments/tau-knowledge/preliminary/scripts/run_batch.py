#!/usr/bin/env python3
"""Validate, create, evaluate, or replay independent benign Tau batches."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from getpass import getuser
from pathlib import Path
from typing import Any

from batch_source import source_provenance, verified_bundle, verify_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "evaluate"):
        child = commands.add_parser(command, allow_abbrev=False)
        child.add_argument("--spec", type=Path, required=True)
        child.add_argument("--runs-root", type=Path, required=True)
        child.add_argument("--resume", type=Path)
        child.add_argument(
            "--scripted", action="store_true", help="synthetic harness check; no model metrics"
        )
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--spec", type=Path, required=True)
    validate.add_argument("--phase", choices=("create", "evaluate"), required=True)
    replay = commands.add_parser("replay", allow_abbrev=False)
    replay.add_argument("root", type=Path)
    replay.add_argument("--complete-sha256")
    return parser


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from r2sp_tau_knowledge.batch import (
            ScriptedBatchBackend,
            load_spec,
            replay_batch,
            run_creation,
            run_evaluation,
        )

        if args.command == "replay":
            _print(replay_batch(args.root, complete_sha256=args.complete_sha256))
            return 0
        phase = args.phase if args.command == "validate" else args.command
        spec = load_spec(args.spec, "creation" if phase == "create" else "evaluation")
        if args.command == "validate":
            _print({"status": "VALID", "scope": "benign-only", "spec": spec.to_dict()})
            return 0
        execution_mode = "scripted" if args.scripted else "live"
        if args.command == "evaluate":
            available_skills: dict[str, set[str]] = {}
            for source in spec.sources:
                source_root = Path(source["root"])
                report = replay_batch(source_root, complete_sha256=source["complete_sha256"])
                if report["phase"] != "creation" or report["execution_mode"] != execution_mode:
                    raise ValueError(
                        "evaluation requires creation sources with matching execution mode"
                    )
                source_spec = json.loads((source_root / "spec.json").read_text())
                available_skills[source["source_id"]] = {
                    item["skill_id"] for item in source_spec["items"]
                }
            for trial in spec.trials:
                if trial["skill_id"] not in available_skills[trial["source_id"]]:
                    raise ValueError("evaluation trial references a Skill absent from its source")
        bundle_directory = args.runs_root.resolve() / "source-bundles"
        if bundle_directory.is_relative_to(PROJECT_ROOT):
            bundle_directory = Path(tempfile.gettempdir()) / f"tau-v2-source-bundles-{getuser()}"
        provenance = source_provenance(PROJECT_ROOT, bundle_directory)
        provenance["execution_mode"] = execution_mode

        def pre_publish_check() -> None:
            _, members = verified_bundle(
                Path(provenance["source_bundle_path"]), provenance["source_bundle_sha256"]
            )
            verify_checkout(PROJECT_ROOT, members)

        runner = run_creation if args.command == "create" else run_evaluation
        if args.scripted:
            result = runner(
                spec,
                ScriptedBatchBackend(),
                runs_root=args.runs_root,
                provenance=provenance,
                resume=args.resume,
                pre_publish_check=pre_publish_check,
            )
        else:
            from r2sp_tau_knowledge.batch_runtime import BatchRuntime

            with BatchRuntime(
                phase="creation" if args.command == "create" else "evaluation", model=spec.model
            ) as runtime:
                provenance["runtime"] = runtime.metadata
                result = runner(
                    spec,
                    runtime.backend,
                    runs_root=args.runs_root,
                    provenance=provenance,
                    resume=args.resume,
                    pre_publish_check=pre_publish_check,
                )
        _print(
            {
                "root": str(result.root),
                "status": result.status,
                "complete_sha256": result.complete_sha256,
                "scope": "benign-only",
                "execution_mode": provenance["execution_mode"],
            }
        )
        return 0 if result.status == "COMPLETE" else 1
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(
            json.dumps({"status": "INVALID", "reason": str(exc)}, sort_keys=True), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
