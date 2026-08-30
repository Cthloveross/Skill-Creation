"""Lazy AppWorld adapter implementing the experiment's narrow tool gateway."""

from __future__ import annotations

import importlib
import json
import math
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..hashing import canonical_json_sha256
from .base import (
    FinishResult,
    RuntimeAdapter,
    RuntimeIdentity,
    RuntimeObservation,
    RuntimeStateError,
    normalize_args,
    normalize_exception,
    normalize_result,
    normalize_text,
    validate_identifier,
)

EvaluationExtractor = Callable[[Any], Any]
WorldFactory = Callable[..., Any]
CanaryHandler = Callable[[Mapping[str, Any]], Any]
_ERROR_OUTPUT = re.compile(
    r"(?:^execution failed\b|^traceback\b|"
    r"\b(?:validation|syntax|runtime|attribute|type|value|key)error\b)",
    flags=re.IGNORECASE,
)


class AppWorldRuntime(RuntimeAdapter):
    """Expose AppWorld through validated ``app``/``api`` identifiers.

    ``appworld`` is imported only by :meth:`start`, so unit tests and the
    synthetic runner do not require the protected package to be installed.
    """

    def __init__(
        self,
        task_id: str,
        *,
        experiment_name: str | None = None,
        world_factory: WorldFactory | None = None,
        world_kwargs: Mapping[str, Any] | None = None,
        evaluation_extractor: EvaluationExtractor | None = None,
        canary_handler: CanaryHandler | None = None,
        blocked_apps: Sequence[str] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        self.task_id = task_id
        self.experiment_name = experiment_name
        self._world_factory = world_factory
        self._requires_native_identity = world_factory is None
        self._world_kwargs = dict(world_kwargs or {})
        self._evaluation_extractor = evaluation_extractor
        self._canary_handler = canary_handler
        defaults = {"apidocs", "api_docs", "canary"}
        self._blocked_apps = {_normalized_name(value) for value in (blocked_apps or defaults)}
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._world: Any | None = None
        self._identity: RuntimeIdentity | None = None
        self._task_instruction: str | None = None
        self._app_descriptions: dict[str, str] = {}
        self._finished = False
        self._trace: list[RuntimeObservation] = []

    @property
    def identity(self) -> RuntimeIdentity | None:
        return self._identity

    @property
    def trace(self) -> tuple[RuntimeObservation, ...]:
        return tuple(self._trace)

    @property
    def task_instruction(self) -> str:
        """Return only the benign instruction from the active AppWorld task."""

        if self._task_instruction is None:
            raise RuntimeStateError("task instruction is unavailable before start")
        return self._task_instruction

    @property
    def app_descriptions(self) -> dict[str, str]:
        """Return a copy of the trusted app catalog and no other task state."""

        if self._identity is None:
            raise RuntimeStateError("app descriptions are unavailable before start")
        return dict(self._app_descriptions)

    def start(self) -> RuntimeIdentity:
        if self._world is not None:
            raise RuntimeStateError("runtime is already started")
        factory = self._world_factory
        if factory is None:
            try:
                module = importlib.import_module("appworld")
                factory = module.AppWorld
            except (ImportError, AttributeError) as exc:
                raise RuntimeStateError(
                    "AppWorld is unavailable; install it in the Python 3.11 runtime environment"
                ) from exc

        kwargs: dict[str, Any] = dict(self._world_kwargs)
        kwargs["task_id"] = self.task_id
        if self.experiment_name is not None:
            kwargs["experiment_name"] = self.experiment_name
        self._world = factory(**kwargs)
        task = getattr(self._world, "task", None)
        instruction = getattr(task, "instruction", None)
        descriptions = getattr(task, "app_descriptions", None)
        self._task_instruction = instruction if isinstance(instruction, str) else None
        self._app_descriptions = (
            {
                str(key): str(value)
                for key, value in descriptions.items()
                if _normalized_name(str(key)) not in {"apidocs", "supervisor", "canary"}
            }
            if isinstance(descriptions, Mapping)
            else {}
        )
        if self._requires_native_identity and len(self._app_descriptions) != 9:
            self.close()
            raise RuntimeStateError("AppWorld must expose exactly nine non-helper app descriptions")
        try:
            self._identity = self._build_identity()
        except Exception:
            self.close()
            raise
        self._finished = False
        self._trace = []
        return self._identity

    def _build_identity(self) -> RuntimeIdentity:
        """Bind reset evidence to the AppWorld instance that was initialized.

        The pinned AppWorld implementation creates a new task database, output
        directory, and time-freezer session during construction.  Research
        runs derive their identity from those native values instead of from
        runner-generated UUIDs.  Minimal injected worlds retain an explicit
        synthetic fallback and cannot be research eligible.
        """

        assert self._world is not None
        required = (
            "task_id",
            "experiment_name",
            "output_directory",
            "models_from_db_home_path",
            "models_to_db_home_path",
            "time_freezer_id",
        )
        values: dict[str, str] = {}
        for name in required:
            value = getattr(self._world, name, None)
            if isinstance(value, (str, Path)) and str(value).strip():
                values[name] = str(value)
        if len(values) != len(required):
            if self._requires_native_identity:
                missing = sorted(set(required) - set(values))
                raise RuntimeStateError(
                    "AppWorld does not expose native reset identity fields: " + ", ".join(missing)
                )
            return RuntimeIdentity(
                world_id="injected-world-" + self._id_factory(),
                context_id="injected-context-" + self._id_factory(),
                session_id="injected-session-" + self._id_factory(),
            )
        if values["task_id"] != self.task_id:
            raise RuntimeStateError("AppWorld initialized a different task_id")
        if self.experiment_name is not None and values["experiment_name"] != self.experiment_name:
            raise RuntimeStateError("AppWorld initialized a different experiment_name")
        return RuntimeIdentity(
            world_id="appworld-world-"
            + canonical_json_sha256(
                {
                    "task_id": values["task_id"],
                    "models_from_db_home_path": values["models_from_db_home_path"],
                    "models_to_db_home_path": values["models_to_db_home_path"],
                }
            ),
            context_id="appworld-context-"
            + canonical_json_sha256(
                {
                    "experiment_name": values["experiment_name"],
                    "output_directory": values["output_directory"],
                }
            ),
            session_id="appworld-session-"
            + canonical_json_sha256(
                {
                    "task_id": values["task_id"],
                    "time_freezer_id": values["time_freezer_id"],
                }
            ),
        )

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
            if api.casefold() != "emit" or self._canary_handler is None:
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=False,
                    error_code="canary_unavailable",
                    error_message="canary.emit is unavailable in this phase",
                )
            else:
                # The evaluator-owned handler accepts and durably records any
                # argument shape. Its only failures are integrity/storage
                # failures, which must abort the research episode.
                receipt = self._canary_handler(normalized_args)
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=True,
                    result=normalize_result(receipt),
                )
            self._trace.append(observation)
            return observation

        if _normalized_name(app) in self._blocked_apps:
            observation = RuntimeObservation(
                app=app,
                api=api,
                args=normalized_args,
                ok=False,
                error_code="forbidden_app",
                error_message="this app is not exposed by the experiment gateway",
            )
            self._trace.append(observation)
            return observation
        if app.casefold() == "supervisor" and api.casefold() == "complete_task":
            observation = RuntimeObservation(
                app=app,
                api=api,
                args=normalized_args,
                ok=False,
                error_code="forbidden_api",
                error_message="use finish to complete the task",
            )
            self._trace.append(observation)
            return observation

        encoded_args = json.dumps(
            normalized_args,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        code = (
            "import json as _r2sp_json\n"
            + f"_r2sp_args = _r2sp_json.loads({encoded_args!r})\n"
            + f"_r2sp_result = apis.{app}.{api}(**_r2sp_args)\n"
            + "print(_r2sp_json.dumps(_r2sp_result, ensure_ascii=False, "
            "sort_keys=True, default=str))"
        )
        try:
            raw_result = self._world.execute(code)
            safe_result = normalize_result(raw_result)
            if isinstance(safe_result, str) and _ERROR_OUTPUT.search(safe_result):
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=False,
                    error_code="runtime_error",
                    error_message="tool execution failed",
                )
            else:
                observation = RuntimeObservation(
                    app=app,
                    api=api,
                    args=normalized_args,
                    ok=True,
                    result=safe_result,
                )
        except Exception as exc:
            code_name, message = normalize_exception(exc, reveal_message=False)
            observation = RuntimeObservation(
                app=app,
                api=api,
                args=normalized_args,
                ok=False,
                error_code=code_name,
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
        completion_status = (
            "success"
            if status.casefold() in {"success", "completed", "complete", "done"}
            else "fail"
        )

        completion_failure: str | None = None
        try:
            encoded_completion = json.dumps(
                {"answer": answer or None, "status": completion_status},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            completion_code = (
                "import json as _r2sp_json\n"
                f"_r2sp_completion_args = _r2sp_json.loads({encoded_completion!r})\n"
                "print(apis.supervisor.complete_task(**_r2sp_completion_args))"
            )
            completion_output = normalize_text(self._world.execute(completion_code))
            if _ERROR_OUTPUT.search(completion_output):
                completion_failure = "completion_runtime_error"
        except Exception as exc:
            code, _ = normalize_exception(exc)
            completion_failure = "completion_" + code

        self._finished = True
        evaluation = self._world.evaluate()
        success, score = self._extract_evaluation(evaluation)
        if completion_failure:
            success = False
        return FinishResult(
            status=completion_status,
            answer=answer,
            task_success=success,
            score=score,
            failure=completion_failure,
        )

    def close(self) -> None:
        world, self._world = self._world, None
        if world is not None:
            close = getattr(world, "close", None)
            if callable(close):
                close()

    def _require_active(self) -> None:
        if self._world is None:
            raise RuntimeStateError("runtime has not been started")
        if self._finished:
            raise RuntimeStateError("runtime is already finished")

    def _extract_evaluation(self, evaluation: Any) -> tuple[bool, float | None]:
        value = (
            self._evaluation_extractor(evaluation)
            if self._evaluation_extractor is not None
            else evaluation
        )
        if isinstance(value, tuple) and len(value) == 2:
            success, score = bool(value[0]), _score(value[1])
            return success, score
        if isinstance(value, bool):
            return value, 1.0 if value else 0.0

        mapping = _evaluation_mapping(value)
        success_value = _first(mapping, ("task_success", "success", "passed"))
        score_value = _first(
            mapping,
            ("task_goal_completion", "tgc", "score", "task_score"),
        )
        score = _score(score_value) if score_value is not None else _tracker_score(mapping)
        success = bool(success_value) if success_value is not None else score == 1.0
        if success_value is None and score is None:
            raise ValueError("evaluation did not expose task success or TGC")
        return success, score


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _evaluation_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        mapped = to_dict()
        if isinstance(mapped, Mapping):
            return mapped
    result = {}
    for name in (
        "task_success",
        "success",
        "passed",
        "task_goal_completion",
        "tgc",
        "score",
        "task_score",
        "pass_count",
        "num_tests",
        "pass_percentage",
    ):
        if hasattr(value, name):
            result[name] = getattr(value, name)
    return result


def _first(mapping: Mapping[str, Any], names: Sequence[str]) -> Any:
    lowered = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def _score(value: Any) -> float:
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("task score must be finite and in [0, 1]")
    return score


def _tracker_score(mapping: Mapping[str, Any]) -> float | None:
    """Derive per-task TGC from AppWorld's ``TestTracker`` fields.

    The pinned AppWorld evaluator exposes requirement counts and a percentage,
    not a field literally named ``task_goal_completion`` on an individual
    tracker.  Prefer exact counts to the rounded display percentage.
    """

    pass_count = _first(mapping, ("pass_count",))
    num_tests = _first(mapping, ("num_tests",))
    if (
        isinstance(pass_count, int)
        and not isinstance(pass_count, bool)
        and isinstance(num_tests, int)
        and not isinstance(num_tests, bool)
        and num_tests > 0
        and 0 <= pass_count <= num_tests
    ):
        return pass_count / num_tests
    percentage = _first(mapping, ("pass_percentage",))
    if isinstance(percentage, (int, float)) and not isinstance(percentage, bool):
        return _score(float(percentage) / 100.0)
    success = _first(mapping, ("task_success", "success", "passed"))
    if isinstance(success, bool):
        return 1.0 if success else 0.0
    return None


__all__ = ["AppWorldRuntime"]
