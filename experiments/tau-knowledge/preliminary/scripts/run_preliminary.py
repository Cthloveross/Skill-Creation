#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from r2sp_tau_knowledge.constants import EXPERIMENT_ROOT  # noqa: E402
from r2sp_tau_knowledge.gpu_gate import GpuGateError, GpuGateLock, check_gpu_gate  # noqa: E402
from r2sp_tau_knowledge.matrix import PreliminaryMatrixRunner  # noqa: E402
from r2sp_tau_knowledge.scripted import ScriptedMatrixBackend  # noqa: E402


def _record_deferred(result: dict[str, object]) -> Path:
    root = EXPERIMENT_ROOT / "data" / "deferred"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = root / f"gpu-gate-{stamp}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _gpu_pair(value: str) -> tuple[int, int]:
    try:
        indices = tuple(int(item) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--gpus must be two comma-separated indices") from exc
    if len(indices) != 2 or len(set(indices)) != 2 or any(index < 0 for index in indices):
        raise argparse.ArgumentTypeError("--gpus must be two distinct non-negative indices")
    return indices


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the tau-Knowledge preliminary matrix")
    parser.add_argument("--mode", choices=("scripted", "preflight", "live"), default="scripted")
    parser.add_argument("--runs-root", type=Path, default=EXPERIMENT_ROOT / "runs")
    parser.add_argument("--gpus", type=_gpu_pair, default=(0, 6))
    args = parser.parse_args()
    if args.mode == "scripted":
        backend = ScriptedMatrixBackend()
        run = PreliminaryMatrixRunner(backend, runs_root=args.runs_root).run()
        print(run)
        return 0

    try:
        result = check_gpu_gate(indices=args.gpus)
    except GpuGateError as exc:
        result_dict = {"status": "INVALID", "reason": str(exc)}
        print(json.dumps(result_dict, sort_keys=True))
        return 2
    if not result.passed:
        result_dict = {"status": "DEFERRED", **result.to_dict()}
        evidence = _record_deferred(result_dict)
        print(json.dumps({**result_dict, "evidence": str(evidence)}, sort_keys=True))
        return 3
    if args.mode == "preflight":
        print(json.dumps({"status": "SUCCESS", **result.to_dict()}, sort_keys=True))
        return 0

    gpu_label = "-".join(str(index) for index in args.gpus)
    with GpuGateLock(
        EXPERIMENT_ROOT / "data" / f"gpu-{gpu_label}.lock",
        indices=args.gpus,
    ):
        final_check = check_gpu_gate(indices=args.gpus, checks=1, interval_seconds=0)
        if not final_check.passed:
            result_dict = {"status": "DEFERRED", **final_check.to_dict()}
            evidence = _record_deferred(result_dict)
            print(json.dumps({**result_dict, "evidence": str(evidence)}, sort_keys=True))
            return 3
        from r2sp_tau_knowledge.live import run_live_matrix

        run = run_live_matrix(runs_root=args.runs_root, gpu_indices=args.gpus)
        print(run)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
