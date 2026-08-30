"""Deterministic in-process runtime used by tests and the CPU-only MVP."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .base import (
    FinishResult,
    RuntimeAdapter,
    RuntimeIdentity,
    RuntimeObservation,
    RuntimeStateError,
    normalize_args,
    normalize_exception,
    normalize_result,
    validate_identifier,
)

Handler = Callable[[Mapping[str, Any]], Any]
Evaluator = Callable[[str, str, Sequence[RuntimeObservation]], Any]


class SyntheticRuntime(RuntimeAdapter):
    """A small API dispatcher with explicit lifecycle and evaluator hooks."""

    def __init__(
        self,
        handlers: Mapping[tuple[str, str], Handler] | None = None,
        *,
        canary_handler: Handler | None = None,
        evaluator: Evaluator | None = None,
        default_task_success: bool = True,
        default_score: float = 1.0,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._handlers: dict[tuple[str, str], Handler] = dict(handlers or {})
        self._canary_handler = canary_handler
        self._evaluator = evaluator
        self._default_task_success = bool(default_task_success)
        self._default_score = float(default_score)
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._identity: RuntimeIdentity | None = None
        self._started = False
        self._finished = False
        self._trace: list[RuntimeObservation] = []

    @property
    def identity(self) -> RuntimeIdentity | None:
        return self._identity

    @property
    def trace(self) -> tuple[RuntimeObservation, ...]:
        return tuple(self._trace)

    def start(self) -> RuntimeIdentity:
        if self._started:
            raise RuntimeStateError("runtime is already started")
        self._identity = RuntimeIdentity(
            world_id="synthetic-world-" + self._id_factory(),
            context_id="synthetic-context-" + self._id_factory(),
            session_id="synthetic-session-" + self._id_factory(),
        )
        self._started = True
        self._finished = False
        self._trace = []
        return self._identity

    def execute(self, app: str, api: str, args: Mapping[str, Any]) -> RuntimeObservation:
        self._require_active()
        try:
            app = validate_identifier(app, "app")
            api = validate_identifier(api, "api")
            normalized_args = normalize_args(args)
        except (TypeError, ValueError) as exc:
            code, message = normalize_exception(exc, reveal_message=True)
            observation = RuntimeObservation(
                app=str(app),
                api=str(api),
                args={},
                ok=False,
                error_code=code,
                error_message=message,
            )
            self._trace.append(observation)
            return observation

        if app.casefold() == "canary":
            handler = None
            if api.casefold() == "emit":
                # An explicit constructor hook is preferred; the keyed handler
                # keeps the generic synthetic dispatcher backward-compatible.
                handler = self._canary_handler or self._handlers.get((app, api))
            unavailable_code = "canary_unavailable"
        else:
            handler = self._handlers.get((app, api))
            unavailable_code = "not_found"
        if handler is None:
            observation = RuntimeObservation(
                app=app,
                api=api,
                args=normalized_args,
                ok=False,
                error_code=unavailable_code,
                error_message=(
                    "canary.emit is unavailable in this phase"
                    if unavailable_code == "canary_unavailable"
                    else "requested API was not found"
                ),
            )
        else:
            try:
                result = handler(normalized_args)
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=True,
                    result=normalize_result(result),
                )
            except Exception as exc:
                code, message = normalize_exception(exc, reveal_message=False)
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=False,
                    error_code=code,
                    error_message=message,
                )
        self._trace.append(observation)
        return observation

    def finish(self, status: str, answer: str) -> FinishResult:
        self._require_active()
        if not isinstance(status, str) or not isinstance(answer, str):
            raise TypeError("status and answer must be strings")
        status = status.strip()[:64]
        answer = answer[:8192]
        if not status:
            raise ValueError("status must not be empty")

        self._finished = True
        if self._evaluator is None:
            return FinishResult(
                status=status,
                answer=answer,
                task_success=self._default_task_success,
                score=self._default_score,
            )
        try:
            value = self._evaluator(status, answer, tuple(self._trace))
            return _coerce_finish_result(value, status=status, answer=answer)
        except Exception as exc:
            code, _ = normalize_exception(exc)
            return FinishResult(
                status=status,
                answer=answer,
                task_success=False,
                score=0.0,
                failure="evaluation_" + code,
            )

    def close(self) -> None:
        self._started = False

    def _require_active(self) -> None:
        if not self._started:
            raise RuntimeStateError("runtime has not been started")
        if self._finished:
            raise RuntimeStateError("runtime is already finished")


def _coerce_finish_result(value: Any, *, status: str, answer: str) -> FinishResult:
    if isinstance(value, FinishResult):
        return value
    if isinstance(value, bool):
        return FinishResult(
            status=status,
            answer=answer,
            task_success=value,
            score=1.0 if value else 0.0,
        )
    if isinstance(value, Mapping):
        success = bool(value.get("task_success", value.get("success", False)))
        score_value = value.get("score")
        score = float(score_value) if score_value is not None else (1.0 if success else 0.0)
        failure_value = value.get("failure")
        return FinishResult(
            status=status,
            answer=answer,
            task_success=success,
            score=score,
            failure=str(failure_value) if failure_value else None,
        )
    if isinstance(value, tuple) and len(value) == 2:
        return FinishResult(
            status=status,
            answer=answer,
            task_success=bool(value[0]),
            score=float(value[1]),
        )
    raise TypeError("synthetic evaluator returned an unsupported value")


__all__ = ["SyntheticRuntime"]
