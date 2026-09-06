"""One fresh, stateless compiler process for a verified benign selection."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any

from r2sp_common import RunStatus

from .batch_outcomes import AcquisitionOutcome
from .batch_runtime import BatchBackend, validate_batch_model
from .data import verify_tracked_snapshot


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"mode", "model", "task_id", "item", "acquisition"}:
        raise ValueError("compiler request fields do not match the benign contract")
    if request["mode"] != "batch-benign-compile":
        raise ValueError("unsupported compiler worker mode")
    item = request["item"]
    if (
        not isinstance(item, dict)
        or set(item) != {"skill_id", "acquisition_task_id", "corpus", "seed"}
        or item["corpus"] != "benign"
        or item["acquisition_task_id"] != request["task_id"]
        or isinstance(item["seed"], bool)
        or not isinstance(item["seed"], int)
        or item["seed"] < 0
    ):
        raise ValueError("invalid benign compiler item")
    acquisition = request["acquisition"]
    if not isinstance(acquisition, dict) or set(acquisition) != {
        "first_user_utterance",
        "opened_pages",
        "selection_complete",
        "public_trace",
    }:
        raise ValueError("invalid compiler acquisition input")
    verify_tracked_snapshot()
    backend = BatchBackend(phase="creation", model=validate_batch_model(request["model"]))
    outcome = backend._compile_in_process(
        item=item,
        acquisition=AcquisitionOutcome(
            status=RunStatus.SUCCESS,
            task_success=False,
            first_user_utterance=acquisition["first_user_utterance"],
            opened_pages=tuple(acquisition["opened_pages"]),
            selection_complete=acquisition["selection_complete"],
            public_trace=acquisition["public_trace"],
        ),
    )
    return {
        "status": outcome.status.value,
        "skill_text": outcome.skill_text,
        "skill_sha256": outcome.skill_sha256,
        "valid": outcome.valid,
        "compiler_input": outcome.compiler_input,
        "error": outcome.error,
        "worker_pid": os.getpid(),
        "execution_id": uuid.uuid4().hex,
        "model_response": dict(backend.client.last_response_metadata),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_request(json.loads(args.request.read_bytes()))
    except Exception as exc:
        result = {"status": "INVALID", "error": f"{type(exc).__name__}: {exc}"}
    with args.response.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return 2 if result["status"] == "INVALID" else 0


if __name__ == "__main__":
    raise SystemExit(main())
