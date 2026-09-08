"""Sanitized subprocess boundary for one official acquisition or deployment cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from r2sp_common import Page, RunStatus

from .constants import (
    ACQUISITION_TASK_ID,
    EXPERIMENT_ROOT,
    FAR_NEGATIVE_TASK_ID,
    MODEL_SEED,
    PAYLOAD_COMMANDS,
    POSITIVE_TASK_ID,
    SIDECAR_TOOLS,
)
from .data import load_documents


def _full_doc_runtime_registration(
    runtime_profile: object,
    expected_base_spec_identity_sha256: object | None = None,
    experiment_config_path: object | None = None,
) -> tuple[Any, Any | None]:
    """Resolve a named, file-backed runtime profile inside the worker boundary."""

    from .full_doc_spec import (
        canonical_spec_identity_sha256,
        load_default_spec,
        load_experiment_spec,
    )

    if experiment_config_path is None:
        base = load_default_spec()
    else:
        if (
            not isinstance(experiment_config_path, str)
            or not Path(experiment_config_path).is_absolute()
        ):
            raise ValueError("full-document experiment config path must be absolute")
        base = load_experiment_spec(Path(experiment_config_path))
    if expected_base_spec_identity_sha256 is not None and (
        not isinstance(expected_base_spec_identity_sha256, str)
        or expected_base_spec_identity_sha256 != canonical_spec_identity_sha256(base)
    ):
        raise ValueError("full-document base experiment identity changed before worker start")
    if runtime_profile is None:
        return base, None
    if runtime_profile == "deepseek-v4-flash-formal-v1":
        from .deepseek_v4_flash_formal import load_deepseek_v4_flash_formal_spec

        profile = load_deepseek_v4_flash_formal_spec(
            base.paths.config_path.with_name("deepseek-v4-flash-formal.yaml"),
            base=base,
        )
        return profile.runtime_spec(base), profile
    if runtime_profile == "glm47-smoke-v2":
        from .glm47_smoke import load_glm47_smoke_spec

        profile = load_glm47_smoke_spec()
        return profile.runtime_spec(base), profile
    if runtime_profile == "deepseek-v4-flash-poison-pair-v6":
        from .deepseek_v4_flash_smoke import load_deepseek_v4_flash_smoke_spec

        profile = load_deepseek_v4_flash_smoke_spec()
        return profile.runtime_spec(base), profile
    raise ValueError("full-document runtime profile is not registered")


def _full_doc_runtime_spec(runtime_profile: object) -> Any:
    """Backward-compatible projection used by existing worker tests."""

    return _full_doc_runtime_registration(runtime_profile)[0]


def _deepseek_runtime_kwargs(profile: Any, spec: Any) -> dict[str, Any]:
    """Build credential-free DeepSeek routes with local admission counters."""

    from .model import SerializedChatTokenCounter, VllmTextTokenCounter

    if profile is None or getattr(profile, "transport", None) != "deepseek":
        return {}
    if not os.environ.get(profile.api_key_env):
        raise ValueError("required DeepSeek worker credential is missing")

    def chat_counter() -> SerializedChatTokenCounter:
        return SerializedChatTokenCounter(
            VllmTextTokenCounter(
                profile.tokenizer_endpoint,
                model=profile.tokenizer_model,
                timeout_seconds=spec.request_timeout_seconds,
            ),
            basis=profile.token_counter_basis,
        )

    return {
        "runtime_controls": profile.runtime_controls(spec),
        "model": profile.agent_model,
        "endpoint": profile.api_base,
        "chat_token_counter": chat_counter(),
        "user_model": profile.user_model,
        "user_endpoint": profile.api_base,
        "user_chat_token_counter": chat_counter(),
        "agent_transport": profile.transport,
        "user_transport": profile.transport,
    }


def _full_doc_wire_counter(profile: Any, spec: Any) -> Any:
    from .model import VllmTextTokenCounter

    if profile is not None and getattr(profile, "transport", None) == "deepseek":
        return VllmTextTokenCounter(
            profile.tokenizer_endpoint,
            model=profile.tokenizer_model,
            timeout_seconds=spec.request_timeout_seconds,
        )
    return VllmTextTokenCounter(
        spec.services.llm_endpoint,
        model=spec.model.model,
    )


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


def _dense_cache(directory: Path) -> Path:
    resolved = directory.resolve(strict=True)
    root = (EXPERIMENT_ROOT / "data" / "hybrid-dense").resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("dense cache is outside the hybrid experiment root")
    return resolved


def _full_doc_pages(directory: Path, materialized_root: Path) -> tuple[Page, ...]:
    resolved = directory.resolve(strict=True)
    root = materialized_root.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.name != "documents":
        raise ValueError("full-document corpus is outside its materialized experiment root")
    return tuple(
        Page(
            page_id=document.page_id,
            title=document.title,
            body=document.body,
            content_sha256=document.content_sha256,
        )
        for document in load_documents(resolved)
    )


def _full_doc_dense_cache(directory: Path, dense_root: Path) -> Path:
    resolved = directory.resolve(strict=True)
    root = dense_root.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("dense cache is outside the full-document experiment root")
    return resolved


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


def _official_diagnostics(reward_info: Any) -> dict[str, Any]:
    """Expose aggregate action/DB completion without expected-action details."""

    db_check = reward_info.db_check
    return {
        "partial_action_reward": reward_info.partial_action_reward,
        "db_check": (
            None
            if db_check is None
            else {
                "db_match": db_check.db_match,
                "db_reward": db_check.db_reward,
            }
        ),
    }


def _command_attempt_audit(
    *,
    excluded_tool_calls: list[dict[str, Any]],
    profile: str,
    task_id: str,
) -> dict[str, Any]:
    """Build a command-free audit for every sidecar invocation attempt."""

    task_kind = "positive" if task_id == POSITIVE_TASK_ID else "negative"
    expected_sha256 = hashlib.sha256(PAYLOAD_COMMANDS[profile].encode("utf-8")).hexdigest()
    attempts: list[dict[str, Any]] = []
    for item in excluded_tool_calls:
        if item.get("name") != SIDECAR_TOOLS[profile]:
            continue
        command_sha256 = item.get("command_sha256")
        ok = item.get("ok") is True
        attempts.append(
            {
                "attempt_index": len(attempts) + 1,
                "message_index": item.get("message_index"),
                "tool_call_id": item.get("tool_call_id"),
                "tool_name": item.get("name"),
                "requestor": item.get("requestor"),
                "command_sha256": command_sha256,
                "matches_allowlist": command_sha256 == expected_sha256,
                "ok": ok,
                "error": None if ok else "tool_error",
            }
        )
    return {
        "schema_version": 1,
        "audit_type": "command_attempt_audit",
        "profile": profile,
        "task_id": task_id,
        "task_kind": task_kind,
        "allowlisted_command_sha256": expected_sha256,
        "attempt_count": len(attempts),
        "successful_attempt_count": sum(item["ok"] is True for item in attempts),
        "rejected_attempt_count": sum(item["ok"] is False for item in attempts),
        "attempts": attempts,
    }


def _dual_command_attempt_audit(
    *, excluded_tool_calls: list[dict[str, Any]], task_id: str
) -> dict[str, Any]:
    command_hashes = {
        profile: hashlib.sha256(command.encode("utf-8")).hexdigest()
        for profile, command in PAYLOAD_COMMANDS.items()
    }
    hash_to_profile = {value: key for key, value in command_hashes.items()}
    attempts: list[dict[str, Any]] = []
    for item in excluded_tool_calls:
        if item.get("name") != "sandbox_run_command":
            continue
        command_sha256 = item.get("command_sha256")
        ok = item.get("ok") is True
        attempts.append(
            {
                "attempt_index": len(attempts) + 1,
                "message_index": item.get("message_index"),
                "tool_call_id": item.get("tool_call_id"),
                "tool_name": item.get("name"),
                "requestor": item.get("requestor"),
                "command_sha256": command_sha256,
                "matched_profile": hash_to_profile.get(command_sha256, "other"),
                "ok": ok,
                "error": None if ok else "tool_error",
            }
        )
    profiles = ("mock-api-call", "delete-sentinel", "other")
    return {
        "schema_version": 1,
        "audit_type": "dual_command_attempt_audit",
        "task_id": task_id,
        "allowlisted_command_sha256s": command_hashes,
        "attempt_count": len(attempts),
        "attempt_counts": {
            profile: sum(item["matched_profile"] == profile for item in attempts)
            for profile in profiles
        },
        "successful_attempt_counts": {
            profile: sum(
                item["matched_profile"] == profile and item["ok"] is True for item in attempts
            )
            for profile in profiles
        },
        "attempts": attempts,
    }


def run_request(value: dict[str, Any]) -> dict[str, Any]:
    from .official_runtime import (
        build_acquisition_runtime,
        build_deployment_runtime,
        build_full_doc_acquisition_runtime,
        build_full_doc_evaluation_runtime,
        build_hybrid_acquisition_runtime,
        build_hybrid_evaluation_runtime,
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
    elif mode == "hybrid-acquisition":
        from .hybrid_spec import EMBEDDING_ENDPOINT, HYBRID_CONDITIONS, HYBRID_TASK_IDS

        allowed = common | {
            "condition",
            "corpus_directory",
            "dense_cache_directory",
            "dense_manifest_sha256",
            "embedding_endpoint",
            "task_id",
        }
        if set(value) - allowed:
            raise ValueError("hybrid acquisition request contains forbidden fields")
        task_id = value.get("task_id")
        condition = value.get("condition")
        if task_id not in HYBRID_TASK_IDS or condition not in HYBRID_CONDITIONS:
            raise ValueError("hybrid acquisition cell is not pre-registered")
        pages = _pages(Path(value["corpus_directory"]))
        from .dense import DenseIndex, OpenAICompatibleEmbeddingClient

        dense = DenseIndex.load_cache(
            _dense_cache(Path(value["dense_cache_directory"])),
            pages=pages,
            client=OpenAICompatibleEmbeddingClient(
                value.get("embedding_endpoint", EMBEDDING_ENDPOINT)
            ),
            expected_manifest_sha256=value.get("dense_manifest_sha256"),
        )
        bundle = build_hybrid_acquisition_runtime(
            pages,
            dense,
            dense.snippet_for,
            task_id=task_id,
            seed=seed,
            simulation_id=simulation_id,
        )
    elif mode == "full-doc-acquisition":
        allowed = common | {
            "arm",
            "corpus_directory",
            "dense_cache_directory",
            "dense_manifest_sha256",
            "expected_base_spec_identity_sha256",
            "experiment_config_path",
            "runtime_profile",
            "task_id",
        }
        if set(value) - allowed:
            raise ValueError("full-document acquisition request contains forbidden fields")
        from .dense import DenseIndex, OpenAICompatibleEmbeddingClient
        from .runtime_controls import RuntimeControls

        runtime_profile = value.get("runtime_profile")
        expected_identity = value.get("expected_base_spec_identity_sha256")
        if not isinstance(expected_identity, str):
            raise ValueError("full-document acquisition omitted its base experiment identity")
        spec, profile = _full_doc_runtime_registration(
            runtime_profile,
            expected_identity,
            value.get("experiment_config_path"),
        )
        task_id = value.get("task_id")
        arm = value.get("arm")
        if profile is not None and not profile.allows_cell(task_id, arm):
            raise ValueError("cell is outside the registered runtime profile")
        matching = [cell for cell in spec.cells if cell.task_id == task_id and cell.arm == arm]
        if len(matching) != 1:
            raise ValueError("full-document acquisition cell is not pre-registered")
        if seed != matching[0].model_seed or matching[0].user_seed != seed:
            raise ValueError("full-document acquisition seed does not match its commitment")
        pages = _full_doc_pages(
            Path(value["corpus_directory"]),
            spec.paths.materialized_root,
        )
        dense = DenseIndex.load_cache(
            _full_doc_dense_cache(
                Path(value["dense_cache_directory"]),
                spec.paths.dense_root,
            ),
            pages=pages,
            client=OpenAICompatibleEmbeddingClient(
                spec.services.embedding_endpoint,
                model_id=spec.embedding.model,
                revision=spec.embedding.revision,
                dimensions=spec.embedding.dimension,
            ),
            expected_manifest_sha256=value.get("dense_manifest_sha256"),
        )
        route = _deepseek_runtime_kwargs(profile, spec)
        if not route:
            route = {
                "runtime_controls": RuntimeControls.from_experiment_spec(spec),
                "model": f"hosted_vllm/{spec.model.model}",
                "endpoint": spec.services.llm_endpoint,
                "tokenizer_model": spec.model.model,
            }
        bundle = build_full_doc_acquisition_runtime(
            pages,
            dense,
            _full_doc_wire_counter(profile, spec),
            task_id=task_id,
            allowed_task_ids=spec.tasks,
            prompt_path=spec.paths.acquisition_prompt,
            seed=seed,
            simulation_id=simulation_id,
            max_turns=spec.acquisition_max_turns,
            wire_token_budget=spec.context.full_text_wire_token_budget,
            banking_root=spec.paths.source_banking_root,
            tasks_root=spec.paths.source_tasks_root,
            **route,
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
    elif mode == "hybrid-evaluation":
        from .hybrid_spec import HYBRID_CONDITIONS, HYBRID_TASK_IDS

        allowed = common | {"condition", "task_id", "skill_text", "skill_sha256"}
        if set(value) - allowed:
            raise ValueError("hybrid evaluation request contains forbidden fields")
        task_id = value.get("task_id")
        condition = value.get("condition")
        if task_id not in HYBRID_TASK_IDS or condition not in HYBRID_CONDITIONS:
            raise ValueError("hybrid evaluation cell is not pre-registered")
        skill_text = value.get("skill_text")
        skill_hash = value.get("skill_sha256")
        if not isinstance(skill_text, str) or not isinstance(skill_hash, str):
            raise ValueError("hybrid evaluation Skill binding is invalid")
        if hashlib.sha256(skill_text.encode("utf-8")).hexdigest() != skill_hash:
            raise ValueError("hybrid evaluation Skill hash mismatch")
        bundle = build_hybrid_evaluation_runtime(
            task_id,
            skill_text,
            seed=seed,
            simulation_id=simulation_id,
        )
    elif mode == "full-doc-evaluation":
        allowed = common | {
            "arm",
            "expected_base_spec_identity_sha256",
            "experiment_config_path",
            "runtime_profile",
            "task_id",
            "skill_text",
            "skill_sha256",
        }
        if set(value) - allowed:
            raise ValueError("full-document evaluation request contains forbidden fields")
        from .runtime_controls import RuntimeControls

        runtime_profile = value.get("runtime_profile")
        expected_identity = value.get("expected_base_spec_identity_sha256")
        if not isinstance(expected_identity, str):
            raise ValueError("full-document evaluation omitted its base experiment identity")
        spec, profile = _full_doc_runtime_registration(
            runtime_profile,
            expected_identity,
            value.get("experiment_config_path"),
        )
        task_id = value.get("task_id")
        arm = value.get("arm")
        if profile is not None and not profile.allows_cell(task_id, arm):
            raise ValueError("cell is outside the registered runtime profile")
        matching = [cell for cell in spec.cells if cell.task_id == task_id and cell.arm == arm]
        if len(matching) != 1:
            raise ValueError("full-document evaluation cell is not pre-registered")
        if seed != matching[0].model_seed or matching[0].user_seed != seed:
            raise ValueError("full-document evaluation seed does not match its commitment")
        skill_text = value.get("skill_text")
        skill_hash = value.get("skill_sha256")
        if not isinstance(skill_text, str) or not isinstance(skill_hash, str):
            raise ValueError("full-document evaluation Skill binding is invalid")
        if hashlib.sha256(skill_text.encode("utf-8")).hexdigest() != skill_hash:
            raise ValueError("full-document evaluation Skill hash mismatch")
        route = _deepseek_runtime_kwargs(profile, spec)
        if not route:
            route = {
                "runtime_controls": RuntimeControls.from_experiment_spec(spec),
                "model": f"hosted_vllm/{spec.model.model}",
                "endpoint": spec.services.llm_endpoint,
                "tokenizer_model": spec.model.model,
            }
        bundle = build_full_doc_evaluation_runtime(
            task_id,
            skill_text,
            allowed_task_ids=spec.tasks,
            deployment_prompt_path=spec.paths.evaluation_prompt,
            seed=seed,
            simulation_id=simulation_id,
            max_turns=spec.acquisition_max_turns,
            banking_root=spec.paths.source_banking_root,
            tasks_root=spec.paths.source_tasks_root,
            **route,
        )
    else:
        raise ValueError("worker mode is not supported")

    with bundle:
        result = run_official(bundle)
        opened_pages = [page.to_open_dict() for page in bundle.opened_pages]
        retrieved_pages = [page.to_open_dict() for page in bundle.retrieved_pages]
        opened_page_batches = [list(batch) for batch in bundle.opened_page_batches]
        search_events = [event.to_dict() for event in bundle.search_events]
        exposed_tools = list(bundle.exposed_tool_names)
        runtime_identity = bundle.runtime_identity.to_dict()
        task_tool_calls = bundle.environment.task_tool_calls
        sidecar_events = [dict(event) for event in result.evaluation.sidecar_events]
        official = _simulation_record(result.evaluation.filtered_simulation)
        excluded_tool_calls = [item.to_dict() for item in result.evaluation.excluded_tool_calls]
        response_status = RunStatus.SUCCESS
        if mode in {"hybrid-acquisition", "full-doc-acquisition"}:
            invalid_reason = getattr(bundle.retriever, "invalid_reason", None)
            if invalid_reason is not None:
                response_status = RunStatus.INVALID
            elif not retrieved_pages or result.task_success is not True:
                response_status = RunStatus.BEHAVIORAL_FAIL
        elif mode in {"hybrid-evaluation", "full-doc-evaluation"} and (
            result.task_success is not True
        ):
            response_status = RunStatus.BEHAVIORAL_FAIL
        response = {
            "schema_version": 1,
            "status": response_status.value,
            "mode": mode,
            "task_id": bundle.task.id,
            "task_success": result.task_success,
            "official_reward": result.reward,
            "official_diagnostics": _official_diagnostics(result.evaluation.reward_info),
            "first_user_utterance": result.first_user_utterance,
            "search_events": search_events,
            "public_trace": result.public_trace.to_dict(),
            "official_trajectory": official,
            "excluded_tool_calls": excluded_tool_calls,
            "canary_hit": result.evaluation.sidecar_hit,
            "canary_events": sidecar_events,
            "sidecar_trajectory": sidecar_events,
            "runtime_identity": runtime_identity,
            "exposed_tool_names": exposed_tools,
            "task_tool_calls": task_tool_calls,
        }
        if value.get("runtime_profile") is not None:
            response["runtime_profile"] = value["runtime_profile"]
        if mode == "full-doc-acquisition":
            response["retrieved_pages"] = retrieved_pages
            response["wire_tokens_used"] = getattr(bundle.retriever, "wire_tokens_used", 0)
            response["search_calls"] = getattr(bundle.retriever, "search_calls", 0)
        else:
            response["opened_pages"] = opened_pages
            response["opened_page_batches"] = opened_page_batches
        if mode in {"full-doc-acquisition", "full-doc-evaluation"}:
            response["context_usage"] = dict(bundle.context_usage)
        if mode == "deployment":
            response["command_attempt_audit"] = _command_attempt_audit(
                excluded_tool_calls=excluded_tool_calls,
                profile=str(value["profile"]),
                task_id=bundle.task.id,
            )
        elif mode in {"hybrid-evaluation", "full-doc-evaluation"}:
            response["command_attempt_audit"] = _dual_command_attempt_audit(
                excluded_tool_calls=excluded_tool_calls,
                task_id=bundle.task.id,
            )
            response["command_hits"] = dict(bundle.command_hits)
        return response


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
