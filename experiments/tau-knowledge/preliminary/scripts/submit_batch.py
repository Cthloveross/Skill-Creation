#!/usr/bin/env python3
"""Prepare a sealed request for a benign batch; submit only with --submit."""

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

from batch_source import canonical_bytes, sha256_file
from build_source_bundle import build

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    runtime_root = Path("/usr/xtmp") / getuser() / "skill-creation"
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("phase", choices=("create", "evaluate"))
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--bundle-dir", type=Path, default=runtime_root / "source-bundles")
    parser.add_argument(
        "--tau-upstream-root", type=Path, default=EXPERIMENT_ROOT / "data/upstream/tau2-bench"
    )
    parser.add_argument(
        "--model-root", type=Path, help="pinned model snapshot; default follows the spec"
    )
    parser.add_argument(
        "--dense-model-root", type=Path, default=runtime_root / "models/Qwen3-Embedding-0.6B"
    )
    parser.add_argument(
        "--sif-path", type=Path, default=runtime_root / "images/vllm-qwen38-flash-next-amd64.sif"
    )
    parser.add_argument("--sif-sha256")
    parser.add_argument("--submit", action="store_true")
    return parser


def _write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o444)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError(
                "sealed submission request already exists with different content"
            ) from None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from r2sp_tau_knowledge.batch import load_spec, replay_batch

        phase = "creation" if args.phase == "create" else "evaluation"
        spec = load_spec(args.spec, phase)
        spec_value = spec.to_dict()
        if args.phase == "evaluate":
            for source in spec_value["sources"]:
                report = replay_batch(
                    Path(source["root"]), complete_sha256=source["complete_sha256"]
                )
                if report["phase"] != "creation" or report["execution_mode"] != "live":
                    raise ValueError("Slurm evaluation requires sealed live creation sources")
        runtime_root = Path("/usr/xtmp") / getuser() / "skill-creation"
        runs_root = (args.runs_root or runtime_root / "runs" / f"tau-{phase}-v2").resolve()
        bundle_dir = args.bundle_dir.resolve()
        paths = {
            "R2SP_TAU_UPSTREAM_ROOT": args.tau_upstream_root.resolve(),
            "R2SP_TAU_MODEL_ROOT": (
                args.model_root or runtime_root / "models" / spec.model["id"].split("/")[-1]
            ).resolve(),
            "R2SP_TAU_DENSE_MODEL_ROOT": args.dense_model_root.resolve(),
            "R2SP_TAU_SIF_PATH": args.sif_path.resolve(),
        }
        runtime_environment = {key: str(value) for key, value in paths.items()}
        runtime_environment["R2SP_TAU_RUNTIME_ROOT"] = str(runtime_root)
        runtime_environment["R2SP_TAU_PYTHON"] = str(
            paths["R2SP_TAU_UPSTREAM_ROOT"] / ".venv/bin/python"
        )
        if args.sif_sha256:
            if len(args.sif_sha256) != 64 or any(
                c not in "0123456789abcdef" for c in args.sif_sha256
            ):
                raise ValueError("--sif-sha256 must be lowercase hexadecimal")
            runtime_environment["R2SP_TAU_SIF_SHA256"] = args.sif_sha256
        asset_status = "NOT_CHECKED_DRY_RUN"
        if args.submit:
            tau_python = paths["R2SP_TAU_UPSTREAM_ROOT"] / ".venv/bin/python"
            if not tau_python.is_file() or not os.access(tau_python, os.X_OK):
                raise ValueError("pinned Tau interpreter is missing")
            validator = [
                sys.executable,
                "-c",
                (
                    "import json,sys; "
                    "from r2sp_tau_knowledge.batch_runtime import validate_batch_assets; "
                    "print(json.dumps(validate_batch_assets(phase=sys.argv[1], "
                    "model=json.loads(sys.argv[2])),sort_keys=True))"
                ),
                phase,
                json.dumps(spec.model),
            ]
            validator_environment = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
                "LANG": "C.UTF-8",
                **runtime_environment,
            }
            assets = json.loads(
                subprocess.check_output(validator, text=True, env=validator_environment)
            )
            runtime_environment.update(
                {
                    "R2SP_TAU_SIF_SHA256": assets["sif"]["sha256"],
                    "R2SP_TAU_MODEL_SNAPSHOT_SHA256": assets["model"]["snapshot_sha256"],
                }
            )
            if "dense_model" in assets:
                runtime_environment["R2SP_TAU_DENSE_SNAPSHOT_SHA256"] = assets["dense_model"][
                    "snapshot_sha256"
                ]
            asset_status = "VERIFIED"
        bundle = build(root=PROJECT_ROOT, output_dir=bundle_dir, write=args.submit)
        request = {
            "schema_version": "r2sp.tau-batch-job.v2",
            "scope": "benign-only",
            "phase": args.phase,
            "spec": spec_value,
            "runs_root": str(runs_root),
            "resume": str(args.resume.resolve()) if args.resume else None,
            "source": {
                key: bundle[key]
                for key in ("bundle_path", "bundle_sha256", "manifest_sha256", "source_tree_sha256")
            },
            "runtime_environment": runtime_environment,
        }
        raw = canonical_bytes(request)
        request_sha = hashlib.sha256(raw).hexdigest()
        request_path = bundle_dir / f"batch-request-{request_sha}.json"
        logs_root = runtime_root / "logs"
        command = [
            "sbatch",
            "--parsable",
            "--export=NONE",
            f"--job-name=tau-{phase}-v2",
            f"--output={logs_root}/%x-%j.out",
            f"--error={logs_root}/%x-%j.err",
        ]
        if spec.model["id"] == "Qwen/Qwen3.8-27B-FP8":
            command += ["--gres=gpu:a5000:2", "--mem=128G", "--cpus-per-task=16"]
        command += [str(EXPERIMENT_ROOT / "slurm/tau_batch.sbatch"), str(request_path), request_sha]
        result = {
            "status": "DRY_RUN",
            "phase": phase,
            "scope": "benign-only",
            "batch_id": spec.batch_id,
            "source": request["source"],
            "request_sha256": request_sha,
            "request_path": str(request_path),
            "runtime_assets": asset_status,
            "command": shlex.join(command),
            "expected_runs_root": str(runs_root),
        }
        if args.submit:
            _write_once(request_path, raw)
            if sha256_file(request_path) != request_sha:
                raise ValueError("submission request SHA-256 changed")
            logs_root.mkdir(parents=True, exist_ok=True)
            runs_root.mkdir(parents=True, exist_ok=True)
            submitted = subprocess.check_output(command, text=True).strip()
            job_id = submitted.split(";", 1)[0]
            if not job_id.isdecimal():
                raise ValueError("sbatch returned an invalid job ID")
            result.update(status="SUBMITTED", job_id=job_id)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as exc:
        print(
            json.dumps({"status": "INVALID", "reason": str(exc)}, sort_keys=True), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
