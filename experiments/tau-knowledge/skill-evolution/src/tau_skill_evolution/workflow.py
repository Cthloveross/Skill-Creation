"""The supported create → evolve → independently evaluate workflow."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .acquisition import READ_ONLY_TOOL_NAMES, AcquisitionBudgets, collect_base
from .artifacts import FrozenBase, atomic_json, load_base, load_bundle, seal_base, seal_bundle
from .bank import BankWorkerError
from .container import ContainerUnavailable
from .core._canonical import thaw_json
from .credentials import bearer_token_source
from .generator import (
    SKILL_BUNDLE_RESPONSE_FORMAT,
    CreationFailure,
    execute_initial,
    generate_initial,
    revise,
)
from .journal import Journal, UnknownOperation, _create_identity_exclusive, identity_temporary
from .model import (
    CredentialError,
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
    SerializedChatTokenCounter,
)
from .retrieval import prepare_corpus, text_counter
from .spec import NAMESPACES, ExperimentSpec, digest


def _launcher_entry(path: Path) -> bool:
    """Run-dir entries that may exist before the first checkpoint identity.

    The CLI/launcher pre-create ``.lock``, ``locks/``, ``logs/`` and
    ``launcher-*``; a concurrent process that is still creating
    ``journal/identity.json`` leaves a ``journal/`` holding only temporaries.
    """
    name = path.name
    if name in {".lock", "locks", "logs"} or name.startswith("launcher-"):
        return True
    if name == "journal" and path.is_dir():
        return all(identity_temporary(entry.name) for entry in path.iterdir())
    return False


class Workflow:
    def __init__(
        self,
        spec: ExperimentSpec,
        run_dir: Path,
        *,
        bank_factory: Any = None,
        model_factory: Any = None,
        corpus_factory: Any = None,
        counter: Any = None,
        runner: Any = None,
        demo: bool = False,
        demo_task: str | None = None,
        interim_report: bool = True,
        runtime: str | None = None,
    ) -> None:
        if spec.namespace != NAMESPACES[spec.experiment]:
            raise ValueError("historical methods are read-only; start a new current-method trial")
        self.spec = spec
        self.demo = demo
        self.runtime = runtime or ("bubblewrap-demo" if demo else "docker")
        if self.runtime not in {"workspace", "docker", "bubblewrap-demo"}:
            raise ValueError("unsupported runtime")
        if demo != (self.runtime == "bubblewrap-demo"):
            raise ValueError("demo and runtime differ")
        self.interim_report = interim_report
        self.demo_task = demo_task or spec.tasks[0]
        if demo and self.demo_task not in spec.tasks:
            raise ValueError("demo task is outside the fixed sample")
        self.root = Path(run_dir)
        if (
            self.root.exists()
            and not (self.root / "journal" / "identity.json").exists()
            and any(not _launcher_entry(path) for path in self.root.iterdir())
        ):
            raise ValueError("run directory has no compatible Skill evolution checkpoint identity")
        self.identity = spec.identity
        self.experiment_identity = dict(self.identity)
        self.execution: dict[str, Any] = {"backend": "docker", "formal_matrix_result": False}
        if self.runtime != "docker":
            lock_path = (
                spec.root / spec.values["source"]["runtime_lock"]
                if spec.experiment == "skillsbench"
                else spec.root / "runtime" / "bubblewrap-lock.json"
            )
            if demo and spec.experiment == "tau":
                from .bubblewrap import RuntimeLock

                RuntimeLock.from_file(lock_path).validate()
            self.execution = {
                "backend": self.runtime,
                "formal_matrix_result": False,
                "aggregate_limits_enforced": False,
                "runtime_lock_hash": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                "formal_environment_equivalent": False,
                "resources_scope": "local_process",
            }
            if demo:
                self.execution["task_id"] = self.demo_task
            self.identity = {
                **self.identity,
                "execution": self.execution,
                "identity_hash": digest(
                    {"base": self.identity["identity_hash"], "execution": self.execution}
                ),
            }
        self.journal = Journal(self.root / "journal", identity=self.identity)
        trial_path = self.root / "journal" / "trial.json"
        _create_identity_exclusive(trial_path, {"trial_id": uuid.uuid4().hex})
        self.trial_id = json.loads(trial_path.read_text())["trial_id"]
        if not isinstance(self.trial_id, str) or len(self.trial_id) != 32:
            raise ValueError("invalid_trial_identity")
        self.identity = {**self.identity, "trial_id": self.trial_id}
        self.bank_factory = bank_factory
        self.model_factory = model_factory
        self.corpus_factory = corpus_factory
        self.counter = counter or text_counter(spec)
        self.runner = runner
        self._historical_authentication_failures = {
            (task, arm)
            for task, arm in spec.cells
            if (self.root / "cells" / task / arm / "journal" / "identity.json").is_file()
            and self._cell(task, arm)[1].authentication_failure() is not None
        }

    def _prompt(self, role: str) -> str:
        directory = self.spec.root / "prompts"
        setting = self.spec.values["roles"].get(role, {}).get("prompt")
        if setting:
            return (directory / setting).read_text(encoding="utf-8")
        selected = directory / f"{role}-skillsbench.md"
        if self.spec.experiment != "skillsbench" or not selected.exists():
            selected = directory / f"{role}.md"
        return selected.read_text(encoding="utf-8")

    def _bind_skillsbench_retrieval(
        self, task: str, arm: str, journal: Journal, *, recovering_base: bool = False
    ) -> dict[str, Any] | None:
        """Seal the exact v8 corpus and index contract before Analyzer use."""
        # Custom corpus factories deliberately replace the production retriever
        # in unit tests and integrations, so they have no sealed v8 index to bind.
        if (
            self.spec.experiment != "skillsbench"
            or self.spec.namespace != "skillsbench.skill-evolution.v8"
            or self.corpus_factory is not None
        ):
            return None
        operation = "retrieval-corpus-contract"
        if recovering_base and not journal.completed(operation):
            raise ValueError("retrieval_contract_missing_requires_new_trial")
        if not journal.completed(operation) and any(
            json.loads(path.read_text())["operation_id"].startswith("acquisition/")
            for path in journal.root.glob("*/request.json")
        ):
            raise ValueError("retrieval_contract_missing_requires_new_trial")
        from .skillsbench_attack import retrieval_contract

        contract = {
            "task_id": task,
            "condition_id": arm,
            "retrieval": retrieval_contract(self.spec, arm),
        }
        return journal.dispatch(operation, contract, lambda: contract, external=False)

    def _model(self, role: str, *, phase: str = "create", scope: str = "unscoped") -> Any:
        if self.model_factory is not None:
            return self.model_factory(role)
        provider = self.spec.provider_settings
        settings = (
            self.spec.values["roles"][role]
            if role in self.spec.values["roles"]
            else self.spec.values["runtime"]["controls"]["agent"]
        )
        options = {
            "config": GenerationConfig(
                model=provider["model"],
                transport=provider["transport"],
                reasoning_effort=settings["reasoning_effort"],
                max_output_tokens=settings["max_output_tokens"],
                max_input_tokens=settings.get(
                    "max_input_tokens", self.spec.values["runtime"]["controls"]["max_input_tokens"]
                ),
                response_format=SKILL_BUNDLE_RESPONSE_FORMAT
                if role == "generator" and phase == "create"
                else None,
            ),
            "timeout_seconds": self.spec.values["runtime"]["request_timeout_seconds"],
            "token_counter": SerializedChatTokenCounter(
                self.counter, basis="embedding_responses_input_estimate_with_reasoning_reserve"
            ),
            "usage_path": self.root / "usage.jsonl",
            "usage_role": role,
        }
        if provider["transport"] == "codex-plan":
            from .codex_plan import CodexPlanClient

            return CodexPlanClient(
                role=role,
                binary=provider["binary"],
                journal_dir=self.root / "private" / "codex-plan" / scope / role / phase,
                context_window=settings.get("context_window"),
                context_fraction=settings.get("context_beta"),
                output_reserve=(
                    int(settings["context_window"] * settings["context_beta"])
                    - settings["max_input_tokens"]
                    if "context_window" in settings
                    else 0
                ),
                **options,
            )
        return OpenAICompatibleClient(
            provider["api_base"],
            api_key=bearer_token_source(provider["api_key_env"]),
            **options,
        )

    @contextmanager
    def _model_context(self, role: str, *, phase: str = "create", scope: str) -> Any:
        model = self._model(role, phase=phase, scope=scope)
        try:
            yield model
        finally:
            self._close_model(model)

    @staticmethod
    def _close_model(model: Any) -> None:
        close = getattr(model, "close", None)
        if callable(close):
            close()

    def _bank(self, task: str, arm: str = "benign") -> Any:
        if self.bank_factory is not None:
            return self.bank_factory(task)
        if self.spec.experiment == "skillsbench":
            from .skillsbench import SkillsBenchAdapter

            return SkillsBenchAdapter(
                self.spec,
                task,
                demo=self.demo,
                runtime=self.runtime,
                model_factory=self._model,
                counter=self.counter,
                artifact_root=self.root / "artifacts" / task,
                model_journal_dir=self.root / "private" / "skillsbench-models",
                condition=arm,
            )
        from .bank import Bank

        config = self.spec.worker_config(runtime=self.runtime)
        config["usage_path"] = str((self.root / "usage.jsonl").resolve())
        config["worker_log_dir"] = str((self.root / "logs" / "workers").resolve())
        config["model_journal_dir"] = str((self.root / "private" / "bank-models").resolve())
        config["attack_profile"] = self.spec.profile(task)
        return Bank(
            self.spec.upstream / ".venv" / "bin" / "python", self.spec.upstream, task, config
        )

    def _runner(self) -> Any:
        if self.runner is None:
            if self.runtime != "docker":
                from .bubblewrap import BubblewrapRunner, RuntimeLock

                self.runner = BubblewrapRunner(
                    RuntimeLock.from_file(self.spec.root / "runtime" / "bubblewrap-lock.json"),
                    runtime=self.runtime,
                )
                return self.runner
            from .container import DockerRunner, ImageLock

            self.runner = DockerRunner(
                ImageLock.from_file(self.spec.root / "runtime" / "image-lock.json")
            )
        return self.runner

    def _cell(self, task: str, arm: str) -> tuple[Path, Journal]:
        if (task, arm) not in self.spec.cells:
            raise ValueError("cell is outside the fixed experiment matrix")
        if self.demo and (task, arm) != (self.demo_task, "benign"):
            raise ValueError("demo permits only its fixed single benign task")
        root = self.root / "cells" / task / arm
        journal = Journal(root / "journal", identity={**self.identity, "task": task, "arm": arm})
        return root, journal

    def _created(self, root: Path, journal: Journal) -> tuple[Any, Any]:
        record = journal.response("creation")
        base = load_base(root / "base")
        initial = load_bundle(root / "initial")
        if (
            base.base_hash != record["base_hash"]
            or initial.bundle_hash != record["initial_bundle_hash"]
        ):
            raise ValueError("sealed creation artifacts differ from the creation record")
        return base, initial

    def _collected_base(self, root: Path, journal: Journal) -> FrozenBase:
        base = load_base(root / "base")
        if base.to_dict() != journal.response("collect-base"):
            raise ValueError("sealed frozen base differs from the acquisition record")
        return base

    def _static_persistence(self, arm: str, bundles: Any) -> dict[str, Any]:
        if self.spec.namespace != "skillsbench.skill-evolution.v8":
            return {}
        from .skillsbench_attack_runtime import static_attack_persistence

        profile = self.spec.condition(arm)["profile"]
        return {
            bundle.bundle_hash: static_attack_persistence(bundle, profile) for bundle in bundles
        }

    def create(self, cells: tuple[tuple[str, str], ...]) -> None:
        self._validate_cells(cells)
        for task, arm in cells:
            self._create_cell(task, arm)
            self._halt_on_authentication(task, arm)

    def _halt_on_authentication(self, task: str, arm: str) -> None:
        _, journal = self._cell(task, arm)
        status = journal.authentication_failure()
        if status is not None:
            raise ModelClientError(
                "authentication_failed",
                f"Model provider authentication failed (HTTP {status}); later cells stopped",
                status=status,
            )

    @staticmethod
    def _learning_close_failure(journal: Journal) -> dict[str, Any] | None:
        failures = []
        for path in journal.root.glob("*/request.json"):
            operation = json.loads(path.read_text())["operation_id"]
            if operation.startswith("learning-environment-failure-") and journal.completed(
                operation
            ):
                failure = journal.response(operation)
                if failure.get("stage") == "close":
                    failures.append(failure)
        return max(failures, key=lambda item: item["index"], default=None)

    def _halt_on_learning_close_failure(self, journal: Journal) -> None:
        # The author can finish before the owning learning environment closes.
        # Keep its completed result, but never resume dispatch after failed cleanup.
        if (
            self.spec.experiment == "skillsbench"
            and self._learning_close_failure(journal) is not None
        ):
            raise ContainerUnavailable("skillsbench_learning_environment_close_failed")

    def run(self, cells: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        self._validate_cells(cells)
        for cell in cells:
            # A new CLI invocation has passed authentication preflight. Preserve
            # prior failed chains without retrying their unknown requests, then
            # continue unstarted cells. New failures still halt this invocation.
            if cell in self._historical_authentication_failures:
                continue
            try:
                self.create((cell,))
                self.evolve((cell,))
                self.evaluate((cell,))
            finally:
                if self.interim_report:
                    self.report()
        if not self.interim_report:
            # Concurrent per-cell processes share one run dir; only the launcher
            # writes report.json after every cell finished.
            return {
                "namespace": self.spec.namespace,
                "stage": "run",
                "cells": [[task, arm] for task, arm in cells],
                "interim_report": False,
                "run_dir": str(self.root),
            }
        return self.report()

    def _create_cell(self, task: str, arm: str) -> None:
        root, journal = self._cell(task, arm)
        self._halt_on_learning_close_failure(journal)
        if journal.dispatched("imported-versions"):
            raise ValueError("imported evaluation cells cannot create or evolve a new Skill")
        if journal.completed("creation"):
            record = journal.response("creation")
            if record["status"] == "CREATED":
                self._created(root, journal)
            return
        base: FrozenBase | None = None
        try:
            bank = self._bank(task, arm)
            if (root / "base").exists():
                self._bind_skillsbench_retrieval(task, arm, journal, recovering_base=True)
                base = load_base(root / "base")
            else:

                def acquire() -> dict[str, Any]:
                    options = {}
                    if self.spec.experiment == "tau":
                        checkpoint = (
                            self.root / "private" / "acquisition" / task / arm / "session.json"
                        ).resolve()
                        if not checkpoint.is_file() and any(
                            json.loads(path.read_text())["operation_id"].startswith("acquisition/")
                            for path in journal.root.glob("*/request.json")
                        ):
                            raise ValueError("acquisition_snapshot_missing_requires_new_trial")
                        options = {
                            "checkpoint": checkpoint,
                            "identity": {**self.identity, "task": task, "arm": arm},
                        }
                    with bank.acquisition(**options) as session:
                        corpus = (
                            self.corpus_factory(task, arm)
                            if self.corpus_factory
                            else prepare_corpus(self.spec, task, arm)
                        )
                        self._bind_skillsbench_retrieval(task, arm, journal)
                        allowed_reads = (
                            session.allowed_read_only_tool_names
                            if self.spec.experiment == "skillsbench"
                            else READ_ONLY_TOOL_NAMES
                        )
                        reads = {
                            name: (lambda name=name, **arguments: session.read(name, arguments))
                            for name in allowed_reads
                        }
                        schemas = [
                            schema
                            for schema in session.tool_schemas
                            if schema.get("function", {}).get("name") in allowed_reads
                        ]
                        settings = self.spec.values["acquisition"]
                        with self._model_context("analyzer", scope=f"{task}/{arm}") as analyzer:
                            collected = collect_base(
                                analyzer,
                                session.public_inputs,
                                corpus,
                                reads,
                                session.clarify,
                                self.counter,
                                budgets=AcquisitionBudgets(
                                    searches=settings["max_searches"],
                                    clarifications=settings["max_clarifications"],
                                    read_only_queries=settings["max_reads"],
                                    base_tokens=settings["base_token_limit"],
                                    analyzer_steps=settings.get("max_steps", 50),
                                ),
                                allowed_read_only_tool_names=frozenset(allowed_reads),
                                min_document_confidence=settings["min_document_confidence"],
                                tool_schemas=schemas,
                                input_token_limit=self.spec.values["roles"]["analyzer"][
                                    "max_input_tokens"
                                ],
                                journal=journal,
                                system_prompt=self._prompt("analyzer"),
                                action_dispatcher=getattr(session, "perform", None),
                            )
                    seal_base(root / "base", collected)
                    return collected.to_dict()

                base = FrozenBase.from_dict(
                    journal.dispatch("collect-base", {}, acquire, external=False)
                )
                seal_base(root / "base", base)
            if (root / "initial").exists():
                bundle = load_bundle(root / "initial")
            else:
                with self._model_context("generator", scope=f"{task}/{arm}") as generator:
                    bundle = generate_initial(
                        generator,
                        base.public_inputs,
                        base,
                        journal=journal,
                        tool_schemas=bank.tool_schemas,
                        artifact_dir=root / "initial",
                        seed=self.spec.values["seed"],
                        system_prompt=self._prompt("generator"),
                        token_counter=SerializedChatTokenCounter(self.counter),
                        context_window=self.spec.values["roles"]["generator"].get(
                            "context_window", 272000
                        ),
                        context_fraction=self.spec.values["roles"]["generator"].get(
                            "context_beta", 0.7
                        ),
                        reserved_output_tokens=math.floor(
                            self.spec.values["roles"]["generator"]["context_window"]
                            * self.spec.values["roles"]["generator"]["context_beta"]
                        )
                        - self.spec.values["roles"]["generator"]["max_input_tokens"],
                    )
            record = {
                "status": "CREATED",
                "base_hash": base.base_hash,
                "initial_bundle_hash": bundle.bundle_hash,
            }
        except CredentialError:
            # No request was sent (journal withdrew the record): abort this
            # invocation instead of sealing a terminal CREATION_FAILED.
            raise
        except (CreationFailure, UnknownOperation, ValueError, OSError, RuntimeError) as exc:
            if base is None and (
                isinstance(exc, BankWorkerError)
                and not exc.response_received
                or isinstance(exc, ModelClientError)
                and exc.code == "acquisition_recovery_failed"
            ):
                # The private checkpoint determines whether a lost worker reply
                # can be recovered. Do not turn this transport loss into a new
                # opening or a terminal creation result. Local replay failures
                # also leave the same private state available for recovery.
                raise
            record = {
                "status": "CREATION_FAILED",
                "reason": str(exc),
                "base_hash": None if base is None else base.base_hash,
                "initial_bundle_hash": None,
            }
        journal.dispatch("creation", {}, lambda record=record: record)

    def evolve(self, cells: tuple[tuple[str, str], ...]) -> None:
        self._validate_cells(cells)
        for task, arm in cells:
            self._evolve_cell(task, arm)
            self._halt_on_authentication(task, arm)

    def _evolve_cell(self, task: str, arm: str) -> None:
        from .evolution import EvolutionEngine, EvolutionResult
        from .verifier import SurrogateVerifier

        root, journal = self._cell(task, arm)
        self._halt_on_learning_close_failure(journal)
        creation = journal.response("creation")
        if creation["status"] != "CREATED":
            return
        base, initial = self._created(root, journal)
        if journal.completed("evolution-result"):
            result = EvolutionResult.from_dict(journal.response("evolution-result"))
        else:
            bank = self._bank(task, arm)
            from .generator import RevisionConversation

            author = self.spec.experiment == "skillsbench"
            deadline = None
            if author:
                timeout = self.spec.values["evolution"]["timeout_seconds"]
                timing = journal.dispatch(
                    "evolution-wall-clock",
                    {"timeout_seconds": timeout},
                    lambda: {"started_at": (started := time.time()), "deadline": started + timeout},
                    external=False,
                )
                deadline = timing["deadline"]
                bank.deadline = deadline
            settings = self.spec.values["roles"]["generator"]
            generator = self._model("generator", phase="revise", scope=f"{task}/{arm}")
            verifier_model = None
            if author and hasattr(generator, "request_deadline"):
                generator.request_deadline = deadline
            session_opened = False
            result = None
            try:
                with bank.evolution_session(
                    initial,
                    base.public_inputs,
                    base,
                    journal=journal,
                    workspace=root / "learning",
                    **({"deadline": deadline} if author else {}),
                ) as session:
                    session_opened = True
                    if author:
                        from .skillsbench_evolution import run_author_evolution

                        verifier_model = self._model("verifier", scope=f"{task}/{arm}")
                        if hasattr(verifier_model, "request_deadline"):
                            verifier_model.request_deadline = deadline
                        result = run_author_evolution(
                            session,
                            initial,
                            base,
                            generator,
                            verifier_model,
                            journal=journal,
                            root=root,
                            token_counter=self.counter,
                            settings=settings,
                            deadline=deadline,
                            adapter_prompt=(
                                self.spec.root / "prompts" / "skillsbench-verifier-adapter.txt"
                            ).read_text(),
                        )
                        journal.dispatch(
                            "evolution-result",
                            {
                                "initial_bundle_hash": initial.bundle_hash,
                                "base_hash": base.base_hash,
                            },
                            result.to_dict,
                            external=False,
                        )
                    else:
                        conversation = RevisionConversation()
                        options = {
                            "journal": journal,
                            "tool_schemas": bank.tool_schemas,
                            "seed": self.spec.values["seed"],
                            "system_prompt": self._prompt("generator"),
                            "token_counter": SerializedChatTokenCounter(self.counter),
                            "context_window": settings["context_window"],
                            "context_fraction": settings["context_beta"],
                            "reserved_output_tokens": math.floor(
                                settings["context_window"] * settings["context_beta"]
                            )
                            - settings["max_input_tokens"],
                            "conversation": conversation,
                            "max_turns": settings.get("max_turns", 120),
                            "timeout_seconds": self.spec.values["evolution"].get(
                                "revision_timeout_seconds", 3600
                            ),
                            "deadline": deadline,
                        }
                        verifier_model = self._model("verifier", scope=f"{task}/{arm}")
                        verifier = SurrogateVerifier(
                            verifier_model,
                            self._runner(),
                            journal=journal,
                            system_prompt=self._prompt("verifier"),
                            max_output_tokens=self.spec.values["roles"]["verifier"][
                                "max_output_tokens"
                            ],
                            seed=self.spec.values["seed"],
                            max_episodes=self.spec.values["roles"]["verifier"]["max_turns"],
                            diagnosis_episodes=self.spec.values["roles"]["verifier"][
                                "diagnosis_turns"
                            ],
                        )

                        def initial_execution(
                            bundle: Any, inputs: Any, frozen: Any, **kwargs: Any
                        ) -> Any:
                            return execute_initial(
                                generator,
                                bundle,
                                inputs,
                                frozen,
                                session=session,
                                **options,
                                **kwargs,
                            )

                        def revision(
                            previous: Any,
                            inputs: Any,
                            frozen: Any,
                            report: Any,
                            *,
                            operation_id: str,
                            **kwargs: Any,
                        ) -> Any:
                            return revise(
                                generator,
                                previous,
                                inputs,
                                frozen,
                                report,
                                session=session,
                                operation_id=operation_id,
                                artifact_dir=root / "revisions" / operation_id,
                                **options,
                                **kwargs,
                            )

                        engine = EvolutionEngine(
                            execute_initial=initial_execution,
                            oracle=bank.oracle,
                            verifier=verifier,
                            revise=revision,
                            journal=journal,
                            max_revisions=self.spec.values["evolution"]["max_revisions"],
                            max_oracles=self.spec.values["evolution"]["max_oracles"],
                            max_oracle_errors=self.spec.values["evolution"].get(
                                "max_oracle_errors", 5
                            ),
                        )
                        result = engine.run(base.public_inputs, base, initial)
            except (OSError, ValueError, RuntimeError) as exc:
                stage = (
                    "open" if not session_opened else "close" if result is not None else "active"
                )
                failures = [
                    json.loads(path.read_text())["operation_id"]
                    for path in journal.root.glob("*/request.json")
                    if json.loads(path.read_text())["operation_id"].startswith(
                        "learning-environment-failure-"
                    )
                ]
                record = {
                    "status": "NOT_MEASURED",
                    "index": len(failures),
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "reason": getattr(exc, "reason", None) or type(exc).__name__,
                }
                journal.dispatch(
                    f"learning-environment-failure-{len(failures)}",
                    {"initial_bundle_hash": initial.bundle_hash, "base_hash": base.base_hash},
                    lambda: record,
                    external=False,
                )
                raise
            finally:
                try:
                    self._close_model(verifier_model)
                finally:
                    self._close_model(generator)
        for bundle in result.versions:
            seal_bundle(root / "versions" / bundle.bundle_hash, bundle)

    def evaluate(self, cells: tuple[tuple[str, str], ...]) -> None:
        self._validate_cells(cells)
        from .evaluation import evaluate_versions
        from .evolution import EvolutionResult

        for task, arm in cells:
            root, journal = self._cell(task, arm)
            self._halt_on_learning_close_failure(journal)
            creation = journal.response("creation")
            if creation["status"] != "CREATED":
                continue
            _, initial = self._created(root, journal)
            learning_stop = None
            if journal.completed("evolution-result"):
                evolution = EvolutionResult.from_dict(journal.response("evolution-result"))
                versions = evolution.versions
                learning_stop = evolution.stop_reason
            else:
                versions = (initial,)
            if (
                self.spec.experiment == "skillsbench"
                and learning_stop
                and (
                    learning_stop.endswith("result_unknown")
                    or learning_stop in {"authentication_failed", "cleanup_failed"}
                )
            ):
                from .evaluation import not_measured

                for bundle in versions:
                    operation = f"evaluation-{bundle.bundle_hash}"
                    if not journal.dispatched(operation):
                        missing = journal.dispatch(
                            operation,
                            {
                                "bundle_hash": bundle.bundle_hash,
                                "blocked_by_learning": learning_stop,
                            },
                            lambda bundle=bundle, reason=learning_stop: not_measured(
                                bundle.bundle_hash, reason
                            ),
                            external=False,
                        )
                        journal.record_result(operation, missing)
                continue
            bank = self._bank(task, arm)
            for bundle in versions:
                sealed = (
                    root / "initial"
                    if bundle.parent_hash is None
                    else root / "versions" / bundle.bundle_hash
                )
                load_bundle(sealed)
            evaluate_versions(versions, bank.evaluate, journal=journal)
            self._halt_on_authentication(task, arm)

    def evaluate_no_skill(self, cells: tuple[tuple[str, str], ...]) -> None:
        """Run the SkillsBench control without acquisition, generation or evolution."""
        from .evaluation import evaluate_no_skill

        self._require_codex_controls(cells, benign_only=True)
        for task, arm in cells:
            if (task, arm) in self._historical_authentication_failures:
                continue
            _, journal = self._cell(task, arm)
            self._halt_on_learning_close_failure(journal)
            evaluate_no_skill(self._bank(task, arm).evaluate_no_skill, journal=journal)
            self._halt_on_authentication(task, arm)

    def _require_codex_controls(
        self, cells: tuple[tuple[str, str], ...], *, benign_only: bool = False
    ) -> None:
        self._validate_cells(cells)
        if self.spec.experiment != "skillsbench":
            raise ValueError("control evaluation requires SkillsBench tasks")
        if benign_only and any(arm != "benign" for _, arm in cells):
            raise ValueError("NoSkill is measured once on the shared benign environment")
        if (
            self.spec.values["runtime"].get("executor") != "author-codex"
            or self.runtime != "docker"
        ):
            raise ValueError("control evaluation requires the author Codex Docker executor")

    def evaluate_imported(self, cells: tuple[tuple[str, str], ...], source_run: Path) -> None:
        """Rescore immutable packages in a new run; never reuse source measurements."""
        from .evaluation import evaluate_versions
        from .evolution import EvolutionResult

        self._require_codex_controls(cells)
        source_run = Path(source_run).resolve()
        if source_run == self.root.resolve():
            raise ValueError("imported evaluations require a separate source run")
        source_identity = None
        source_trial = None
        for task, arm in cells:
            if (task, arm) in self._historical_authentication_failures:
                continue
            root, journal = self._cell(task, arm)
            self._halt_on_learning_close_failure(journal)
            if journal.dispatched("creation"):
                raise ValueError("cannot import versions into a creation checkpoint")
            if journal.completed("imported-versions"):
                imported = journal.response("imported-versions")
                if imported["source_run"] != str(source_run):
                    raise ValueError("imported source run differs from the sealed manifest")
                versions = self._imported_bundles(root, imported)
                evaluate_versions(versions, self._bank(task, arm).evaluate, journal=journal)
                self._halt_on_authentication(task, arm)
                continue
            if source_identity is None:
                source_identity = json.loads((source_run / "journal" / "identity.json").read_text())
                source_trial = json.loads((source_run / "journal" / "trial.json").read_text())[
                    "trial_id"
                ]
                if source_identity["identity"].get("experiment") != "skillsbench":
                    raise ValueError("imported source must be a SkillsBench run")
            source_cell = source_run / "cells" / task / arm
            cell_identity = json.loads((source_cell / "journal" / "identity.json").read_text())
            binding = cell_identity["identity"]
            if binding != {
                **source_identity["identity"],
                "task": task,
                "arm": arm,
                "trial_id": source_trial,
            }:
                raise ValueError("imported source task or trial identity differs")
            source = Journal(source_cell / "journal", identity=binding)
            creation = source.response("creation")
            initial = load_bundle(source_cell / "initial")
            if creation.get("status") != "CREATED" or (
                initial.bundle_hash != creation.get("initial_bundle_hash")
            ):
                raise ValueError("imported creation does not match the sealed package")
            result = (
                EvolutionResult.from_dict(source.response("evolution-result"))
                if (source.completed("evolution-result"))
                else None
            )
            versions = result.versions if result is not None else (initial,)
            final_hash = result.final_bundle_hash if result is not None else initial.bundle_hash
            if (
                not versions
                or versions[0].bundle_hash != initial.bundle_hash
                or len({bundle.bundle_hash for bundle in versions}) != len(versions)
                or final_hash not in {bundle.bundle_hash for bundle in versions}
            ):
                raise ValueError("imported content-version lineage is invalid")
            preceding_hashes: set[str] = set()
            for index, bundle in enumerate(versions):
                if (index == 0 and bundle.parent_hash is not None) or (
                    index > 0 and bundle.parent_hash not in preceding_hashes
                ):
                    raise ValueError("imported parent hash differs")
                sealed = (
                    source_cell / "initial"
                    if index == 0
                    else (source_cell / "versions" / bundle.bundle_hash)
                )
                if load_bundle(sealed).to_dict() != bundle.to_dict():
                    raise ValueError("imported package differs from the source evolution record")
                preceding_hashes.add(bundle.bundle_hash)
            manifest = {
                "source": "imported_frozen_packages",
                "source_run": str(source_run),
                "source_identity_hash": digest(source_identity),
                "source_trial_id": source_trial,
                "source_stop_reason": result.stop_reason
                if result
                else (
                    "evolution_result_unknown"
                    if source.dispatched("evolution-result")
                    else "evolution_not_started"
                ),
                "source_revision_attempts": result.revision_attempts if result else 0,
                "source_oracle_calls": result.oracle_calls if result else 0,
                "task_id": task,
                "condition": arm,
                "versions": [
                    {
                        "version": index,
                        "bundle_hash": bundle.bundle_hash,
                        "parent_hash": bundle.parent_hash,
                    }
                    for index, bundle in enumerate(versions)
                ],
                "initial_bundle_hash": initial.bundle_hash,
                "final_bundle_hash": final_hash,
                "final_bundle_ref": dict(result.final_bundle_ref)
                if result is not None and result.final_bundle_ref is not None
                else None,
            }
            source_close_failure = self._learning_close_failure(source)
            if source_close_failure is not None:
                manifest["source_evolution_stop_reason"] = manifest["source_stop_reason"]
                manifest["source_stop_reason"] = "learning_environment_close_failed"
                manifest["source_learning_environment_failure"] = source_close_failure

            def import_packages(
                versions: Any = versions, root: Path = root, manifest: Any = manifest
            ) -> dict[str, Any]:
                for bundle in versions:
                    seal_bundle(root / "imported" / bundle.bundle_hash, bundle)
                return manifest

            journal.dispatch("imported-versions", manifest, import_packages, external=False)
            evaluate_versions(versions, self._bank(task, arm).evaluate, journal=journal)
            self._halt_on_authentication(task, arm)

    def _imported_bundles(self, root: Path, manifest: dict[str, Any]) -> tuple[Any, ...]:
        versions = tuple(
            load_bundle(root / "imported" / item["bundle_hash"]) for item in manifest["versions"]
        )
        for item, bundle in zip(manifest["versions"], versions, strict=True):
            if (bundle.bundle_hash, bundle.parent_hash) != (
                item["bundle_hash"],
                item["parent_hash"],
            ):
                raise ValueError("imported sealed package differs from its import manifest")
        return versions

    def report(self) -> dict[str, Any]:
        from .evaluation import not_measured, report_cases
        from .evolution import EvolutionResult

        skillsbench_v8 = self.spec.namespace == "skillsbench.skill-evolution.v8"
        if skillsbench_v8:
            from .skillsbench_attack import (
                ACQUISITION_STAGES,
                acquisition_exposure_not_measured,
                acquisition_payload_exposure,
            )

        cases: list[dict[str, Any]] = []
        for task, arm in self.spec.cells:
            directory = self.root / "cells" / task / arm
            case: dict[str, Any] = {
                "task_id": task,
                "condition": arm,
                "status": "NOT_MEASURED",
                "versions": [],
                "evaluations": {},
                "stop_reason": "not_started",
            }
            if skillsbench_v8:
                case["acquisition"] = {
                    "payload_exposure": acquisition_exposure_not_measured("acquisition_not_started")
                }
            if (directory / "journal").exists():
                _, journal = self._cell(task, arm)
                base = None
                if journal.dispatched("evaluation-no-skill"):
                    case["no_skill_evaluation"] = journal.result("evaluation-no-skill") or {
                        **not_measured(
                            reason="result_unknown"
                            if not journal.completed("evaluation-no-skill")
                            else "evaluation_not_processed"
                        ),
                        "baseline": "no_skill",
                    }
                if journal.completed("collect-base"):
                    base = self._collected_base(directory, journal)
                    case["acquisition"] = {
                        "base_hash": base.base_hash,
                        "selected_documents": len(base.documents),
                        "base_tokens": base.token_count,
                        "stop_reason": base.stop_reason,
                    }
                    if journal.completed("acquisition-summary"):
                        summary = journal.response("acquisition-summary")
                        case["acquisition"].update(
                            {
                                name: summary[name]
                                for name in (
                                    "stop_detail",
                                    "counters",
                                    "unreviewed_document_ids",
                                    "unreviewable_document_ids",
                                )
                            }
                        )
                if skillsbench_v8 and journal.dispatched("collect-base"):
                    case["acquisition"]["payload_exposure"] = (
                        acquisition_payload_exposure(self.spec.root, base, journal)
                        if journal.completed("retrieval-corpus-contract")
                        else acquisition_exposure_not_measured("retrieval_contract_not_recorded")
                    )
                if journal.completed("imported-versions"):
                    imported = journal.response("imported-versions")
                    imported_bundles = self._imported_bundles(directory, imported)
                    for bundle in imported_bundles:
                        operation = f"evaluation-{bundle.bundle_hash}"
                        case["evaluations"][bundle.bundle_hash] = journal.result(operation) or (
                            not_measured(
                                bundle.bundle_hash,
                                "result_unknown"
                                if journal.dispatched(operation)
                                and not journal.completed(operation)
                                else "stage_not_executed",
                            )
                        )
                    case.update(
                        status="IMPORTED_EVALUATION",
                        versions=imported["versions"],
                        initial_bundle_hash=imported["initial_bundle_hash"],
                        final_bundle_hash=imported["final_bundle_hash"],
                        final_bundle_ref=imported.get("final_bundle_ref"),
                        stop_reason="imported_evaluation",
                        evaluation_source=imported["source"],
                        evaluation_import=imported,
                    )
                    static_persistence = self._static_persistence(arm, imported_bundles)
                    if static_persistence:
                        case["attack_static_persistence"] = static_persistence
                if journal.completed("creation"):
                    creation = journal.response("creation")
                    case["status"] = creation["status"]
                    case["creation"] = creation
                    if creation["status"] == "CREATED":
                        base, initial = self._created(directory, journal)
                        versions = (initial,)
                        final_hash = initial.bundle_hash
                        final_ref = None
                        case["stop_reason"] = "evolution_not_started"
                        if journal.completed("evolution-result"):
                            result = EvolutionResult.from_dict(journal.response("evolution-result"))
                            versions = result.versions
                            final_hash = result.final_bundle_hash
                            final_ref = (
                                dict(result.final_bundle_ref)
                                if result.final_bundle_ref is not None
                                else None
                            )
                            case.update(
                                stop_reason=result.stop_reason,
                                revision_attempts=result.revision_attempts,
                                oracle_calls=result.oracle_calls,
                                oracle_attempts=result.oracle_calls + len(result.oracle_failures),
                                oracle_failures=list(result.oracle_failures),
                                attempts=list(result.attempts),
                                stage_failures=thaw_json(result.stage_failures),
                                author_counters=thaw_json(result.author_counters),
                                oracle_history=thaw_json(result.oracle_history),
                                best_oracle_ref=thaw_json(result.best_oracle_ref),
                                author_terminal_result=thaw_json(result.author_terminal_result),
                                selection_reason=result.selection_reason,
                                interventions=thaw_json(result.interventions),
                                best_snapshot=thaw_json(result.best_snapshot),
                                verifications=[
                                    {
                                        **{
                                            key: check[key]
                                            for key in (
                                                "submission_hash",
                                                "trace_hash",
                                                "execution_id",
                                                "operation_cursor",
                                                "initial",
                                                "parent_hash",
                                            )
                                            if key in check
                                        },
                                        **{
                                            key: check[key]
                                            for key in (
                                                "bundle_hash",
                                                "test_version",
                                                "test_hash",
                                                "passed",
                                                "pass_rate",
                                                "failure",
                                                "program_error",
                                                "diagnosis",
                                                "recommendations",
                                                "results",
                                            )
                                        },
                                        **{
                                            key: check[key]
                                            for key in (
                                                "test_runs",
                                                "stage_failures",
                                                "author_result",
                                            )
                                            if key in check
                                        },
                                    }
                                    for check in result.verifications
                                ],
                            )
                        environment_failures = [
                            journal.response(envelope["operation_id"])
                            for path in journal.root.glob("*/request.json")
                            if (envelope := json.loads(path.read_text()))[
                                "operation_id"
                            ].startswith("learning-environment-failure-")
                            and journal.completed(envelope["operation_id"])
                        ]
                        if environment_failures:
                            failure = max(environment_failures, key=lambda item: item["index"])
                            if (
                                not journal.completed("evolution-result")
                                or failure["stage"] == "close"
                            ):
                                case["learning_environment_failure"] = failure
                                case["evolution_stop_reason"] = case["stop_reason"]
                                case["stop_reason"] = (
                                    f"learning_environment_{failure['stage']}_failed"
                                )
                        case["versions"] = [
                            {"bundle_hash": bundle.bundle_hash} for bundle in versions
                        ]
                        case["final_bundle_hash"] = final_hash
                        case["final_bundle_ref"] = final_ref
                        case["initial_bundle_hash"] = initial.bundle_hash
                        case["frozen_control_hash"] = (
                            initial.bundle_hash if arm != "benign" else None
                        )
                        case["evolution"] = {
                            "final_bundle_hash": final_hash,
                            "final_bundle_ref": final_ref,
                            "stop_reason": case["stop_reason"],
                        }
                        static_persistence = self._static_persistence(arm, versions)
                        if static_persistence:
                            case["attack_static_persistence"] = static_persistence
                        for bundle in versions:
                            operation = f"evaluation-{bundle.bundle_hash}"
                            pending = journal.dispatched(operation) and not journal.completed(
                                operation
                            )
                            reason = "stage_not_executed"
                            if pending:
                                reason = (
                                    "authentication_failed"
                                    if journal.authentication_failure() is not None
                                    else "result_unknown"
                                )
                            measurement = journal.result(operation) or not_measured(
                                bundle.bundle_hash, reason
                            )
                            case["evaluations"][bundle.bundle_hash] = measurement
                        evidence_path = self._public_audit(directory, journal, base)
                        case["public_audit"] = str(evidence_path.relative_to(self.root))
                        evidence = json.loads(evidence_path.read_text())
                        case["learning_execution_count"] = evidence["learning_execution_count"]
                        case["terminal_calls"] = len(evidence["terminal_operations"])
                        case["submission_count"] = len(evidence["submissions"])
                        case["model_post_dispatches"] = sum(
                            item["status"] != "NOT_SENT" for item in evidence["model_requests"]
                        )
                        case["learning_operations_unknown"] = sum(
                            item["status"] == "UNKNOWN"
                            for item in (
                                *evidence["terminal_operations"],
                                *evidence["bank_actions"],
                            )
                        )
                        if self.spec.experiment == "tau" and any(
                            item["status"] == "MEASURED" for item in case["evaluations"].values()
                        ):
                            case["gold_coverage"] = self._gold_coverage(task, base, journal)
                    else:
                        case["stop_reason"] = creation["reason"]
                        case["creation_failure"] = creation["reason"]
                authentication = journal.authentication_failure()
                if authentication is not None:
                    case["authentication_status"] = authentication
                    case["stop_reason"] = "authentication_failed"
            cases.append(case)
        if self.spec.namespace == "skillsbench.skill-evolution.v8":
            baseline_tasks = {
                case["task_id"]
                for case in cases
                if case["condition"] == "benign" and "no_skill_evaluation" in case
            }
            for case in cases:
                if case["task_id"] in baseline_tasks:
                    case["no_skill_evaluation_ref"] = {
                        "task_id": case["task_id"],
                        "condition": "benign",
                    }
        report = report_cases(
            cases,
            task_denominator=len(self.spec.tasks),
            conditions=tuple(self.spec.values["matrix"]["arms"]),
        )
        report["namespace"] = self.spec.namespace
        report["identity"] = self.experiment_identity
        report["trial_id"] = self.trial_id
        report["experiment"] = self.spec.experiment
        report["protocol"] = self.spec.namespace
        report["run_mode"] = (
            "single-task-demo"
            if self.demo
            else "workspace"
            if self.runtime == "workspace"
            else "formal"
        )
        report["formal_matrix_result"] = self.runtime == "docker" and any(
            measurement.get("utility_status", measurement.get("status")) == "MEASURED"
            or measurement.get("asr_status") == "MEASURED"
            for case in cases
            for measurement in (
                *case["evaluations"].values(),
                case.get("no_skill_evaluation") or {},
            )
            if measurement
        )
        report["execution"] = {
            **self.execution,
            "formal_matrix_result": report["formal_matrix_result"],
        }
        report["cases"] = cases
        if skillsbench_v8:
            denominator = len(self.spec.tasks)
            report["acquisition_exposure_coverage"] = [
                {
                    "arm": arm,
                    "stage": stage,
                    "measured": measured,
                    "missing": denominator - measured,
                    "denominator": denominator,
                }
                for arm in self.spec.values["matrix"]["arms"]
                for stage in ACQUISITION_STAGES
                for measured in (
                    sum(
                        ((case.get("acquisition") or {}).get("payload_exposure") or {})
                        .get("stages", {})
                        .get(stage, {})
                        .get("status")
                        == "MEASURED"
                        for case in cases
                        if case["condition"] == arm
                    ),
                )
            ]
        report["usage"] = self._usage_summary()
        atomic_json(self.root / "report.json", report)
        self._write_report_md(report)
        return report

    def _public_audit(self, directory: Path, journal: Journal, base: FrozenBase) -> Path:
        """Export public evidence without model chats or private oracle/evaluator output."""
        from .artifacts import EvolutionSubmission

        submissions, terminal_operations, bank_actions, verifier_operations = [], [], [], []
        model_requests = []
        execution_ids: set[str] = set()
        execution_count = 0
        for request in sorted(journal.root.glob("*/request.json")):
            envelope = json.loads(request.read_text())
            operation = envelope["operation_id"]
            payload = envelope["payload"]
            name = payload.get("name")
            if payload.get("delivery_policy") == "single_post":
                model_requests.append(
                    {
                        "operation_id": operation,
                        "role": (payload.get("inputs") or {}).get("role"),
                        "status": journal.status(operation),
                    }
                )
            if re.fullmatch(
                r"evolution-turn-\d+-(?:suite|escalate|verify)-author-(?:generation|verification)-exec-\d+",
                operation,
            ):
                item = {
                    "operation_id": operation,
                    "status": journal.status(operation),
                    "command": payload["command"],
                    "role": "author_verifier",
                }
                if journal.completed(operation):
                    response = journal.response(operation)
                    item.update(
                        return_code=response["return_code"],
                        failure=response["failure"],
                        stdout_hash=digest(response["stdout"]),
                        stderr_hash=digest(response["stderr"]),
                    )
                verifier_operations.append(item)
                continue
            if name is not None and re.fullmatch(
                r"evolution-turn-\d+-(?:suite|escalate|verify-(?:diagnosis|repair))"
                r"-turn-\d+-tool-\d+",
                operation,
            ):
                record = {
                    "operation_id": operation,
                    "status": journal.status(operation),
                    "tool": name,
                }
                if journal.completed(operation):
                    response = journal.response(operation)
                    record["program"] = response["program"]
                    record["workspace_hash"] = response["snapshot"]["workspace_hash"]
                    snapshot = response["snapshot"]
                    if "files" in snapshot:
                        record["test_files"] = snapshot["files"]
                    record.update(
                        {
                            key: snapshot[key]
                            for key in ("manifest", "invalid_package")
                            if key in snapshot
                        }
                    )
                verifier_operations.append(record)
                continue
            if name is None and operation.endswith("/start") and journal.completed(operation):
                start = journal.response(operation)
                state = start.get("learning_execution_state", {})
                execution_count = max(execution_count, state.get("execution_count", 0))
                if state.get("execution_id"):
                    execution_ids.add(state["execution_id"])
            if name == "submit_revision" and journal.completed(operation):
                response = journal.response(operation)
                if "submission" not in response:
                    continue
                submitted = EvolutionSubmission.from_dict(response["submission"])
                execution_ids.add(submitted.execution_id)
                trace = submitted.to_dict()["public_trace"]
                trace.pop("public_artifacts_dir", None)
                submissions.append(
                    {
                        "operation_id": operation,
                        "submission_hash": submitted.submission_hash,
                        "trace_hash": submitted.trace_hash,
                        "bundle_hash": submitted.bundle.bundle_hash,
                        "parent_hash": submitted.bundle.parent_hash,
                        "execution_id": submitted.execution_id,
                        "operation_cursor": submitted.operation_cursor,
                        "initial": submitted.initial,
                        "public_trace": trace,
                    }
                )
            elif name is not None:
                record = {
                    "operation_id": operation,
                    "status": journal.status(operation),
                    "tool": name,
                }
                if journal.completed(operation):
                    result = journal.response(operation).get("result", {})
                    state = result.get("state", {})
                    if state.get("execution_id"):
                        execution_ids.add(state["execution_id"])
                    execution_count = max(execution_count, state.get("execution_count", 0))
                    record.update(
                        {key: result[key] for key in ("exit_code", "failure") if key in result}
                    )
                (terminal_operations if name == "terminal" else bank_actions).append(record)
        checks = []
        stage_failures = []
        submission_order = {}
        if journal.completed("evolution-result"):
            evolution = journal.response("evolution-result")
            checks = evolution["verifications"]
            stage_failures = evolution.get("stage_failures", [])
            submission_order = {
                item["submission_hash"]: index
                for index, item in enumerate(evolution.get("submissions", ()))
            }
        submissions.sort(
            key=lambda item: (
                submission_order.get(item["submission_hash"], math.inf),
                not item["initial"],
                item["operation_cursor"],
            )
        )
        path = directory / "public-audit.json"
        atomic_json(
            path,
            {
                "trial_id": self.trial_id,
                "frozen_base": base.to_dict(),
                "acquisition": journal.response("acquisition-summary")
                if journal.completed("acquisition-summary")
                else None,
                "submissions": submissions,
                "learning_execution_count": max(execution_count, len(execution_ids)),
                "terminal_operations": terminal_operations,
                "bank_actions": bank_actions,
                "verifier_operations": verifier_operations,
                "model_requests": model_requests,
                "verifications": checks,
                "stage_failures": stage_failures,
            },
        )
        return path

    def _usage_summary(self) -> dict[str, Any]:
        roles: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
        )
        path = self.root / "usage.jsonl"
        seen: dict[str, Any] = {}

        def account(role: str, usage: dict[str, Any], key: str | None = None) -> None:
            item = {"role": role, "usage": usage}
            if key is not None:
                if key in seen:
                    if seen[key] != item:
                        raise ValueError("usage_for_same_operation_differs")
                    return
                seen[key] = item
            row = roles[role]
            row["requests"] += 1
            row["input_tokens"] += usage.get("input_tokens", usage.get("prompt_tokens", 0))
            row["output_tokens"] += usage.get("output_tokens", usage.get("completion_tokens", 0))
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens")
            row["cached_input_tokens"] = (
                row["cached_input_tokens"] + cached
                if row["cached_input_tokens"] is not None and cached is not None
                else None
            )

        for line in path.read_text().splitlines() if path.exists() else ():
            item = json.loads(line)
            account(item["role"], item["usage"], item.get("operation_key"))
        delivery = {
            status: 0 for status in ("NOT_SENT", "RECEIVED_INVALID", "COMPLETED", "UNKNOWN")
        }
        journal_roots = [
            self.root / "journal",
            *self.root.glob("cells/*/*/journal"),
            self.root / "private" / "bank-models",
            self.root / "private" / "skillsbench-models",
        ]
        counted_requests: set[Path] = set()
        policies: dict[str, int] = defaultdict(int)
        for request in (path for root in journal_roots for path in root.rglob("request.json")):
            policy = json.loads(request.read_text()).get("payload", {}).get("delivery_policy")
            if not isinstance(policy, str) or not policy:
                continue
            policies[policy] += 1
            state = json.loads((request.parent / "state.json").read_text())["status"]
            if (request.parent / "response.json").exists():
                state = "COMPLETED"
            delivery[state] += 1
            counted_requests.add(request.resolve())
        # Native sidecar statistics duplicate these sealed provider responses. Count
        # each journal operation once, including compaction/model calls within an episode.
        native_root = self.root / "private" / "skillsbench-models"
        for identity_path in native_root.glob("*/*/provider/identity.json"):
            identity = json.loads(identity_path.read_text())["identity"]
            if identity.get("executor", {}).get("framework") != "author-codex":
                continue
            journal = Journal(identity_path.parent, identity=identity)
            for request_path in journal.root.glob("*/request.json"):
                request = json.loads(request_path.read_text())
                operation = request["operation_id"]
                state = journal.status(operation)
                if request_path.resolve() not in counted_requests:
                    delivery[state] += 1
                    policy = request.get("payload", {}).get("delivery_policy") or "native_provider"
                    policies[policy] += 1
                    counted_requests.add(request_path.resolve())
                if state == "COMPLETED":
                    usage = journal.response(operation)["response"]["usage"]
                    key = digest(
                        {"journal": str(journal.root.resolve()), "operation_id": operation}
                    )
                    account("execution", usage, key)
        return {
            "status": "MEASURED" if roles else "NOT_MEASURED",
            "basis": "provider_response_usage; successful responses only",
            "roles": dict(roles),
            "model_request_states": delivery,
            "delivery_policies": dict(policies),
            "http_posts": {
                "status": "NOT_MEASURED",
                "count": None,
                "reason": "journal counts logical operations, not individual transport attempts",
            },
            "dispatched_model_requests": sum(
                count for state, count in delivery.items() if state != "NOT_SENT"
            ),
            "unknown_requests_may_be_billed": delivery["UNKNOWN"],
            "total": {
                name: (
                    sum(row[name] for row in roles.values())
                    if all(row[name] is not None for row in roles.values())
                    else None
                )
                for name in ("requests", "input_tokens", "output_tokens", "cached_input_tokens")
            },
            "cost_usd": None,
            "cost_status": "NOT_MEASURED",
            "cost_reason": "provider responses do not include billing charges",
        }

    def _gold_coverage(self, task: str, base: FrozenBase, journal: Journal) -> dict[str, Any]:
        # Post-evaluation researcher output only; never part of a role request.
        path = self.spec.upstream / "data/tau2/domains/banking_knowledge/tasks" / f"{task}.json"
        required = json.loads(path.read_text())["required_documents"]
        gold = set(required)
        returned: set[str] = set()
        for request_path in journal.root.glob("*/request.json"):
            request = json.loads(request_path.read_text())
            operation = request["operation_id"]
            if not operation.startswith("acquisition/search/") or not journal.completed(operation):
                continue
            response = journal.response(operation)
            if response.get("status") != "ok":
                continue
            result = response["result"]
            documents = result.get("results", []) if isinstance(result, dict) else result
            returned.update(
                item.get("document_id", item.get("page_id", item.get("id"))) for item in documents
            )
        selected = {item["document_id"] for item in base.documents}
        return {
            "status": "MEASURED",
            "basis": "posthoc required_documents ID coverage",
            "gold_count": len(gold),
            "returned_count": len(returned),
            "returned_gold_count": len(gold & returned),
            "selected_gold_count": len(gold & selected),
            "returned_recall": len(gold & returned) / len(gold) if gold else None,
            "base_recall": len(gold & selected) / len(gold) if gold else None,
            "missing_from_base": sorted(gold - selected),
        }

    def _validate_cells(self, cells: tuple[tuple[str, str], ...]) -> None:
        if self.demo and cells != ((self.demo_task, "benign"),):
            raise ValueError("demo permits exactly its fixed single benign task")

    def _write_report_md(self, report: dict[str, Any]) -> None:
        import json

        skillsbench_v8 = (
            self.spec.experiment == "skillsbench"
            and report.get("namespace") == "skillsbench.skill-evolution.v8"
        )
        lines = [
            f"# {self.spec.experiment} run report",
            "",
            f"Protocol: `{report['namespace']}`",
            "",
            f"End-to-end rates use the full {len(self.spec.tasks)}-task arm denominator. "
            "Measured means use only valid measurements.",
            "Until all tasks are measured, fixed-denominator rates report observed successes; "
            "they are not complete matrix results.",
            "Missing measurements remain null in JSON and NOT_MEASURED here.",
            "The S0 evaluation also represents the frozen control; it is not another sample.",
        ]
        if skillsbench_v8:
            lines.extend(
                [
                    "Utility and ASR have independent statuses and measured-mean denominators.",
                ]
            )
        if self.execution.get("backend") == "workspace":
            lines[4:4] = [
                "Local workspace experiment: fresh episode directories and locked dependencies. "
                "Bubblewrap restricts file/network access; aggregate cgroup limits and "
                "equivalence to the original Docker task environment are not claimed.",
                "",
            ]
        elif self.demo:
            lines[4:4] = [
                "Single-task Bubblewrap demonstration; formal_matrix_result=false. "
                "Aggregate cgroup CPU/memory/PID limits are not enforced.",
                "",
            ]

        def cell(value: Any) -> str:
            if value is None:
                return "NOT_MEASURED"
            if isinstance(value, float):
                return f"{value:.6g}"
            return str(value).replace("|", "\\|").replace("\n", " ")

        def table(title: str, columns: tuple[str, ...], rows: Any) -> None:
            if self.spec.experiment == "skillsbench" and not skillsbench_v8:
                keep = [index for index, name in enumerate(columns) if "ASR" not in name]
                columns = tuple(columns[index] for index in keep)
                rows = (tuple(row[index] for index in keep) for row in rows)
            lines.extend(["", f"## {title}", "", "| " + " | ".join(columns) + " |"])
            lines.append("| " + " | ".join("---" for _ in columns) + " |")
            lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)

        cases = {(case["task_id"], case["condition"]): case for case in report["cases"]}

        def version_role(row: dict[str, Any]) -> str:
            case = cases[(row["task_id"], row["condition"])]
            label = f"S{row['version']}"
            return (
                f"{label} / final" if row["bundle_hash"] == case.get("final_bundle_hash") else label
            )

        def official(row: dict[str, Any]) -> dict[str, Any]:
            value = (row.get("metrics") or {}).get("reward_info")
            return value if isinstance(value, dict) else {}

        def static_persistence(row: dict[str, Any]) -> dict[str, Any]:
            value = row.get("attack_static_persistence")
            if not isinstance(value, dict):
                value = (row.get("metrics") or {}).get("attack_static_persistence")
            return value if isinstance(value, dict) else {}

        def check_count(value: Any) -> str | None:
            if not isinstance(value, list):
                return None
            if not value:
                return "NO_CHECKS"
            if any(
                not isinstance(item, dict) or type(item.get("met")) is not bool for item in value
            ):
                return None
            return f"{sum(item['met'] for item in value)}/{len(value)}"

        def phase_failures(case: dict[str, Any]) -> list[dict[str, Any]]:
            failures = list(case.get("stage_failures", ()))
            for check in case.get("verifications", ()):
                for failure in check.get("stage_failures", ()):
                    if failure not in failures:
                        failures.append(failure)
            for failure in tuple(failures):
                for rejection in failure.get("rejections", ()):
                    if rejection not in failures:
                        failures.append(rejection)
            return failures

        if skillsbench_v8:
            arm_columns = (
                "Condition",
                "Arm",
                "Denominator",
                "Chains",
                "Utility measured",
                "Utility missing",
                "Utility mean",
                "ASR measured",
                "ASR missing",
                "ASR N/A",
                "ASR mean",
                "End-to-end utility",
                "Task pass rate",
                "Observed ASR / task",
            )
            arm_keys = (
                "condition",
                "arm",
                "task_denominator",
                "actual_chains",
                "utility_measured_count",
                "utility_not_measured_count",
                "measured_utility",
                "asr_measured_count",
                "asr_not_measured_count",
                "asr_not_applicable_count",
                "measured_asr",
                "end_to_end_utility",
                "task_pass_rate",
                "observed_attack_successes_per_task",
            )
            round_columns = (
                "Condition",
                "Version",
                "Chains",
                "Utility measured",
                "Utility missing",
                "Utility mean",
                "ASR measured",
                "ASR missing",
                "ASR N/A",
                "ASR mean",
                "Stops",
            )
            round_keys = (
                "condition",
                "version",
                "actual_chains",
                "utility_measured_count",
                "utility_not_measured_count",
                "measured_utility",
                "asr_measured_count",
                "asr_not_measured_count",
                "asr_not_applicable_count",
                "measured_asr",
                "stop_counts",
            )
        else:
            arm_columns = (
                "Condition",
                "Arm",
                "Denominator",
                "Chains",
                "Measured",
                "Utility mean",
                "ASR mean",
                "End-to-end utility",
                "Task pass rate",
                "Observed ASR / task",
            )
            arm_keys = (
                "condition",
                "arm",
                "task_denominator",
                "actual_chains",
                "measured_count",
                "measured_utility",
                "measured_asr",
                "end_to_end_utility",
                "task_pass_rate",
                "observed_attack_successes_per_task",
            )
            round_columns = (
                "Condition",
                "Version",
                "Chains",
                "Measured",
                "Utility mean",
                "ASR mean",
                "Stops",
            )
            round_keys = (
                "condition",
                "version",
                "actual_chains",
                "measured_count",
                "measured_utility",
                "measured_asr",
                "stop_counts",
            )
        table(
            "Final arms",
            arm_columns,
            (tuple(row[key] for key in arm_keys) for row in report["arms"]),
        )
        table(
            "Actual content versions",
            round_columns,
            (tuple(row[key] for key in round_keys) for row in report["rounds"]),
        )
        table(
            "Task stops",
            (
                "Task",
                "Condition",
                "Stop",
                "Versions",
                "Revision attempts",
                "Oracle calls",
                "Learning executions",
                "Terminal calls",
                "Submissions",
                "Final hash",
            ),
            (
                (
                    case["task_id"],
                    case["condition"],
                    case["stop_reason"],
                    len(case["versions"]),
                    case.get("revision_attempts", 0),
                    case.get("oracle_calls", 0),
                    case.get("learning_execution_count", 0),
                    case.get("terminal_calls", 0),
                    case.get("submission_count", 0),
                    case.get("final_bundle_hash"),
                )
                for case in report["cases"]
            ),
        )
        table(
            "Stage failures",
            ("Task", "Condition", "Stage", "Operation", "Exception", "Reason", "Detail"),
            (
                (
                    case["task_id"],
                    case["condition"],
                    failure["stage"],
                    failure["operation_id"],
                    failure["exception_type"],
                    failure["reason"],
                    failure["detail"],
                )
                for case in report["cases"]
                for failure in phase_failures(case)
            ),
        )
        if self.spec.experiment == "skillsbench":
            author_cases = [case for case in report["cases"] if case.get("author_counters")]
            if author_cases:
                table(
                    "Author selection and actual remeasurement",
                    (
                        "Task",
                        "r interventions",
                        "Normal K",
                        "Effective episodes",
                        "GT executions",
                        "Historical best",
                        "Actual post-final",
                        "Author retained result",
                        "Result source",
                        "Independent final reward",
                    ),
                    (
                        (
                            case["task_id"],
                            case["author_counters"]["surrogate_retries"],
                            case["author_counters"]["normal_oracle_interventions"],
                            case["author_counters"].get("generator_episodes"),
                            case.get("oracle_attempts"),
                            next(
                                (
                                    item.get("resolved_reward")
                                    for item in case["oracle_history"]
                                    if case.get("best_oracle_ref")
                                    and item["operation_id"]
                                    == case["best_oracle_ref"]["operation_id"]
                                ),
                                None,
                            ),
                            next(
                                (
                                    item.get("resolved_reward")
                                    for item in reversed(case["oracle_history"])
                                    if item["phase"] == "post_final"
                                ),
                                None,
                            ),
                            (case.get("author_terminal_result") or {}).get("resolved_reward"),
                            (case.get("author_terminal_result") or {}).get("source"),
                            (
                                (case["evaluations"].get(case.get("final_bundle_hash")) or {}).get(
                                    "metrics"
                                )
                                or {}
                            ).get("reward"),
                        )
                        for case in author_cases
                    ),
                )
            baseline_cases = [case for case in report["cases"] if "no_skill_evaluation" in case]
            if baseline_cases:
                lines.extend(
                    [
                        "",
                        "No-Skill runs use no package and do not create S0. Baseline comparisons "
                        "require the same sealed executor identity; "
                        "evaluations do not enter learning.",
                    ]
                )
                table(
                    "No-Skill independent measurements",
                    (
                        "Task",
                        "Status",
                        "Utility",
                        "ASR",
                        "ASR status",
                        "Reward",
                        "Official checks passed",
                        "Official checks total",
                        "Official check rate",
                        "Official check unit",
                    ),
                    (
                        (
                            case["task_id"],
                            case["no_skill_evaluation"].get(
                                "utility_status", case["no_skill_evaluation"]["status"]
                            ),
                            case["no_skill_evaluation"]["utility"],
                            case["no_skill_evaluation"].get("asr"),
                            case["no_skill_evaluation"].get("asr_status", "NOT_MEASURED"),
                            (case["no_skill_evaluation"].get("metrics") or {}).get("reward"),
                            (
                                (case["no_skill_evaluation"].get("metrics") or {}).get(
                                    "official_checks"
                                )
                                or {}
                            ).get("passed"),
                            (
                                (case["no_skill_evaluation"].get("metrics") or {}).get(
                                    "official_checks"
                                )
                                or {}
                            ).get("total"),
                            (
                                (case["no_skill_evaluation"].get("metrics") or {}).get(
                                    "official_checks"
                                )
                                or {}
                            ).get("rate"),
                            (
                                (case["no_skill_evaluation"].get("metrics") or {}).get(
                                    "official_checks"
                                )
                                or {}
                            ).get("unit"),
                        )
                        for case in baseline_cases
                    ),
                )
                table(
                    "No-Skill paired comparisons",
                    (
                        "Condition",
                        "Endpoint",
                        "Paired",
                        "Denominator",
                        "Utility delta",
                        "Paired coverage",
                        "Reward delta",
                        "GT paired",
                        "GT paired coverage",
                        "GT delta (pp)",
                        "Rescued",
                        "Degraded",
                    ),
                    (
                        tuple(
                            100 * row[key]
                            if key == "mean_official_check_rate_delta" and row[key] is not None
                            else row[key]
                            for key in (
                                "condition",
                                "endpoint",
                                "paired_count",
                                "task_denominator",
                                "mean_utility_delta",
                                "paired_coverage",
                                "mean_reward_delta",
                                "official_check_paired_count",
                                "official_check_paired_coverage",
                                "mean_official_check_rate_delta",
                                "rescued_count",
                                "degraded_count",
                            )
                        )
                        for row in report["baseline_paired_progress"]
                    ),
                )
            comparisons = {
                (row["task_id"], row["condition"], row["to_label"]): row
                for row in report["version_progress"]
            }
            table(
                "Independent measurements",
                (
                    "Task",
                    "Version",
                    "Role",
                    "Package hash",
                    "Utility status" if skillsbench_v8 else "Status",
                    "Utility",
                    "Reward",
                    "Official checks passed",
                    "Official checks total",
                    "Official check rate",
                    "Official check unit",
                    "ASR",
                    "ASR status",
                    "Static persistence",
                    "Static feature rate",
                    "Static matched",
                    "Static required",
                    "Previous",
                    "Utility delta",
                    "Reward delta",
                    "GT delta (pp)",
                    "GT delta reason",
                ),
                (
                    (
                        row["task_id"],
                        row["version"],
                        version_role(row),
                        row["bundle_hash"],
                        row.get("utility_status", row["status"]),
                        row["utility"],
                        (row.get("metrics") or {}).get("reward"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("passed"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("total"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("rate"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("unit"),
                        row.get("asr"),
                        row.get("asr_status"),
                        static.get("status"),
                        static.get("rate"),
                        (", ".join(static["matched"]) or "NONE")
                        if isinstance(static.get("matched"), list)
                        else None,
                        static.get("required"),
                        comparison.get("from_label"),
                        comparison.get("utility_delta"),
                        comparison.get("reward_delta"),
                        None
                        if comparison.get("official_check_rate_delta") is None
                        else 100 * comparison["official_check_rate_delta"],
                        comparison.get("official_check_delta_reason")
                        or comparison.get("reason")
                        or ("no_previous_measurement" if not comparison else "MEASURED"),
                    )
                    for row in report["versions"]
                    for comparison in (
                        comparisons.get(
                            (row["task_id"], row["condition"], f"S{row['version']}"), {}
                        ),
                    )
                    for static in (static_persistence(row),)
                ),
            )
            lines.extend(
                [
                    "",
                    "Official reward comes from the pinned grader's reward file. "
                    "Unavailable check counts remain NOT_MEASURED. "
                    "Bank reference actions and the tau banking canary do not apply to "
                    "SkillsBench. In v8, ASR is the separately monitored, controlled "
                    "injected effect from fresh evaluation; monitor failure leaves it "
                    "NOT_MEASURED without replacing official utility.",
                ]
            )
            table(
                "Surrogate checks",
                (
                    "Task",
                    "Package hash",
                    "Test version",
                    "Test hash",
                    "Passed",
                    "Pass rate",
                    "Failure",
                ),
                (
                    (
                        case["task_id"],
                        check["bundle_hash"],
                        check["test_version"],
                        check["test_hash"],
                        check["passed"],
                        check["pass_rate"],
                        check["failure"],
                    )
                    for case in report["cases"]
                    for check in case.get("verifications", [])
                ),
            )
            self._write_report_tail(lines, report, table)
            (self.root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
        table(
            "Independent measurements",
            (
                "Task",
                "Condition",
                "Version",
                "Role",
                "Package hash",
                "Status",
                "Utility",
                "ASR",
                "Reference matched",
                "Reference expected",
                "Match rate",
                "Match status",
            ),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["version"],
                    version_role(row),
                    row["bundle_hash"],
                    row["status"],
                    row["utility"],
                    row["asr"],
                    row["completion_steps"]["matched"],
                    row["completion_steps"]["expected"],
                    row["completion_steps"]["rate"],
                    row["completion_steps"]["status"],
                )
                for row in report["versions"]
            ),
        )
        lines.extend(
            [
                "",
                "Reference-action matching is separate from official utility. "
                "For DB-only tasks, a valid alternative workflow may succeed without "
                "matching every reference call. A matched call does not by itself "
                "prove the requested state change succeeded. Check indices identify "
                "reference actions, not execution order.",
                "Missing or empty action checks remain NOT_MEASURED; "
                "they are not a measured zero or full match. "
                "All details below come only from independent evaluation.",
            ]
        )
        table(
            "Reference action checks",
            (
                "Task",
                "Condition",
                "Version",
                "Role",
                "Check",
                "Action",
                "Actor",
                "Arguments",
                "Matched",
            ),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["version"],
                    version_role(row),
                    index,
                    step["action"],
                    step["actor"],
                    json.dumps(step["arguments"], ensure_ascii=False, sort_keys=True),
                    step["matched"],
                )
                for row in report["versions"]
                for index, step in enumerate(row["completion_steps"]["steps"], 1)
            ),
        )
        table(
            "Official evaluation components",
            (
                "Task",
                "Condition",
                "Version",
                "Role",
                "Reward basis",
                "DB match",
                "DB reward",
                "Environment met",
                "Communication met",
                "NL assertions met",
            ),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["version"],
                    version_role(row),
                    json.dumps(info["reward_basis"], ensure_ascii=False)
                    if info.get("reward_basis") is not None
                    else None,
                    (info.get("db_check") or {}).get("db_match"),
                    (info.get("db_check") or {}).get("db_reward"),
                    check_count(info.get("env_assertions")),
                    check_count(info.get("communicate_checks")),
                    check_count(info.get("nl_assertions")),
                )
                for row in report["versions"]
                for info in (official(row),)
            ),
        )
        table(
            "Official communication checks",
            (
                "Task",
                "Condition",
                "Version",
                "Role",
                "Check",
                "Information",
                "Met",
                "Justification",
            ),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["version"],
                    version_role(row),
                    index,
                    check.get("info"),
                    check.get("met"),
                    check.get("justification"),
                )
                for row in report["versions"]
                for index, check in enumerate(official(row).get("communicate_checks") or [], 1)
                if isinstance(check, dict)
            ),
        )
        table(
            "Surrogate checks",
            (
                "Task",
                "Condition",
                "Package hash",
                "Test version",
                "Test hash",
                "Passed",
                "Pass rate",
                "Failure",
            ),
            (
                (
                    case["task_id"],
                    case["condition"],
                    check["bundle_hash"],
                    check["test_version"],
                    check["test_hash"],
                    check["passed"],
                    check["pass_rate"],
                    check["failure"] or "—",
                )
                for case in report["cases"]
                for check in case.get("verifications", [])
            ),
        )
        lines.extend(["", "## Revision attempts", ""])
        for case in report["cases"]:
            for attempt in case.get("attempts", []):
                lines.append(
                    f"- {cell(case['task_id'])} / {case['condition']}: "
                    f"attempt {attempt['attempt']}, "
                    f"{attempt['status']}, parent `{attempt['parent_hash']}`, "
                    f"package `{attempt.get('bundle_hash', 'NOT_MEASURED')}`, "
                    f"tests v{attempt['test_version']} `{attempt['test_hash']}`."
                )
        self._write_report_tail(lines, report, table)
        (self.root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_report_tail(self, lines: list[str], report: dict[str, Any], table: Any) -> None:
        skillsbench_v8 = (
            self.spec.experiment == "skillsbench"
            and report.get("namespace") == "skillsbench.skill-evolution.v8"
        )

        def exposure_population(stage: dict[str, Any]) -> str:
            return "; ".join(
                f"{label} {stage[name]}"
                for label, name in (
                    ("O", "chunk_occurrences"),
                    ("C", "unique_chunks"),
                    ("S", "unique_sources"),
                )
            )

        def exposure_rate(stage: dict[str, Any], flag: str) -> str:
            rates = stage["rates"][flag]
            return "; ".join(
                f"{label} {rates[name]['numerator']}/{rates[name]['denominator']}"
                for label, name in (
                    ("O", "chunk_occurrences"),
                    ("C", "unique_chunks"),
                    ("S", "unique_sources"),
                )
            )

        table(
            "Adjacent content paired coverage",
            (
                "Condition",
                "From",
                "To",
                "Actual chains",
                "Denominator",
                "Paired",
                "Paired coverage",
                "Utility delta",
                "Reward paired",
                "Reward delta",
                "GT paired",
                "GT paired coverage",
                "GT delta (pp)",
            ),
            (
                (
                    row["condition"],
                    row["from_label"],
                    row["to_label"],
                    row["actual_chains"],
                    row["task_denominator"],
                    row["paired_count"],
                    row["paired_coverage"],
                    row["mean_utility_delta"],
                    row["reward_paired_count"],
                    row["mean_reward_delta"],
                    row["official_check_paired_count"],
                    row["official_check_paired_coverage"],
                    None
                    if row["mean_official_check_rate_delta"] is None
                    else 100 * row["mean_official_check_rate_delta"],
                )
                for row in report["version_paired_progress"]
            ),
        )
        lines.extend(
            [
                "",
                "S labels enumerate sealed content hashes, not revision attempts. "
                "Final aliases the selected content's existing evaluation; "
                "early stopping adds no versions. "
                "GT deltas require measured checks with matching unit, total and source. "
                "Utility/reward and GT means use their own recorded pair counts; "
                "different coverage cannot be subtracted as an evolution effect.",
            ]
        )
        table(
            "Paired evolution progress",
            (
                "Task",
                "Condition",
                "Paired measured",
                "Utility delta",
                "Reward delta",
                "GT delta (pp)",
                "GT delta reason",
                "Final aliases S0",
                "Rescued",
            ),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["paired_measured"],
                    row["utility_delta"],
                    row["reward_delta"],
                    None
                    if row["official_check_rate_delta"] is None
                    else 100 * row["official_check_rate_delta"],
                    row["official_check_delta_reason"] or "MEASURED",
                    row["same_content"],
                    row["rescued"],
                )
                for row in report["progress"]
                if row["initial_hash"] is not None
            ),
        )
        table(
            "S0-to-Final paired coverage",
            (
                "Condition",
                "Denominator",
                "Paired",
                "Paired coverage",
                "Utility delta",
                "Reward paired",
                "Reward delta",
                "GT paired",
                "GT paired coverage",
                "GT delta (pp)",
                "Same content",
                "Rescued",
                "Degraded",
            ),
            (
                (
                    row["condition"],
                    row["task_denominator"],
                    row["paired_count"],
                    row["paired_coverage"],
                    row["mean_utility_delta"],
                    row["reward_paired_count"],
                    row["mean_reward_delta"],
                    row["official_check_paired_count"],
                    row["official_check_paired_coverage"],
                    None
                    if row["mean_official_check_rate_delta"] is None
                    else 100 * row["mean_official_check_rate_delta"],
                    row["same_content_count"],
                    row["rescued_count"],
                    row["degraded_count"],
                )
                for row in report["paired_progress"]
            ),
        )
        table(
            "Frozen acquisition",
            ("Task", "Condition", "Documents", "Tokens", "Stop", "Base hash"),
            (
                (
                    case["task_id"],
                    case["condition"],
                    base["selected_documents"],
                    base["base_tokens"],
                    base["stop_reason"],
                    base["base_hash"],
                )
                for case in report["cases"]
                for base in (case.get("acquisition"),)
                if base and base.get("base_hash")
            ),
        )
        if skillsbench_v8:
            lines.extend(
                [
                    "",
                    "Acquisition exposure uses O for chunk occurrences, C for unique chunks, "
                    "and S for unique source documents. Join it to Independent measurements "
                    "by task and condition: acquisition exposure records pre-package input "
                    "visibility, package-static persistence records features in the sealed "
                    "package, and fresh ASR records controlled behavior during independent "
                    "evaluation. These are separate measurements.",
                ]
            )
            table(
                "Acquisition exposure coverage",
                ("Arm", "Stage", "Measured", "Missing", "Denominator"),
                (
                    (
                        row["arm"],
                        row["stage"],
                        row["measured"],
                        row["missing"],
                        row["denominator"],
                    )
                    for row in report.get("acquisition_exposure_coverage", ())
                ),
            )
            table(
                "Acquisition payload exposure",
                (
                    "Task",
                    "Condition",
                    "Stage",
                    "Status",
                    "Reason",
                    "Population (O/C/S)",
                    "Source poisoned (O/C/S)",
                    "Payload present (O/C/S)",
                    "Partial payload (O/C/S)",
                    "Full payload (O/C/S)",
                ),
                (
                    (
                        case["task_id"],
                        case["condition"],
                        stage_name,
                        stage.get("status"),
                        stage.get("reason", "—"),
                        exposure_population(stage) if stage.get("status") == "MEASURED" else None,
                        exposure_rate(stage, "source_poisoned")
                        if stage.get("status") == "MEASURED"
                        else None,
                        exposure_rate(stage, "payload_present")
                        if stage.get("status") == "MEASURED"
                        else None,
                        exposure_rate(stage, "payload_partial")
                        if stage.get("status") == "MEASURED"
                        else None,
                        exposure_rate(stage, "full_payload_present")
                        if stage.get("status") == "MEASURED"
                        else None,
                    )
                    for case in report["cases"]
                    for acquisition in (case.get("acquisition") or {},)
                    for payload in (acquisition.get("payload_exposure") or {},)
                    for stage_name in (
                        "corpus",
                        "search_returns",
                        "analyzer_visible",
                        "frozen_base",
                    )
                    for stage in ((payload.get("stages") or {}).get(stage_name),)
                    if stage
                ),
            )
        if self.spec.experiment == "tau":
            table(
                "Post-evaluation gold coverage",
                (
                    "Task",
                    "Condition",
                    "Gold docs",
                    "Returned gold",
                    "Frozen gold",
                    "Returned recall",
                    "Base recall",
                ),
                (
                    (
                        case["task_id"],
                        case["condition"],
                        gold["gold_count"],
                        gold["returned_gold_count"],
                        gold["selected_gold_count"],
                        gold["returned_recall"],
                        gold["base_recall"],
                    )
                    for case in report["cases"]
                    for gold in (case.get("gold_coverage"),)
                    if gold
                ),
            )
        usage = report["usage"]
        table(
            "Provider token usage",
            ("Role", "Responses", "Input tokens", "Output tokens", "Cached input tokens"),
            (
                (
                    role,
                    item["requests"],
                    item["input_tokens"],
                    item["output_tokens"],
                    item["cached_input_tokens"],
                )
                for role, item in usage["roles"].items()
            ),
        )
        lines.extend(
            [
                "",
                "Dollar cost: NOT_MEASURED; provider responses do not include billing charges. "
                "Usage includes successful responses; "
                "unknown requests may incur unreported charges.",
            ]
        )
