"""Sanitized subprocess boundary for one official acquisition or deployment cell."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from r2sp_common import Page, RunStatus

from .constants import (
    ACQUISITION_TASK_ID,
    EXPERIMENT_ROOT,
    FAR_NEGATIVE_TASK_ID,
    MODEL_SEED,
    POSITIVE_TASK_ID,
)
from .data import load_documents


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


def _pages(directory: Path) -> tuple[Page, ...]:
    resolved = directory.resolve(strict=True)
    materialized_root = (EXPERIMENT_ROOT / "data" / "materialized").resolve(strict=True)
    if not resolved.is_relative_to(materialized_root) or resolved.name != "documents":
        raise ValueError("acquisition corpus is outside the materialized experiment root")
    return tuple(
        Page(
            page_id=document.page_id,
            title=document.title,
            body=document.body,
            content_sha256=document.content_sha256,
        )
        for document in load_documents(resolved)
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
    from .official_runtime import (
        build_acquisition_runtime,
        build_deployment_runtime,
        run_official,
    )

    mode = value.get("mode")
    common = {"mode", "seed", "simulation_id"}
    seed = value.get("seed", MODEL_SEED)
    simulation_id = value.get("simulation_id")
    if mode == "acquisition":
        if set(value) - (common | {"corpus_directory"}):
            raise ValueError("acquisition request contains forbidden fields")
        bundle = build_acquisition_runtime(
            _pages(Path(value["corpus_directory"])),
            task_id=ACQUISITION_TASK_ID,
            seed=seed,
            simulation_id=simulation_id,
        )
    elif mode == "deployment":
        if set(value) - (common | {"task_id", "profile", "skill_text", "skill_sha256"}):
            raise ValueError("deployment request contains forbidden fields")
        task_id = value.get("task_id")
        if task_id not in {POSITIVE_TASK_ID, FAR_NEGATIVE_TASK_ID}:
            raise ValueError("deployment task is not pre-registered")
        skill_text = value.get("skill_text")
        skill_hash = value.get("skill_sha256")
        if not isinstance(skill_text, str) or not isinstance(skill_hash, str):
            raise ValueError("deployment skill binding is invalid")
        if hashlib.sha256(skill_text.encode()).hexdigest() != skill_hash:
            raise ValueError("deployment skill hash mismatch")
        bundle = build_deployment_runtime(
            task_id,
            skill_text,
            value.get("profile"),
            seed=seed,
            simulation_id=simulation_id,
        )
    else:
        raise ValueError("worker mode must be acquisition or deployment")

    with bundle:
        result = run_official(bundle)
        opened_pages = [page.to_open_dict() for page in bundle.opened_pages]
        search_events = [event.to_dict() for event in bundle.search_events]
        exposed_tools = list(bundle.exposed_tool_names)
        runtime_identity = bundle.runtime_identity.to_dict()
        task_tool_calls = bundle.environment.task_tool_calls
        sidecar_events = [dict(event) for event in result.evaluation.sidecar_events]
        official = _simulation_record(result.evaluation.filtered_simulation)
        return {
            "schema_version": 1,
            "status": RunStatus.SUCCESS.value,
            "mode": mode,
            "task_id": bundle.task.id,
            "task_success": result.task_success,
            "official_reward": result.reward,
            "first_user_utterance": result.first_user_utterance,
            "opened_pages": opened_pages,
            "search_events": search_events,
            "public_trace": result.public_trace.to_dict(),
            "official_trajectory": official,
            "excluded_tool_calls": [
                item.to_dict() for item in result.evaluation.excluded_tool_calls
            ],
            "canary_hit": result.evaluation.sidecar_hit,
            "canary_events": sidecar_events,
            "sidecar_trajectory": sidecar_events,
            "runtime_identity": runtime_identity,
            "exposed_tool_names": exposed_tools,
            "task_tool_calls": task_tool_calls,
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
