#!/usr/bin/env python3
"""Seal and optionally submit one benign model qualification job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from getpass import getuser
from pathlib import Path

from batch_source import canonical_bytes
from build_source_bundle import build
from submit_batch import _write_once

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> int:
    runtime_root = Path("/usr/xtmp") / getuser() / "skill-creation"
    experiment = PROJECT_ROOT / "experiments/tau-knowledge/preliminary"
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler-input", type=Path)
    parser.add_argument("--retrieval-queries", type=Path)
    parser.add_argument("--bundle-dir", type=Path, default=runtime_root / "source-bundles")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    try:
        from r2sp_tau_knowledge.batch import load_spec
        from r2sp_tau_knowledge.batch_runtime import validate_batch_assets
        from r2sp_tau_knowledge.batch_services import (
            DENSE_MODEL_ROOT,
            PINNED_PYTHON,
            SIF_PATH,
            UPSTREAM_ROOT,
        )
        from r2sp_tau_knowledge.benign_probe import verified_documents

        spec = load_spec(args.spec, "creation")
        if args.output.exists():
            raise ValueError("qualification output already exists; use a new directory")
        compiler_input = None
        if args.compiler_input:
            task, pages = verified_documents(args.compiler_input)
            compiler_input = {"task": task, "documents_actually_read": pages}
        queries = None
        if args.retrieval_queries:
            queries = json.loads(args.retrieval_queries.read_bytes())
            if (
                not isinstance(queries, list)
                or not 1 <= len(queries) <= 2
                or any(not isinstance(query, str) or not query.strip() for query in queries)
            ):
                raise ValueError("retrieval probe requires one or two query strings")
        environment = {
            "R2SP_TAU_RUNTIME_ROOT": str(runtime_root),
            "R2SP_TAU_MODEL_ROOT": os.environ.get(
                "R2SP_TAU_MODEL_ROOT",
                str(runtime_root / "models" / spec.model["id"].split("/")[-1]),
            ),
            "R2SP_TAU_DENSE_MODEL_ROOT": str(DENSE_MODEL_ROOT),
            "R2SP_TAU_UPSTREAM_ROOT": str(UPSTREAM_ROOT),
            "R2SP_TAU_PYTHON": str(PINNED_PYTHON),
            "R2SP_TAU_SIF_PATH": str(SIF_PATH),
        }
        assets = None
        if args.submit:
            assets = validate_batch_assets(phase="creation", model=spec.model)
            environment.update(
                {
                    "R2SP_TAU_SIF_SHA256": assets["sif"]["sha256"],
                    "R2SP_TAU_MODEL_SNAPSHOT_SHA256": assets["model"]["snapshot_sha256"],
                    "R2SP_TAU_DENSE_SNAPSHOT_SHA256": assets["dense_model"]["snapshot_sha256"],
                }
            )
        bundle = build(root=PROJECT_ROOT, output_dir=args.bundle_dir.resolve(), write=args.submit)
        request = {
            "schema_version": "r2sp.benign-qualification-job.v1",
            "spec": spec.to_dict(),
            "compiler_input": compiler_input,
            "retrieval_queries": queries,
            "compiler_input_origin_sha256": (
                hashlib.sha256(args.compiler_input.read_bytes()).hexdigest()
                if args.compiler_input
                else None
            ),
            "output": str(args.output.absolute()),
            "runtime_environment": environment,
            "source": bundle,
        }
        raw = canonical_bytes(request)
        digest = hashlib.sha256(raw).hexdigest()
        path = args.bundle_dir.resolve() / f"qualification-request-{digest}.json"
        logs = runtime_root / "logs"
        command = [
            "sbatch",
            "--parsable",
            "--export=NONE",
            f"--output={logs}/%x-%j.out",
            f"--error={logs}/%x-%j.err",
        ]
        if spec.model["id"] == "Qwen/Qwen3.8-27B-FP8":
            command += ["--gres=gpu:a5000:2", "--mem=128G", "--cpus-per-task=16"]
        command += [str(experiment / "slurm/tau_qualification.sbatch"), str(path), digest]
        report = {
            "status": "DRY_RUN",
            "diagnostic_only": True,
            "request_path": str(path),
            "request_sha256": digest,
            "command": shlex.join(command),
            "output": request["output"],
            "assets": assets,
        }
        if args.submit:
            _write_once(path, raw)
            logs.mkdir(parents=True, exist_ok=True)
            job_id = subprocess.check_output(command, text=True).strip().split(";", 1)[0]
            if not job_id.isdecimal():
                raise ValueError("sbatch returned an invalid job ID")
            report.update(status="SUBMITTED", job_id=job_id)
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "INVALID", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
