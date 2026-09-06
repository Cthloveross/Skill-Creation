"""Fresh-process boundary for benign acquisition and ordinary banking utility."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from r2sp_common import RunStatus


def _request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("worker request must be an object")
    return value


def _write_response(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        )


def _simulation_record(simulation: Any) -> dict[str, Any]:
    return {
        "id": simulation.id,
        "task_id": simulation.task_id,
        "start_time": simulation.start_time,
        "end_time": simulation.end_time,
        "duration": simulation.duration,
        "termination_reason": simulation.termination_reason.value,
        "messages": [message.model_dump(mode="json") for message in simulation.messages or []],
        "seed": simulation.seed,
        "mode": simulation.mode,
    }


def run_request(value: dict[str, Any]) -> dict[str, Any]:
    from .batch_runtime import validate_batch_model

    if not isinstance(value, dict):
        raise ValueError("worker request must be an object")
    mode = value.get("mode")
    if mode not in {"batch-benign-acquisition", "batch-utility-deployment"}:
        raise ValueError("worker mode must be benign acquisition or utility deployment")
    acquisition = mode == "batch-benign-acquisition"
    fields = {"mode", "seed", "simulation_id", "task_id", "model"}
    fields |= {"corpus"} if acquisition else {"skill_text", "skill_sha256"}
    if set(value) != fields:
        raise ValueError("batch worker request fields do not match its contract")
    model = validate_batch_model(value["model"])
    seed = value["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("batch seed must be a non-negative integer")
    simulation_id = value["simulation_id"]
    if not isinstance(simulation_id, str) or not simulation_id.strip():
        raise ValueError("batch simulation ID must be a non-empty string")
    if acquisition and value["corpus"] != "benign":
        raise ValueError("batch acquisition accepts only the official benign corpus")
    if not acquisition:
        skill = value["skill_text"]
        if (
            not isinstance(skill, str)
            or not skill.strip()
            or hashlib.sha256(skill.encode()).hexdigest() != value["skill_sha256"]
        ):
            raise ValueError("batch deployment Skill hash mismatch")

    # Validate requests before importing the pinned official runtime or data.
    from .batch_official_runtime import build_benign_batch_runtime, run_official

    started = time.monotonic()
    bundle = build_benign_batch_runtime(
        mode="acquisition" if acquisition else "deployment",
        task_id=value["task_id"],
        model=model["id"],
        endpoint=model["endpoint"],
        seed=seed,
        simulation_id=simulation_id,
        skill_text=None if acquisition else value["skill_text"],
    )
    with bundle:
        result = run_official(bundle)
        return {
            "schema_version": 1,
            "status": RunStatus.SUCCESS.value,
            "mode": mode,
            "task_id": bundle.task.id,
            "task_success": result.task_success,
            "official_reward": result.reward,
            "first_user_utterance": result.first_user_utterance,
            "opened_pages": [page.to_open_dict() for page in bundle.opened_pages],
            "selection_complete": bundle.selection_complete,
            "search_events": [event.to_dict() for event in bundle.search_events],
            "public_trace": result.public_trace.to_dict(),
            "official_trajectory": _simulation_record(result.evaluation.filtered_simulation),
            "excluded_tool_calls": [
                item.to_dict() for item in result.evaluation.excluded_tool_calls
            ],
            "runtime_identity": bundle.runtime_identity.to_dict(),
            "exposed_tool_names": list(bundle.exposed_tool_names),
            "task_tool_calls": bundle.environment.task_tool_calls,
            "duration_seconds": time.monotonic() - started,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        response = run_request(_request(args.request))
    except Exception as exc:
        response = {
            "schema_version": 1,
            "status": RunStatus.INVALID.value,
            "error": f"{type(exc).__name__}: {exc}",
        }
    _write_response(args.response, response)
    return 0 if response["status"] != RunStatus.INVALID.value else 2


if __name__ == "__main__":
    raise SystemExit(main())
