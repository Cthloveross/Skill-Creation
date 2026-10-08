"""Run the published CoEvoSkills controller; adapt transport and sealed evidence only."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from .artifacts import (
    EvolutionSubmission,
    SkillBundle,
    atomic_json,
    decode_package_text,
    is_runtime_cache,
    seal_bundle,
)
from .author_controller import AuthorControllerBridge
from .author_verifier import author_module
from .evolution import EvolutionResult
from .journal import UnknownOperation
from .model import InputTokenBudgetExceeded
from .skillsbench import _EVOLUTION_PRIVATE_ROOTS


def _read_package(path: Path, parent_hash: str | None) -> SkillBundle:
    files = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise ValueError("author_package_special_file")
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            if not is_runtime_cache(relative):
                files[relative] = decode_package_text(item.read_bytes(), relative)
    return SkillBundle(files, parent_hash=parent_hash)


def run_author_evolution(
    session: Any,
    initial: SkillBundle,
    base: Any,
    generator: Any,
    verifier: Any,
    *,
    journal: Any,
    root: Path,
    token_counter: Any,
    settings: dict[str, Any],
    deadline: float,
    adapter_prompt: str,
) -> EvolutionResult:
    """No local verification/selection loop: all such decisions remain upstream."""
    from harbor.models.agent.context import AgentContext

    operation = "published-author-controller"
    if journal.completed(operation):
        return EvolutionResult.from_dict(journal.response(operation))
    if journal.status(operation) != "NOT_SENT":
        raise UnknownOperation("author_controller_interrupted_requires_new_trial")
    private = root / "private" / "author-controller"
    environment_dir = private / session.adapter.task_id / "environment"
    environment_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        session.runner.task_directory / "task.toml", environment_dir.parent / "task.toml"
    )
    bridge = AuthorControllerBridge(
        generator,
        verifier,
        session.runner,
        journal,
        operation_id=operation,
        environment_dir=environment_dir,
        token_counter=token_counter,
        deadline=deadline,
        max_input_tokens=settings["max_input_tokens"],
        record_tool_result=session.record_tool_result,
    )
    versions = {initial.bundle_hash: initial}
    submissions: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    oracle_history: list[dict[str, Any]] = []
    current = initial
    terminal: dict[str, Any] = {}
    episodes = 0
    latest_verification: Any = None
    verification_cursor = 0
    rolled_back: SkillBundle | None = None
    rollback: dict[str, Any] | None = None
    native = author_module("agents.terminus_2.harbor_terminus_2_evolution")

    def seal_current(kind: str = "model_task_complete") -> EvolutionSubmission | None:
        nonlocal current
        bridge.check()
        try:
            files = session.files()
            first = not submissions and files == dict(initial.files)
            bundle = initial if first else SkillBundle(files, parent_hash=current.bundle_hash)
        except ValueError as exc:
            # A malformed draft is not a version. Let the original controller's
            # schema/repair branch run instead of prematurely aborting it here.
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "status": "invalid",
                    "parent_hash": current.bundle_hash,
                    "reason": str(exc),
                }
            )
            atomic_json(private / "attempts.json", attempts)
            return None
        with session.runner.snapshot_workspace() as mounts:
            trace = {
                "task_id": session.adapter.task_id,
                "events": [],
                "executor": {"framework": "published-generator-direct"},
                **session.adapter._seal_public_workspace(
                    mounts, excluded_roots=_EVOLUTION_PRIVATE_ROOTS
                ),
            }
        if session.files() != files:
            raise ValueError("author_candidate_changed_during_submission")
        submission = EvolutionSubmission(
            bundle, trace, session.state["execution_id"], len(bridge.terminal_results), first
        )
        submissions.append(
            {
                "bundle_hash": bundle.bundle_hash,
                "parent_hash": bundle.parent_hash,
                "execution_id": submission.execution_id,
                "operation_cursor": submission.operation_cursor,
                "initial": submission.initial,
                "submission_kind": kind,
                "submission_hash": submission.submission_hash,
                "trace_hash": submission.trace_hash,
            }
        )
        atomic_json(private / f"submission-{len(submissions)}.json", submission.to_dict())
        if not first:
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "parent_hash": current.bundle_hash,
                    "bundle_hash": bundle.bundle_hash,
                    "status": "unchanged"
                    if bundle.bundle_hash == current.bundle_hash
                    else "changed",
                }
            )
        versions.setdefault(bundle.bundle_hash, bundle)
        seal_bundle(root / "versions" / bundle.bundle_hash, versions[bundle.bundle_hash])
        current = bundle
        atomic_json(private / "submissions.json", submissions)
        return submission

    class Controller(native.HarborTerminus2Evolution):
        # Methods below only connect the existing experiment's runtime/evidence.
        def _get_max_context_tokens(self) -> int:
            observed = getattr(self._llm, "last_context_budget", {}).get("context_window")
            return (
                min(settings["context_window"], observed)
                if observed
                else settings["context_window"]
            )

        async def _export_skills_from_container(
            self,
            environment: Any,
            skill_names: set[str],
            target_dir: Path,
            include_references: bool = False,
        ) -> list[str]:
            exported = await super()._export_skills_from_container(
                environment, skill_names, target_dir, include_references=include_references
            )
            if "evo-current" in exported:
                try:
                    files = session.files()
                    SkillBundle(files)
                except ValueError:
                    return exported  # Preserve the native schema/repair branch.
                try:
                    target = target_dir / "evo-current"
                    partial = _read_package(target, None)
                    if any(files.get(path) != text for path, text in partial.files.items()):
                        raise ValueError("author_export_differs_from_candidate")
                    # Native export copies scripts/references only. Preserve the
                    # creator's evals/assets and other safe text resources for GT,
                    # best snapshots and rollback, without host manifest metadata.
                    for path, text in files.items():
                        destination = target / path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(text, encoding="utf-8")
                    if session.files() != files:
                        raise ValueError("author_candidate_changed_during_export")
                except BaseException as exc:
                    bridge.runs["environment"].fatal = exc
                    raise
            return exported

        async def _check_episode_exit(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal episodes
            episodes = kwargs["episode"]
            observed = getattr(self._llm, "last_context_budget", {})
            if observed and self._chat is not None:
                occupied = sum(
                    observed[name] for name in ("input_tokens", "output_tokens", "reserve_tokens")
                )
                visible = self._chat.last_input_tokens
                self._chat._last_input_tokens = max(visible, occupied)
                atomic_json(
                    private / "context-budget.json",
                    {
                        "episode": episodes,
                        "visible_input_estimate": visible,
                        "provider_context": observed,
                        "effective_window": self._get_max_context_tokens(),
                        "native_occupancy": self._chat.last_input_tokens,
                    },
                )
            if kwargs["result"].is_task_complete:
                seal_current()
            outcome = await super()._check_episode_exit(*args, **kwargs)
            if checks and latest_verification is not None:
                checks[-1]["diagnosis"] = latest_verification.diagnosis
                checks[-1]["author_result"] = latest_verification.to_dict()
                atomic_json(private / "verifications.json", checks)
            return outcome

        async def _record_intervention(self, *args: Any, **kwargs: Any) -> Any:
            try:
                changed = session.files() != dict(current.files)
            except ValueError:
                changed = True
            if not submissions or changed:
                seal_current("host_forced_submission")
            try:
                checked_hash = (
                    current.bundle_hash if session.files() == dict(current.files) else None
                )
            except ValueError:
                checked_hash = None
            entry = await super()._record_intervention(*args, **kwargs)
            if entry.get("surrogate_result") is not None and latest_verification is not None:
                raw = latest_verification.to_dict()
                script = await bridge.environment.exec(
                    "cat /root/verifier/test_outputs.py 2>/dev/null || true", timeout_sec=15
                )
                digest = hashlib.sha256((script.stdout or "").encode()).hexdigest()
                previous = list(dict.fromkeys(item["test_hash"] for item in checks))
                checks.append(
                    {
                        "bundle_hash": checked_hash,
                        "test_version": previous.index(digest) + 1
                        if digest in previous
                        else len(previous) + 1,
                        "test_hash": digest,
                        "passed": (
                            raw.get("source") == "script"
                            and raw.get("total_tests", 0) > 0
                            and raw.get("tests_failed", 0) == 0
                            and raw.get("tests_passed") == raw.get("total_tests")
                        )
                        if checked_hash is not None
                        else None,
                        "pass_rate": raw.get("pass_rate", 0.0),
                        "failure": raw.get("error")
                        if checked_hash is not None
                        else "invalid_candidate",
                        "candidate_status": "SEALED" if checked_hash is not None else "UNSEALED",
                        "program_error": raw.get("source") in {"no_script", "script_error"},
                        "diagnosis": raw.get("diagnosis", ""),
                        "recommendations": [],
                        "results": raw.get("test_details", []),
                        "author_result": raw,
                    }
                )
                atomic_json(private / "verifications.json", checks)
            return entry

        async def _run_gt_oracle_check(
            self,
            instruction: str,
            environment: Any,
            oracle_model: Any = None,
            evolved_skills_dir: Path | None = None,
            oracle_label: str | None = None,
        ) -> dict[str, Any] | None:
            bridge.check()
            phase = (
                "post_final"
                if oracle_label == "gt-oracle-final"
                else (
                    "cap_final"
                    if self._exit_reason in {"max_interventions", "max_surrogate_retries"}
                    else "normal"
                )
            )
            try:
                directories = list(evolved_skills_dir.glob("evo-*")) if evolved_skills_dir else []
                if len(directories) != 1 or directories[0].name != "evo-current":
                    raise ValueError("author_submission_requires_single_evo_current_package")
                candidate = _read_package(directories[0], current.parent_hash)
                match = (
                    current
                    if candidate.bundle_hash == current.bundle_hash
                    else versions.get(candidate.bundle_hash)
                )
                if match is None:
                    seal_current("terminal_gt")
                    match = versions.get(candidate.bundle_hash)
                if match is None:
                    raise ValueError("oracle_package_not_sealed")
                if phase == "post_final":
                    eligible = [
                        item
                        for item in oracle_history
                        if item["status"] == "MEASURED" and item["phase"] != "post_final"
                    ]
                    best = (
                        max(eligible, key=lambda item: item["resolved_reward"])
                        if eligible
                        else None
                    )
                    native_best = getattr(self, "_best_gt_snapshot", None)
                    if (
                        best
                        and best["bundle_hash"] == candidate.bundle_hash
                        and (
                            candidate.bundle_hash != current.bundle_hash
                            or native_best
                            and Path(native_best.get("skills_dir", "")) == evolved_skills_dir
                        )
                    ):
                        match = replace(match, parent_hash=best["parent_hash"])
                gt_operation = f"author-gt-{len(oracle_history)}"
                result = await asyncio.to_thread(
                    journal.dispatch,
                    gt_operation,
                    {"bundle_hash": candidate.bundle_hash, "phase": phase},
                    lambda: session.adapter.oracle(match, phase=phase),
                )
            except BaseException as exc:
                # Native GT catches must not turn a broken bridge or UNKNOWN
                # operation into further model requests.
                bridge.runs["environment"].fatal = exc
                raise
            oracle_history.append({"operation_id": gt_operation, **result})
            atomic_json(private / "oracle-history.json", oracle_history)
            bridge.check()
            if result["status"] != "MEASURED":
                return {"error": result.get("failure") or "official_score_unavailable"}
            return {
                "passed": result["passed"],
                "reward": result["canonical_reward"],
                "tests_passed": result["tests_passed"],
                "total_tests": result["total_tests"],
                "pass_rate": result["resolved_reward"],
                # Full GT evidence stays private; this experiment retains its
                # boolean learning-side oracle rather than GT-derived labels.
                "test_details": [],
            }

        def _write_evolution_log(self, *args: Any, **kwargs: Any) -> None:
            terminal.update(kwargs.get("gt_oracle_result") or {})
            if terminal and not terminal.get("error"):
                terminal["resolved_reward"] = self._gt_full_score_and_reward(terminal)[1]
            super()._write_evolution_log(*args, **kwargs)

        def _rollback_host_skills(self, environment: Any, skills_dir: Any) -> None:
            nonlocal rolled_back, rollback
            source = _read_package(Path(skills_dir) / "evo-current", None)
            eligible = [
                item
                for item in oracle_history
                if item["status"] == "MEASURED" and item["phase"] != "post_final"
            ]
            reference = (
                max(eligible, key=lambda item: item["resolved_reward"]) if eligible else None
            )
            if reference is None or source.bundle_hash not in versions:
                raise ValueError("rollback_package_not_sealed")
            if reference["bundle_hash"] != source.bundle_hash:
                raise ValueError("rollback_package_differs_from_author_best")
            super()._rollback_host_skills(environment, skills_dir)
            target = environment_dir / "skills" / "evo-current"
            try:
                if _read_package(target, None).bundle_hash != source.bundle_hash:
                    raise ValueError("rollback_package_hash_mismatch")
            except (OSError, ValueError) as exc:
                rollback = {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "bundle_hash": source.bundle_hash,
                }
                atomic_json(private / "rollback.json", rollback)
                return
            rolled_back = replace(
                versions[source.bundle_hash], parent_hash=reference["parent_hash"]
            )
            rollback = {
                "status": "COMPLETED",
                "bundle_hash": rolled_back.bundle_hash,
                "parent_hash": rolled_back.parent_hash,
            }
            atomic_json(private / "rollback.json", rollback)

    def run() -> dict[str, Any]:
        agent = bridge.build_agent(
            Controller,
            logs_dir=private / "logs",
            model_name=generator.config.model,
            independent_verifier_model=verifier.config.model,
            gt_oracle_agent="codex-skill-only",
            max_episodes=settings["max_episodes"],
            timeout_multiplier=5,
        )

        def input_budget_stop(error: InputTokenBudgetExceeded) -> None:
            agent._exit_reason = "token_budget"
            atomic_json(
                private / "input-budget-stop.json",
                {
                    "dispatch": "NOT_SENT",
                    "input_tokens": error.input_tokens,
                    "max_input_tokens": error.max_input_tokens,
                    "source": "transport_admission",
                    "generator_model_cursor": bridge.runs["generator"].model_cursor,
                },
            )

        bridge.runs["generator"].owner.on_input_budget_stop = input_budget_stop
        for component, name in (
            (agent._verifier, "verify"),
            (agent._independent_verifier, "generate_and_run"),
        ):
            original = getattr(component, name)

            def candidate_manifest() -> dict[str, Any]:
                try:
                    return session.snapshot()["candidate_manifest"]
                except ValueError as exc:
                    # Evidence must not preempt the author's schema repair.
                    return {"invalid_candidate": str(exc)}

            async def capture(
                *args: Any, _original: Any = original, _name: str = name, **kwargs: Any
            ) -> Any:
                nonlocal latest_verification, verification_cursor
                cursor = verification_cursor
                verification_cursor += 1
                before = candidate_manifest()
                value = await _original(*args, **kwargs)
                latest_verification = value
                after = candidate_manifest()
                changes = {"before": before, "after": after, "changed": before != after}
                journal.dispatch(
                    f"author-verification-source-{cursor}-{_name}",
                    changes,
                    lambda: changes,
                    external=False,
                )
                return value

            setattr(component, name, capture)
        instruction = base.public_inputs["opening"] + "\n\n" + adapter_prompt

        async def execute() -> None:
            await bridge.setup(agent)
            try:
                await bridge.run(agent, instruction, AgentContext(metadata={}))
            except InputTokenBudgetExceeded as error:
                if bridge.runs["generator"].input_budget_stop is not error:
                    raise
                bridge.check()
                # The unchanged run finishes its native post-final branches and
                # then rethrows the original loop error. Only this proven
                # predispatch stop may complete; UNKNOWN remains fatal.
                log = json.loads((private / "logs" / "evolution_run_log.json").read_text())
                if log.get("timing", {}).get("exit_reason") != "token_budget":
                    raise

        asyncio.run(execute())
        # Native final host export can omit references. Never turn that partial
        # export into a new, untested content version. Observe native rollback.
        selected = rolled_back or current
        raw_log = json.loads((private / "logs" / "evolution_run_log.json").read_text())
        best = raw_log.get("best_gt_snapshot")
        history = tuple(item for item in oracle_history if item["status"] == "MEASURED")
        selection_history = tuple(item for item in history if item["phase"] != "post_final")
        best_ref = (
            max(selection_history, key=lambda item: item["resolved_reward"])
            if selection_history
            else None
        )
        result = EvolutionResult(
            versions=tuple(versions.values()),
            attempts=tuple(attempts),
            verifications=tuple(checks),
            oracle_results=tuple(item["passed"] for item in history),
            revision_attempts=len(attempts),
            stop_reason=agent._exit_reason or "execution_episodes",
            final_bundle_hash=selected.bundle_hash,
            final_bundle_ref={
                "bundle_hash": selected.bundle_hash,
                "parent_hash": selected.parent_hash,
            },
            submissions=tuple(submissions),
            oracle_failures=tuple(item for item in oracle_history if item["status"] != "MEASURED"),
            oracle_history=tuple(oracle_history),
            best_oracle_ref=best_ref,
            author_terminal_result=terminal,
            best_snapshot={
                "author_record": best,
                "record_available": best is not None,
                "rollback": rollback,
            },
            selection_reason="published_controller",
            interventions=tuple(agent._intervention_history),
            author_counters={
                "surrogate_retries": agent._surrogate_retry_count,
                "normal_oracle_interventions": agent._host_intervention_count,
                "generator_model_attempts": bridge.runs["generator"].model_cursor,
                "generator_responses": sum(
                    journal.completed(f"{bridge.runs['generator'].operation_id}-model-{cursor}")
                    for cursor in range(bridge.runs["generator"].model_cursor)
                ),
                "generator_episodes": episodes,
                "generator_terminal_calls": sum(
                    item["actor"] == "generator" for item in bridge.terminal_results
                ),
                "verifier_terminal_calls": sum(
                    item["actor"] == "verifier" for item in bridge.terminal_results
                ),
            },
        )
        return result.to_dict()

    return EvolutionResult.from_dict(
        journal.dispatch(
            operation,
            {"initial_bundle_hash": initial.bundle_hash, "base_hash": base.base_hash},
            run,
        )
    )
