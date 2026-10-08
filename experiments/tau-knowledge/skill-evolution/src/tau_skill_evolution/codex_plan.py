"""ChatGPT-plan Codex turns; tools remain owned by the experiment controller.

One application turn is observable. Underlying HTTP dispatches are not. No CLI
credential is read, copied, or passed into a task container by this module.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import queue
import subprocess
import threading
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .artifacts import atomic_json
from .core._canonical import canonical_json_sha256
from .journal import Journal, UnknownOperation
from .model import InputTokenBudgetExceeded, ModelClientError

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {name: {"type": "string"} for name in ("id", "name", "arguments")},
                "required": ["id", "name", "arguments"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["content", "tool_calls"],
    "additionalProperties": False,
}
INSTRUCTIONS = (
    "You are a text-only model transport for an experiment controller. Follow the supplied "
    "conversation as the agent operating in its separate task container. Tools, paths, cwd, "
    "and permissions in that conversation refer to that external task container. The local "
    "read-only sandbox and empty environments constrain only your native host capabilities; "
    "they permit returning external tool requests that write task deliverables or the "
    "candidate Skill when the supplied task permissions allow it. Determine external tool "
    "permissions from the supplied conversation, independently of the local host sandbox. "
    "Return exactly the output schema. content is the original assistant "
    "reply, not a summary; requested JSON/XML must be preserved inside that string. "
    "For a permitted tool request return its name, unique id, and JSON arguments string. "
    "For custom tools arguments is the exact raw tool input. Never execute tools yourself. "
    "If no action is requested return tool_calls=[]. Only use supplied tool definitions. "
    "Use namespace.tool as the name for namespaced tools. If content_response_format is "
    "provided, content must contain JSON conforming to its schema."
)


def _inputs(delta: Any, tools: Any, response_format: Any) -> list[dict[str, Any]]:
    images = []

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get("type") == "input_image":
            url = value.get("image_url")
            if not isinstance(url, str) or not url.startswith("data:image/"):
                raise ModelClientError("codex_plan_image_unsupported", "inline task image required")
            images.append(
                {
                    "type": "image",
                    "url": url,
                    **({"detail": value["detail"]} if "detail" in value else {}),
                }
            )
            return {"type": "image_input_reference", "index": len(images) - 1}
        if value.get("type") in {"input_audio", "audio", "localImage"}:
            raise ModelClientError("codex_plan_input_unsupported", "unsupported model input")
        return {key: visit(item) for key, item in value.items()}

    text = json.dumps(
        {
            "messages": visit(delta),
            "tools": tools or [],
            "content_response_format": response_format,
        },
        ensure_ascii=False,
    )
    return [{"type": "text", "text": text}, *images]


class CodexPlanClient:
    def __init__(
        self,
        *,
        model: str = "gpt-6.1-sol",
        role: str,
        journal_dir: str | Path,
        binary: str = "codex",
        reasoning_effort: str = "high",
        timeout_seconds: float = 300,
        usage_path: str | Path | None = None,
        usage_role: str | None = None,
        request_deadline: float | None = None,
        config: Any = None,
        response_format: Any = None,
        max_input_tokens: int | None = None,
        token_counter: Any = None,
        context_window: int | None = None,
        context_fraction: float | None = None,
        output_reserve: int = 0,
    ) -> None:
        if (
            (context_window is None) != (context_fraction is None)
            or (context_window is not None and context_window <= 0)
            or (context_fraction is not None and not 0 < context_fraction <= 1)
            or output_reserve < 0
        ):
            raise ValueError("invalid existing context policy")
        self.context_window = context_window
        self.context_fraction = context_fraction
        self.output_reserve = output_reserve
        self.config = config or SimpleNamespace(
            model=model,
            transport="codex-plan",
            reasoning_effort=reasoning_effort,
            response_format=response_format,
            max_input_tokens=max_input_tokens,
            max_output_tokens=None,
        )
        self.model, self.role, self.binary = self.config.model, role, binary
        self.reasoning_effort, self.timeout_seconds = self.config.reasoning_effort, timeout_seconds
        self._token_counter = token_counter
        self.request_deadline = request_deadline
        self.usage_path = Path(usage_path) if usage_path else None
        self.usage_role = usage_role or role
        self.journal = Journal(
            journal_dir,
            identity={
                "transport": "codex-plan",
                "model": self.model,
                "role": role,
                "effort": self.reasoning_effort,
                "response_format": self.config.response_format,
                "max_input_tokens": self.config.max_input_tokens,
                "context_window": context_window,
                "context_fraction": context_fraction,
                "output_reserve": output_reserve,
            },
        )
        self.work = self.journal.root / "empty-workspace"
        self.work.mkdir(exist_ok=True)
        self.state_path = self.journal.root / "conversation.json"
        self.blocked_path = self.journal.root / "blocked.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self._process: Any = None
        self._queue: queue.Queue[Any] = queue.Queue()
        self._rpc_id = 0
        self._events: list[Any] = []
        self._stream: Any = None
        self._stream_hash: Any = None
        self._stream_state: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.usage_history: list[dict[str, Any]] = []

    def _start(self) -> None:
        if self._process is not None:
            return
        overrides = {
            "model_provider": "openai",
            "web_search": "disabled",
            "mcp_servers": {},
            "features.shell_tool": False,
            "features.unified_exec": False,
            "features.apply_patch_freeform": False,
            "features.apps": False,
            "features.plugins": False,
            "features.multi_agent": False,
            "features.multi_agent_v2": False,
            "features.code_mode_host": False,
            "features.view_image": False,
            "features.browser_use": False,
            "features.browser_use_external": False,
            "features.in_app_browser": False,
            "features.computer_use": False,
            "features.skip_host_skill_discovery": True,
            "features.skill_search": False,
            "features.hooks": False,
            "features.image_generation": False,
            "features.in_app_local_automation": False,
            "features.remote_plugin": False,
            "features.recommended_plugins": False,
            "features.unbounded_connection_retries": False,
            "features.enable_request_compression": False,
        }
        if self.context_window is not None:
            # Public pinned config: keep automatic compaction beyond the existing
            # admission boundary; a received compaction still stops this trial.
            overrides["model_auto_compact_token_limit"] = self.context_window
            overrides["model_auto_compact_token_limit_scope"] = "total"
        command = [self.binary, "app-server", "--listen", "stdio://"]
        for key, value in overrides.items():
            command.extend(["-c", f"{key}={json.dumps(value)}"])
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in {
                "PATH",
                "HOME",
                "CODEX_HOME",
                "TMPDIR",
                "LANG",
                "LC_ALL",
                "SSL_CERT_FILE",
            }
        }
        self._process = subprocess.Popen(
            command,
            cwd=self.work,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        def read() -> None:
            for line in self._process.stdout:
                self._queue.put(line)
            self._queue.put(None)

        threading.Thread(target=read, daemon=True).start()
        self._rpc(
            "initialize",
            {
                "clientInfo": {"name": "skillsbench_plan", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self._write({"method": "initialized", "params": {}})

    def _write(self, value: Any) -> None:
        self._process.stdin.write(json.dumps(value) + "\n")
        self._process.stdin.flush()

    def _read(self, deadline: float) -> Any:
        remaining = deadline - time.monotonic()
        if self.request_deadline is not None:
            remaining = min(remaining, self.request_deadline - time.time())
        try:
            line = self._queue.get(timeout=max(0, remaining))
        except queue.Empty as error:
            raise TimeoutError("codex_plan_turn_timeout") from error
        if line is None:
            raise EOFError("codex_plan_app_server_closed")
        if self._stream is not None:
            encoded = line.encode()
            self._stream.write(encoded)
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream_hash.update(encoded)
        value = json.loads(line)
        self._events.append(value)
        item = value.get("params", {}).get("item", {})
        if item.get("type") == "contextCompaction":
            raise ModelClientError(
                "codex_plan_context_compaction", "provider compacted the preserved conversation"
            )
        if item.get("type") in {
            "commandExecution",
            "fileChange",
            "mcpToolCall",
            "dynamicToolCall",
            "collabAgentToolCall",
            "subAgentActivity",
            "webSearch",
            "imageView",
            "imageGeneration",
            "sleep",
            "enteredReviewMode",
            "exitedReviewMode",
            "functionCallOutput",
            "hookPrompt",
        }:
            raise ModelClientError("codex_plan_native_tool", "unexpected native capability event")
        if "method" in value and "id" in value:
            self._write(
                {
                    "id": value["id"],
                    "error": {
                        "code": -32601,
                        "message": "Native tools are disabled for this model transport",
                    },
                }
            )
            raise ModelClientError("codex_plan_native_tool", "unexpected native tool request")
        return value

    def _rpc(self, method: str, params: Any) -> Any:
        self._rpc_id += 1
        identifier = self._rpc_id
        self._write({"id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            value = self._read(deadline)
            if value.get("id") == identifier:
                if "error" in value:
                    raise ModelClientError("codex_plan_rpc_error", f"{method} rejected")
                return value["result"]

    def metadata(self) -> dict[str, Any]:
        """No inference; return no account identifiers or credential material."""
        with self._lock:
            self._start()
            models = self._rpc("model/list", {"limit": 100, "includeHidden": True})
            account = self._rpc("account/read", {"refreshToken": False})
            limits = self._rpc("account/rateLimits/read", {})
            return {
                "models": [item["model"] for item in models.get("data", [])],
                "authentication": (account.get("account") or {}).get("type"),
                "used_percent": ((limits.get("rateLimits") or {}).get("primary") or {}).get(
                    "usedPercent"
                ),
            }

    def _turn(self, request: dict[str, Any]) -> tuple[int, bytes]:
        directory = self._evidence_directory(request)
        stream_path = directory / "events.jsonl"
        self._stream = os.fdopen(
            os.open(stream_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        )
        self._stream_hash = hashlib.sha256()
        self._stream_state = {
            "input_hash": canonical_json_sha256(request),
            "operation_key": request.get("operation_key"),
            "thread_id": self.state.get("thread_id"),
            "turn_id": None,
            "status": "UNKNOWN",
        }
        atomic_json(directory / "state.json", self._stream_state)
        try:
            result = self._execute_turn(request)
            self._stream_state["status"] = "RECEIVED"
            return result
        except BaseException as error:
            self._stream_state["error_code"] = getattr(error, "code", type(error).__name__)
            atomic_json(
                self.blocked_path,
                {"reason": "UNKNOWN", "input_hash": canonical_json_sha256(request)},
            )
            raise
        finally:
            self._stream.close()
            self._stream = None
            self._stream_state["sha256"] = self._stream_hash.hexdigest()
            atomic_json(directory / "state.json", self._stream_state)

    def _evidence_directory(self, request: dict[str, Any]) -> Path:
        path = (
            self.journal.root
            / "turn-events"
            / (request.get("operation_key") or canonical_json_sha256(request))
        )
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def context_budget(self) -> dict[str, Any]:
        """Last real provider context, distinct from cumulative billable usage."""
        return {
            "context_window": self.state.get("context_budget", {}).get("context_window"),
            "input_tokens": self.state.get("context_budget", {}).get("input_tokens", 0),
            "output_tokens": self.state.get("context_budget", {}).get("output_tokens", 0),
            "reserve_tokens": self.output_reserve,
        }

    def projected_context(self, messages: Any, tools: Any = None) -> dict[str, Any]:
        def count(values: Any) -> int:
            if self._token_counter is None:
                raise ValueError("context admission requires a token counter")
            return self._token_counter.count(values, tools=tools, chat_template_kwargs=None)

        budget = self.context_budget()
        previous = self.state.get("messages", [])
        continuing = (
            bool(self.state.get("thread_id"))
            and len(messages) > len(previous)
            and messages[: len(previous)] == previous
        )
        delta = messages[len(previous) :] if continuing else messages
        visible = count(messages)
        current = budget["input_tokens"] + budget["output_tokens"] if continuing else 0
        incremental = count(delta) if delta and current else 0
        windows = [n for n in (self.context_window, budget["context_window"]) if n is not None]
        window = min(windows) if windows else None
        limit = self.config.max_input_tokens
        if window is not None and self.context_fraction is not None:
            policy_limit = math.floor(window * self.context_fraction) - self.output_reserve
            limit = min(limit, policy_limit) if limit is not None else policy_limit
        return {
            "visible_input_tokens": visible,
            "provider_context_tokens": current,
            "delta_input_tokens": incremental,
            "observed_input_tokens": max(visible, current + incremental),
            "context_window": window,
            "reserve_tokens": self.output_reserve,
            "max_input_tokens": limit,
        }

    def _ready(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.blocked_path.exists():
            raise UnknownOperation("codex_plan_previous_turn_stopped")
        if self.request_deadline is not None and self.request_deadline <= time.time():
            raise ModelClientError(
                "learning_timeout", "Codex plan deadline exhausted before dispatch"
            )
        if self.config.max_input_tokens is not None or self.context_fraction is not None:
            admission = self.projected_context(request["messages"], request.get("tools"))
            atomic_json(self._evidence_directory(request) / "admission.json", admission)
            if admission["observed_input_tokens"] > admission["max_input_tokens"]:
                error = InputTokenBudgetExceeded(
                    admission["observed_input_tokens"], admission["max_input_tokens"]
                )
                error.details.update(admission)
                raise error
        self._start()
        messages = request["messages"]
        previous = self.state.get("messages", [])
        continuing = (
            bool(self.state.get("thread_id"))
            and len(messages) > len(previous)
            and messages[: len(previous)] == previous
        )
        if continuing:
            thread = self._rpc("thread/resume", {"threadId": self.state["thread_id"]})
        else:
            observed_window = self.context_budget()["context_window"]
            thread = self._rpc(
                "thread/start",
                {
                    "model": self.model,
                    "modelProvider": "openai",
                    "cwd": str(self.work),
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "environments": [],
                    "baseInstructions": INSTRUCTIONS,
                    "developerInstructions": "",
                    "dynamicTools": [],
                    "selectedCapabilityRoots": [],
                    "runtimeWorkspaceRoots": [],
                    "allowProviderModelFallback": False,
                },
            )
            self.state = {
                "thread_id": thread["thread"]["id"],
                "messages": [],
                "context_budget": {
                    "context_window": observed_window,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reserve_tokens": self.output_reserve,
                },
            }
            atomic_json(self.state_path, self.state)
        if thread.get("model") != self.model or thread.get("modelProvider") != "openai":
            raise ModelClientError("codex_plan_model_changed", "app-server model/provider mismatch")
        if thread.get("instructionSources") or thread.get("runtimeWorkspaceRoots"):
            raise ModelClientError(
                "codex_plan_host_context", "unexpected host instruction/workspace"
            )
        return request

    def _execute_turn(self, request: dict[str, Any]) -> tuple[int, bytes]:
        messages = request["messages"]
        previous = self.state.get("messages", [])
        self._events = []
        self._stream_state["thread_id"] = self.state["thread_id"]
        turn = self._rpc(
            "turn/start",
            {
                "threadId": self.state["thread_id"],
                "environments": [],
                "runtimeWorkspaceRoots": [],
                "effort": self.reasoning_effort,
                "outputSchema": OUTPUT_SCHEMA,
                "input": _inputs(
                    messages[len(previous) :], request.get("tools"), request.get("response_format")
                ),
            },
        )
        turn_id = turn["turn"]["id"]
        self._stream_state["turn_id"] = turn_id
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            event = self._read(deadline)
            params = event.get("params", {})
            if (
                event.get("method") == "turn/completed"
                and params.get("threadId") == self.state["thread_id"]
                and params.get("turn", {}).get("id") == turn_id
            ):
                return 200, json.dumps(
                    {
                        "thread_id": self.state["thread_id"],
                        "turn_id": turn_id,
                        "events": self._events,
                        "request": request,
                        "prior_usage": self.state.get("total_usage", {}),
                    }
                ).encode()

    def _normalize(self, _status: int, body: bytes) -> dict[str, Any]:
        raw = json.loads(body)
        final = ""
        usage = None
        total_usage = None
        context_window = None
        completed = False
        for event in raw["events"]:
            params = event.get("params", {})
            if params.get("threadId") != raw["thread_id"]:
                continue
            if event.get("method") == "turn/completed":
                if params.get("turn", {}).get("id") != raw["turn_id"]:
                    continue
                completed = True
            elif params.get("turnId") != raw["turn_id"]:
                continue
            if event.get("method") == "thread/tokenUsage/updated":
                usage = params["tokenUsage"]["last"]
                total_usage = params["tokenUsage"].get("total")
                context_window = params["tokenUsage"].get("modelContextWindow")
            if event.get("method") == "item/completed":
                item = params.get("item", {})
                if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                    final = item.get("text", "")
            if event.get("method") == "turn/completed" and params["turn"]["status"] != "completed":
                info = (params["turn"].get("error") or {}).get("codexErrorInfo")
                atomic_json(self.blocked_path, {"reason": "turn_failed", "turn_id": raw["turn_id"]})
                if info == "unauthorized":
                    raise ModelClientError(
                        "authentication_failed", "Codex login rejected", status=401
                    )
                if info in ("usageLimitExceeded", "rateLimitExceeded", "sessionBudgetExceeded"):
                    raise ModelClientError(
                        "codex_plan_quota_unavailable", "Codex plan unavailable", status=403
                    )
                status = (
                    next(
                        (
                            v.get("httpStatusCode")
                            for v in info.values()
                            if isinstance(v, dict) and v.get("httpStatusCode")
                        ),
                        None,
                    )
                    if isinstance(info, dict)
                    else None
                )
                raise ModelClientError(
                    "codex_plan_turn_failed", "Codex turn did not complete", status=status
                )
        if not completed:
            raise ModelClientError(
                "codex_plan_response_invalid", "matching turn completion missing"
            )
        try:
            value = json.loads(final)
        except (json.JSONDecodeError, TypeError) as error:
            raise ModelClientError(
                "codex_plan_response_invalid", "invalid structured Codex output"
            ) from error
        if (
            usage is None
            or not isinstance(value, dict)
            or set(value) != {"content", "tool_calls"}
            or not isinstance(value.get("content"), str)
            or not isinstance(value.get("tool_calls"), list)
        ):
            raise ModelClientError(
                "codex_plan_response_invalid", "Codex turn output or usage is missing"
            )
        required_usage = (
            "inputTokens",
            "outputTokens",
            "cachedInputTokens",
            "reasoningOutputTokens",
            "totalTokens",
        )

        def valid_usage(value: Any) -> bool:
            return isinstance(value, dict) and all(
                type(value.get(k)) is int and value[k] >= 0 for k in required_usage
            )

        if not valid_usage(usage) or (
            context_window is not None
            and (
                isinstance(context_window, bool)
                or not isinstance(context_window, int)
                or context_window <= 0
            )
        ):
            raise ModelClientError("codex_plan_response_invalid", "invalid Codex context usage")
        windows = [
            n for n in (context_window, self.context_budget()["context_window"]) if n is not None
        ]
        context_budget = {
            "context_window": min(windows) if windows else None,
            "input_tokens": usage["inputTokens"],
            "output_tokens": usage["outputTokens"],
            "reserve_tokens": self.output_reserve,
        }
        provider_last_usage = dict(usage)
        if total_usage is not None:
            prior = raw.get("prior_usage", {})
            if (
                not valid_usage(total_usage)
                or not isinstance(prior, dict)
                or not valid_usage({k: prior.get(k, 0) for k in required_usage})
            ):
                raise ModelClientError(
                    "codex_plan_response_invalid", "invalid cumulative Codex usage"
                )
            usage = {k: total_usage[k] - prior.get(k, 0) for k in required_usage}
        if not valid_usage(usage):
            raise ModelClientError("codex_plan_response_invalid", "invalid Codex usage")
        if any(
            not isinstance(c, dict)
            or set(c) != {"id", "name", "arguments"}
            or not all(isinstance(c[k], str) for k in c)
            or not c["id"]
            or not c["name"]
            for c in value["tool_calls"]
        ):
            raise ModelClientError("codex_plan_response_invalid", "invalid Codex tool request")
        if len({c["id"] for c in value["tool_calls"]}) != len(value["tool_calls"]):
            raise ModelClientError("codex_plan_response_invalid", "duplicate Codex tool id")
        calls = [
            {
                "id": c["id"],
                "type": "function",
                "function": {"name": c["name"], "arguments": c["arguments"]},
            }
            for c in value["tool_calls"]
        ]
        counted = {
            "input_tokens": usage["inputTokens"],
            "output_tokens": usage["outputTokens"],
            "total_tokens": usage["totalTokens"],
            "prompt_tokens": usage["inputTokens"],
            "completion_tokens": usage["outputTokens"],
            "input_tokens_details": {"cached_tokens": usage["cachedInputTokens"]},
            "output_tokens_details": {"reasoning_tokens": usage["reasoningOutputTokens"]},
        }
        response = {
            "role": "assistant",
            "content": value["content"],
            "tool_calls": calls,
            "finish_reason": "tool_calls" if calls else "stop",
            "usage": counted,
            "response_id": raw["turn_id"],
            "context_budget": context_budget,
        }
        self.state = {
            "thread_id": raw["thread_id"],
            "messages": raw["request"]["messages"],
            "total_usage": total_usage or {},
            "provider_last_usage": provider_last_usage,
            "context_budget": context_budget,
        }
        atomic_json(self.state_path, self.state)
        self.usage_history.append(counted)
        if self.usage_path:
            self.usage_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.usage_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(
                    fd,
                    (
                        json.dumps(
                            {
                                "role": self.usage_role,
                                "model": self.model,
                                "response_id": raw["turn_id"],
                                "operation_key": raw["request"].get("operation_key"),
                                "usage": counted,
                                "context_budget": context_budget,
                            }
                        )
                        + "\n"
                    ).encode(),
                )
                os.fsync(fd)
            finally:
                os.close(fd)
        return response

    def complete(
        self, messages: Any, *, tools: Any = None, seed: Any = None, max_output_tokens: Any = None
    ) -> dict[str, Any]:
        del seed
        request = self._prepare(messages, tools, max_output_tokens)
        operation_id = "turn/" + canonical_json_sha256(request)
        operation_key = canonical_json_sha256(
            {"journal": str(self.journal.root.resolve()), "operation_id": operation_id}
        )
        with self._lock:
            return self.journal.dispatch_raw(
                operation_id,
                request,
                lambda: self._ready({**request, "operation_key": operation_key}),
                self._turn,
                self._normalize,
            )

    def _prepare(self, messages: Any, tools: Any, max_output_tokens: Any) -> dict[str, Any]:
        if max_output_tokens is not None:
            raise ValueError("Codex plan transport does not impose output token quotas")
        return {
            "messages": deepcopy(list(messages)),
            "tools": deepcopy(tools),
            "response_format": self.config.response_format,
        }

    def complete_journaled(
        self, journal: Any, operation_id: str, payload: Any, messages: Any, **kwargs: Any
    ) -> dict[str, Any]:
        binding = {
            "inputs": payload,
            "messages": list(messages),
            **kwargs,
            "delivery_policy": "single_codex_turn",
            "http_dispatches": "NOT_OBSERVABLE",
        }
        operation_key = canonical_json_sha256(
            {"journal": str(journal.root.resolve()), "operation_id": operation_id}
        )
        with self._lock:
            return journal.dispatch_raw(
                operation_id,
                binding,
                lambda: self._ready(
                    {
                        **self._prepare(
                            messages, kwargs.get("tools"), kwargs.get("max_output_tokens")
                        ),
                        "operation_key": operation_key,
                    }
                ),
                self._turn,
                self._normalize,
            )

    def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
            self._process = None
            self._queue = queue.Queue()


class CodexPlanOpener:
    """Translate native Responses relay requests without executing any tools."""

    def __init__(self, client: CodexPlanClient) -> None:
        self.client = client

    def __call__(self, request: Any, *, timeout: float) -> Any:
        payload = json.loads(request.data)

        original_timeout = self.client.timeout_seconds
        self.client.timeout_seconds = min(timeout, original_timeout)
        try:
            messages = [{"role": "developer", "content": payload.get("instructions", "")}]
            messages.extend(payload["input"])
            result = self.client.complete(messages, tools=payload.get("tools"))
        finally:
            self.client.timeout_seconds = original_timeout
        output = []
        if result["content"]:
            output.append(
                {
                    "id": "msg_" + result["response_id"],
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": result["content"], "annotations": []}
                    ],
                }
            )
        definitions = {}
        for tool in payload.get("tools", []):
            if tool.get("type") == "namespace":
                for nested in tool.get("tools", []):
                    definitions[tool["name"] + "." + nested["name"]] = (nested, tool["name"])
            else:
                definitions[tool.get("name")] = (tool, None)
        # Pinned Codex 0.160.1 also declares these freeform tools in its developer
        # prompt rather than the Responses tools field. Preserve their wire type.
        if not definitions:
            for name in ("exec", "wait", "apply_patch"):
                definitions["functions." + name] = ({"type": "custom", "name": name}, "functions")
        for call in result["tool_calls"]:
            function = call["function"]
            definition, namespace = definitions.get(function["name"], ({}, None))
            if not definition and function["name"].startswith("functions."):
                namespace, name = function["name"].split(".", 1)
                definition = {"type": "function", "name": name}
            custom = definition.get("type") == "custom"
            output.append(
                {
                    "id": "item_" + call["id"],
                    "call_id": call["id"],
                    "type": "custom_tool_call" if custom else "function_call",
                    "name": definition.get("name", function["name"]),
                    "status": "completed",
                    "input" if custom else "arguments": function["arguments"],
                    **({"namespace": namespace} if namespace else {}),
                }
            )
        response = io.BytesIO(
            json.dumps(
                {
                    "id": "resp_" + result["response_id"],
                    "object": "response",
                    "status": "completed",
                    "model": self.client.model,
                    "output": output,
                    "usage": result["usage"],
                }
            ).encode()
        )
        response.status = 200
        return response
