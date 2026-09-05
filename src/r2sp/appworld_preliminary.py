"""AppWorld adapter for the shared preliminary acquisition protocol.

The historical qualification runner remains replayable. New preliminary work
uses this module's body-only ``search_web``/``open_page`` boundary and exact
compiler allowlist. No tau runtime is imported here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from r2sp_common import (
    DeterministicBM25,
    Page,
    PublicTrace,
    SessionWebRetriever,
    fingerprint_code_roots,
)

from .appworld_payloads import load_appworld_injection_payloads
from .compiler import SkillArtifact, validate_skill_text
from .file_injection_fixture import (
    load_appworld_file_fixtures,
    materialize_appworld_file_bundles,
)
from .hashing import canonical_json_sha256, sha256_text
from .model_client import ModelClient, ModelClientError
from .resource_pool import ResourcePool

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "appworld" / "preliminary"
DEFAULT_AGENT_PROMPT = EXPERIMENT_ROOT / "prompts" / "preliminary_agent_system.md"
DEFAULT_COMPILER_PROMPT = EXPERIMENT_ROOT / "prompts" / "preliminary_compiler_system.md"

ACQUISITION_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the fixed AppWorld resource pool by document body.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_page",
            "description": "Open one page exposed by search_web and read its full body.",
            "parameters": {
                "type": "object",
                "properties": {"page_id": {"type": "string"}},
                "required": ["page_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": "Call one AppWorld API through the task runtime.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string"},
                    "api": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["app", "api", "args"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the task with its actual status and answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["success", "fail"]},
                    "answer": {"type": "string"},
                },
                "required": ["status", "answer"],
                "additionalProperties": False,
            },
        },
    },
)


def pages_from_pool(pool: ResourcePool) -> tuple[Page, ...]:
    """Adapt AppWorld resources without making title/app/API terms searchable."""

    if not isinstance(pool, ResourcePool):
        raise TypeError("pool must be a ResourcePool")
    return tuple(
        Page(
            page_id=resource.resource_id,
            title=resource.title,
            body=resource.body,
            content_sha256=resource.content_hash,
        )
        for resource in pool
    )


def build_web_session(pool: ResourcePool) -> SessionWebRetriever:
    return SessionWebRetriever(
        DeterministicBM25(pages_from_pool(pool), k1=1.2, b=0.75),
        internal_k=10,
        visible_k=5,
        max_searches=12,
        max_unique_opens=5,
    )


@dataclass(frozen=True)
class AppWorldAcquisitionResult:
    first_user_utterance: str
    task_success: bool
    opened_pages: tuple[dict[str, str], ...]
    search_evidence: tuple[dict[str, Any], ...]
    public_trace: dict[str, Any]
    turns: int
    task_tool_calls: int
    failure: str | None = None


def _tool_call(value: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ValueError("tool call must be an object")
    function = value.get("function") if isinstance(value.get("function"), Mapping) else value
    name = function.get("name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(name, str) or not isinstance(arguments, Mapping):
        raise ValueError("tool call name/arguments are invalid")
    return str(value.get("id") or "call"), name, dict(arguments)


class AppWorldAcquisitionRunner:
    """Four-tool AppWorld loop; there is no selection phase or read quota of five."""

    def __init__(
        self,
        client: ModelClient,
        *,
        max_turns: int = 60,
        max_task_tool_calls: int = 800,
        system_prompt_path: Path = DEFAULT_AGENT_PROMPT,
    ) -> None:
        self.client = client
        self.max_turns = max_turns
        self.max_task_tool_calls = max_task_tool_calls
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")

    def run(
        self,
        *,
        question: str,
        retriever: SessionWebRetriever,
        runtime: Any,
        seed: int | None = None,
    ) -> AppWorldAcquisitionResult:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be non-empty")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        trace = PublicTrace().append("user", "message", {"content": question})
        task_success = False
        failure: str | None = None
        task_tool_calls = 0
        turns = 0
        try:
            if getattr(runtime, "identity", None) is None:
                runtime.start()
            for turns in range(1, self.max_turns + 1):
                try:
                    response = self.client.complete(
                        messages,
                        tools=ACQUISITION_TOOLS,
                        seed=None if seed is None else seed + turns - 1,
                    )
                except ModelClientError as exc:
                    failure = f"model_{exc.code}"
                    break
                content = response.get("content")
                calls = response.get("tool_calls")
                assistant: dict[str, Any] = {
                    "role": "assistant",
                    "content": content if isinstance(content, str) else None,
                }
                if isinstance(calls, list):
                    assistant["tool_calls"] = calls
                messages.append(assistant)
                trace = trace.append(
                    "assistant",
                    "message",
                    {"content": assistant["content"], "tool_calls": calls or []},
                )
                if not isinstance(calls, list) or len(calls) != 1:
                    messages.append({"role": "user", "content": "Call exactly one available tool."})
                    continue
                task_tool_calls += 1
                if task_tool_calls > self.max_task_tool_calls:
                    failure = "task_tool_budget_exceeded"
                    break
                call_id = f"turn-{turns}"
                name = "invalid"
                try:
                    call_id, name, arguments = _tool_call(calls[0])
                    if name == "search_web":
                        output = retriever.search_web(arguments.get("query"))
                    elif name == "open_page":
                        output = retriever.open_page(arguments.get("page_id"))
                    elif name == "execute":
                        output = runtime.execute(
                            arguments.get("app"), arguments.get("api"), arguments.get("args")
                        ).as_trace()
                    elif name == "finish":
                        finished = runtime.finish(arguments.get("status"), arguments.get("answer"))
                        task_success = finished.task_success
                        failure = finished.failure
                        output = {"accepted": True}
                    else:
                        output = {"error": "unknown_tool"}
                except Exception as exc:
                    output = {"error": type(exc).__name__}
                trace = trace.append("tool", "result", {"name": name, "output": output})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(output, ensure_ascii=False, sort_keys=True),
                    }
                )
                if name == "finish" and output == {"accepted": True}:
                    break
            else:
                failure = "max_turns_exceeded"
            opened = tuple(page.to_open_dict() for page in retriever.opened_pages)
            search = tuple(event.to_dict() for event in retriever.search_events)
            return AppWorldAcquisitionResult(
                first_user_utterance=question,
                task_success=task_success,
                opened_pages=opened,
                search_evidence=search,
                public_trace=trace.to_dict(),
                turns=turns,
                task_tool_calls=task_tool_calls,
                failure=failure,
            )
        finally:
            retriever.close()
            runtime.close()


class AppWorldPreliminaryCompiler:
    def __init__(
        self,
        client: ModelClient,
        *,
        include_public_trace: bool = False,
        prompt_path: Path = DEFAULT_COMPILER_PROMPT,
        max_input_tokens: int = 32768,
        max_skill_tokens: int = 4096,
    ) -> None:
        self.client = client
        self.include_public_trace = include_public_trace
        self.system_prompt = prompt_path.read_text(encoding="utf-8")
        self.max_input_tokens = max_input_tokens
        self.max_skill_tokens = max_skill_tokens

    def build_payload(
        self,
        *,
        first_user_utterance: str,
        opened_pages: Sequence[Mapping[str, Any]],
        task_id: str,
        task_success: bool,
        public_trace: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        documents: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in opened_pages:
            page = Page.from_dict(raw)
            if page.page_id not in seen:
                seen.add(page.page_id)
                documents.append(page.to_open_dict())
        payload: dict[str, Any] = {
            "task": first_user_utterance,
            "documents_actually_read": documents,
            "official_result": {"task_id": task_id, "task_success": task_success},
        }
        if self.include_public_trace:
            if not isinstance(public_trace, Mapping):
                raise ValueError("public_trace is required when enabled")
            payload["public_trace"] = json.loads(json.dumps(public_trace, allow_nan=False))
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if len(encoded) > self.max_input_tokens * 4:
            raise ValueError("full compiler input exceeds the fixed budget")
        return payload

    def compile(self, *, seed: int | None = None, **inputs: Any) -> SkillArtifact:
        payload = self.build_payload(**inputs)
        source_ids = tuple(item["page_id"] for item in payload["documents_actually_read"])
        try:
            response = self.client.complete(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                tools=None,
                seed=seed,
                max_output_tokens=self.max_skill_tokens,
            )
        except ModelClientError as exc:
            return SkillArtifact(
                "", hashlib.sha256(b"").hexdigest(), False, source_ids, f"model_{exc.code}"
            )
        text = response.get("content")
        if response.get("tool_calls") or not isinstance(text, str) or not text.strip():
            return SkillArtifact(
                "", hashlib.sha256(b"").hexdigest(), False, source_ids, "invalid_response"
            )
        text = text.strip() + "\n"
        error = validate_skill_text(text)
        if error is not None:
            return SkillArtifact(
                "", hashlib.sha256(b"").hexdigest(), False, source_ids, f"invalid_skill_{error}"
            )
        return SkillArtifact(text, hashlib.sha256(text.encode()).hexdigest(), True, source_ids)


def appworld_code_fingerprint() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return fingerprint_code_roots(
        {
            "appworld": root / "src" / "r2sp",
            "common": root / "src" / "r2sp_common",
            "appworld_scripts": EXPERIMENT_ROOT / "scripts",
        },
        include_suffixes=(".py", ".sh"),
    ).to_dict()


def materialize_content_addressed(
    *, appworld_root: Path, payload_directory: Path, output_root: Path
) -> dict[str, Any]:
    """Materialize both profiles below an exact payload-set hash directory."""

    payloads = load_appworld_injection_payloads(payload_directory)
    payload_hashes = {name: sha256_text(value) for name, value in payloads.items()}
    payload_set_sha256 = canonical_json_sha256(payload_hashes)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / f"payload-set-{payload_set_sha256}"
    identity = {
        "schema_version": 1,
        "payload_set_sha256": payload_set_sha256,
        "payload_sha256": payload_hashes,
    }
    if destination.exists():
        observed = json.loads((destination / "payload-set.json").read_bytes())
        if observed != identity:
            raise ValueError("existing AppWorld payload-set identity mismatch")
        load_appworld_file_fixtures(appworld_root, destination)
    else:
        staging = output_root / f".payload-set-{uuid.uuid4().hex}"
        try:
            materialize_appworld_file_bundles(
                appworld_root,
                staging,
                payload_directory=payload_directory,
            )
            (staging / "payload-set.json").write_text(
                json.dumps(identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            try:
                os.rename(staging, destination)
            except FileExistsError:
                shutil.rmtree(staging)
            load_appworld_file_fixtures(appworld_root, destination)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    manifests = {
        profile: {
            arm: str(destination / profile / arm / "manifest.json") for arm in ("benign", "poison")
        }
        for profile in sorted(payloads)
    }
    return {**identity, "output_directory": str(destination), "manifests": manifests}


def run_offline_regression(*, appworld_root: Path, bundle_directory: Path, output: Path) -> Path:
    """Exercise the new retrieval boundary over all four materialized corpora."""

    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    records: list[dict[str, Any]] = []
    for profile_name in sorted(loaded.fixtures):
        fixture = loaded.fixtures[profile_name]
        assert fixture.acquisition_pools is not None
        for arm in ("benign", "poison"):
            session = build_web_session(fixture.acquisition_pools[arm])
            visible = session.search_web(fixture.query)
            records.append(
                {
                    "profile": profile_name,
                    "arm": arm,
                    "agent_visible": visible,
                    "evaluator_search": session.search_events[0].to_dict(),
                    "body_only": True,
                    "select_docs_exposed": False,
                }
            )
            session.close()
    report = {
        "schema_version": 1,
        "mode": "appworld_preliminary_offline_regression",
        "code_fingerprint": appworld_code_fingerprint(),
        "records": records,
    }
    output.mkdir(parents=True)
    path = output / "report.json"
    payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AppWorld preliminary offline protocol regression")
    parser.add_argument("--appworld-root", type=Path, required=True)
    parser.add_argument("--bundle-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(
        run_offline_regression(
            appworld_root=args.appworld_root,
            bundle_directory=args.bundle_directory,
            output=args.output,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
