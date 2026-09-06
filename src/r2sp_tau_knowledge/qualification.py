"""Fail-closed qualification for the formal Flash-Next service."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from .batch_compiler import validate_skill_text
from .batch_constants import (
    COMPILER_MAX_OUTPUT_TOKENS,
    COMPILER_MAX_SKILL_TOKENS,
    MODEL_ID,
    MODEL_MAX_CONTEXT_TOKENS,
    MODEL_REVISION,
    MODEL_SEED,
    SELECTION_K,
)
from .batch_model import GenerationConfig, ModelClient, OpenAICompatibleClient


class QualificationError(RuntimeError):
    """The service cannot be used for a formal experiment."""


def _arguments(call: Mapping[str, Any]) -> dict[str, Any]:
    function = call.get("function")
    if not isinstance(function, Mapping):
        raise QualificationError("tool call has no function")
    value = function.get("arguments")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise QualificationError("tool arguments are not valid JSON") from exc
    if not isinstance(value, dict):
        raise QualificationError("tool arguments are not an object")
    return value


def _one_call(message: Mapping[str, Any], name: str) -> tuple[dict[str, Any], Mapping[str, Any]]:
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], Mapping):
        raise QualificationError(f"{name} probe did not return exactly one tool call")
    call = calls[0]
    function = call.get("function")
    if not isinstance(function, Mapping) or function.get("name") != name:
        raise QualificationError(f"{name} probe returned the wrong tool")
    return _arguments(call), call


def _visible_assistant(message: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") if isinstance(message.get("content"), str) else None,
    }
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        result["tool_calls"] = calls
    return result


def _tool_schema(name: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Qualification-only tool with no external side effect.",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def visible_gpu_attestation() -> dict[str, Any]:
    """Require exactly four visible RTX Pro 6000 devices inside the allocation."""

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,uuid,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise QualificationError("nvidia-smi hardware qualification failed") from exc
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(rows) != 4:
        raise QualificationError(
            f"formal service requires exactly four visible GPUs; got {len(rows)}"
        )
    records = []
    for line in rows:
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 5 or "RTX PRO 6000" not in fields[1].upper():
            raise QualificationError("visible GPU is not an RTX Pro 6000")
        records.append(
            {
                "index": int(fields[0]),
                "name": fields[1],
                "uuid": fields[2],
                "driver_version": fields[3],
                "memory_total_mib": int(fields[4]),
            }
        )
    return {"gpu_count": len(records), "gpus": records}


def _model_catalog(
    endpoint: str,
    *,
    model_id: str = MODEL_ID,
    max_context_tokens: int = MODEL_MAX_CONTEXT_TOKENS,
) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/models",
        headers={"Authorization": "Bearer tau-local-evaluation"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            catalog = json.loads(response.read())
    except Exception as exc:
        raise QualificationError("/v1/models qualification failed") from exc
    records = catalog.get("data") if isinstance(catalog, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise QualificationError("model catalog must expose exactly one model")
    record = records[0]
    if record.get("id") != model_id or record.get("max_model_len") != max_context_tokens:
        raise QualificationError("model catalog does not match the frozen contract")
    return {"id": record["id"], "max_model_len": record["max_model_len"]}


def qualify_model_service(
    endpoint: str,
    *,
    client_factory: Callable[[GenerationConfig], ModelClient] | None = None,
    include_long_context: bool = True,
    model_id: str = MODEL_ID,
    model_revision: str = MODEL_REVISION,
    max_context_tokens: int = MODEL_MAX_CONTEXT_TOKENS,
    include_creation: bool = True,
) -> dict[str, Any]:
    """Exercise every response shape used by Phase A before its first formal call."""

    if client_factory is None:
        client_factory = lambda config: OpenAICompatibleClient(  # noqa: E731
            endpoint, config=config, timeout_seconds=900
        )
        catalog = _model_catalog(endpoint, model_id=model_id, max_context_tokens=max_context_tokens)
    else:
        catalog = {"id": model_id, "max_model_len": max_context_tokens}

    nonthinking = client_factory(
        GenerationConfig(
            model=model_id,
            revision=model_revision,
            temperature=0.0,
            top_p=1.0,
            enable_thinking=False,
            preserve_thinking=False,
            reasoning_effort=None,
            max_output_tokens=256,
        )
    )
    thinking = client_factory(
        GenerationConfig(
            model=model_id,
            revision=model_revision,
            enable_thinking=True,
            preserve_thinking=False,
            reasoning_effort="xhigh",
            max_output_tokens=2048,
        )
    )

    ordinary = nonthinking.complete(
        [{"role": "user", "content": "Reply with exactly SERVICE_OK."}], seed=MODEL_SEED
    )
    if "SERVICE_OK" not in str(ordinary.get("content", "")):
        raise QualificationError("ordinary completion probe failed")

    finish_tool = _tool_schema(
        "qualification_finish",
        {"status": {"type": "string", "enum": ["probe-ok"]}},
        ["status"],
    )
    first = thinking.complete(
        [
            {
                "role": "user",
                "content": (
                    "Think carefully about the required status, then call "
                    "qualification_finish exactly once with status probe-ok."
                ),
            }
        ],
        tools=[finish_tool],
        seed=MODEL_SEED,
    )
    finish_args, finish_call = _one_call(first, "qualification_finish")
    if finish_args != {"status": "probe-ok"}:
        raise QualificationError("thinking tool probe returned wrong arguments")
    reasoning = first.get("reasoning_content")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise QualificationError("reasoning parser returned no private reasoning content")
    if any(tag in str(first.get("content", "")).casefold() for tag in ("<think>", "</think>")):
        raise QualificationError("reasoning markup leaked into visible content")

    call_id = finish_call.get("id")
    if not isinstance(call_id, str) or not call_id:
        raise QualificationError("tool parser omitted the tool call id")
    loop = thinking.complete(
        [
            {"role": "user", "content": "Call the qualification tool, then acknowledge it."},
            _visible_assistant(first),
            {"role": "tool", "tool_call_id": call_id, "content": '{"accepted":true}'},
        ],
        tools=[finish_tool],
        seed=MODEL_SEED,
        max_output_tokens=1024,
    )
    if not (isinstance(loop.get("content"), str) and loop["content"].strip()) and not loop.get(
        "tool_calls"
    ):
        raise QualificationError("multi-turn tool loop probe failed")

    if include_creation:
        candidates = [f"candidate-{index:02d}" for index in range(20)]
        select_tool = _tool_schema(
            "select_docs",
            {
                "page_ids": {
                    "type": "array",
                    "items": {"type": "string", "enum": candidates},
                    "minItems": SELECTION_K,
                    "maxItems": SELECTION_K,
                    "uniqueItems": True,
                }
            },
            ["page_ids"],
        )
        selected = thinking.complete(
            [
                {
                    "role": "user",
                    "content": (
                        "Select exactly ten distinct IDs and call select_docs once. Candidates: "
                        + ", ".join(candidates)
                    ),
                }
            ],
            tools=[select_tool],
            seed=MODEL_SEED,
        )
        selected_args, _ = _one_call(selected, "select_docs")
        page_ids = selected_args.get("page_ids")
        if (
            not isinstance(page_ids, list)
            or len(page_ids) != SELECTION_K
            or len(set(page_ids)) != SELECTION_K
            or any(item not in candidates for item in page_ids)
        ):
            raise QualificationError("exact-ten selection probe failed")

        compiler = client_factory(
            GenerationConfig(
                model=model_id,
                revision=model_revision,
                enable_thinking=True,
                preserve_thinking=False,
                reasoning_effort="xhigh",
                max_output_tokens=COMPILER_MAX_OUTPUT_TOKENS,
            )
        )
        compiled = compiler.complete(
            [
                {
                    "role": "system",
                    "content": "Return only a valid compact SKILL.md with YAML frontmatter.",
                },
                {
                    "role": "user",
                    "content": (
                        "Create a workflow skill. Required name: qualification-probe. "
                        "Include one Markdown workflow step."
                    ),
                },
            ],
            seed=MODEL_SEED,
            max_output_tokens=COMPILER_MAX_OUTPUT_TOKENS,
        )
        skill = compiled.get("content")
        if not isinstance(skill, str):
            raise QualificationError("compiler probe returned no text")
        skill = skill.strip() + "\n"
        if validate_skill_text(skill) is not None:
            raise QualificationError("compiler probe returned an invalid SKILL.md")
        counter = getattr(compiler, "count_tokens", None)
        skill_tokens = int(counter(skill)) if callable(counter) else (len(skill) + 3) // 4
        if skill_tokens > COMPILER_MAX_SKILL_TOKENS:
            raise QualificationError("compiler probe exceeded the final Skill cap")

    long_context_tokens = None
    if include_long_context:
        counter = getattr(nonthinking, "count_tokens", None)
        if not callable(counter):
            raise QualificationError("long-context probe requires the tokenizer endpoint")
        body = " context-probe" * 56_000
        long_context_tokens = int(counter(body))
        if not 50_000 <= long_context_tokens <= 60_000:
            target_words = max(1, int(56_000 * 56_000 / max(long_context_tokens, 1)))
            body = " context-probe" * target_words
            long_context_tokens = int(counter(body))
        if not 50_000 <= long_context_tokens <= 60_000:
            raise QualificationError("unable to construct the 56K long-context probe")
        long_reply = nonthinking.complete(
            [
                {"role": "system", "content": "Read the context and reply LONG_CONTEXT_OK."},
                {"role": "user", "content": body + "\nReply LONG_CONTEXT_OK."},
            ],
            seed=MODEL_SEED,
            max_output_tokens=32,
        )
        if "LONG_CONTEXT_OK" not in str(long_reply.get("content", "")):
            raise QualificationError("long-context generation probe failed")

    return {
        "schema_version": "r2sp.tau-model-qualification.v1",
        "status": "SUCCESS",
        "catalog": catalog,
        "ordinary_completion": True,
        "thinking_parser": True,
        "xml_tool_call": True,
        "tool_loop": True,
        "exact_ten_selection": include_creation,
        "compiler_skill": include_creation,
        "long_context_tokens": long_context_tokens,
    }


__all__ = [
    "QualificationError",
    "qualify_model_service",
    "visible_gpu_attestation",
]
