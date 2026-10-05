"""The supported create → evolve → independently evaluate workflow."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .acquisition import READ_ONLY_TOOL_NAMES, AcquisitionBudgets, collect_base
from .artifacts import FrozenBase, atomic_json, load_base, load_bundle, seal_base, seal_bundle
from .credentials import bearer_token_source
from .generator import SKILL_BUNDLE_RESPONSE_FORMAT, CreationFailure, generate_initial, revise
from .journal import Journal, UnknownOperation, identity_temporary
from .model import (
    CredentialError,
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
    SerializedChatTokenCounter,
)
from .retrieval import prepare_corpus, text_counter
from .spec import ExperimentSpec, digest


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
    ) -> None:
        self.spec = spec
        self.demo = demo
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
            raise ValueError("run directory has no tau.skill-evolution.v1 checkpoint identity")
        self.identity = spec.identity
        self.execution: dict[str, Any] = {"backend": "docker", "formal_matrix_result": False}
        if demo:
            lock_path = (
                spec.root / spec.values["source"]["runtime_lock"]
                if spec.experiment == "skillsbench"
                else spec.root / "runtime" / "bubblewrap-lock.json"
            )
            if spec.experiment == "tau":
                from .bubblewrap import RuntimeLock

                RuntimeLock.from_file(lock_path).validate()
            self.execution = {
                "backend": "bubblewrap-demo",
                "formal_matrix_result": False,
                "aggregate_limits_enforced": False,
                "runtime_lock_hash": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                "task_id": self.demo_task,
            }
            self.identity = {
                **self.identity,
                "execution": self.execution,
                "identity_hash": digest(
                    {"base": self.identity["identity_hash"], "execution": self.execution}
                ),
            }
        self.journal = Journal(self.root / "journal", identity=self.identity)
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

    def _model(self, role: str) -> Any:
        if self.model_factory is not None:
            return self.model_factory(role)
        provider = self.spec.provider_settings
        settings = (
            self.spec.values["roles"][role]
            if role in self.spec.values["roles"]
            else self.spec.values["runtime"]["controls"]["agent"]
        )
        return OpenAICompatibleClient(
            provider["api_base"],
            api_key=bearer_token_source(provider["api_key_env"]),
            config=GenerationConfig(
                model=provider["model"],
                transport=provider["transport"],
                reasoning_effort=settings["reasoning_effort"],
                max_output_tokens=settings["max_output_tokens"],
                max_input_tokens=settings.get(
                    "max_input_tokens", self.spec.values["runtime"]["controls"]["max_input_tokens"]
                ),
                response_format=SKILL_BUNDLE_RESPONSE_FORMAT if role == "generator" else None,
            ),
            timeout_seconds=self.spec.values["runtime"]["request_timeout_seconds"],
            token_counter=SerializedChatTokenCounter(
                self.counter, basis="embedding_serialized_text_estimate"
            ),
            usage_path=self.root / "usage.jsonl",
            usage_role=role,
        )

    def _bank(self, task: str) -> Any:
        if self.bank_factory is not None:
            return self.bank_factory(task)
        if self.spec.experiment == "skillsbench":
            from .skillsbench import SkillsBenchAdapter

            return SkillsBenchAdapter(
                self.spec,
                task,
                demo=self.demo,
                model_factory=self._model,
                counter=self.counter,
                artifact_root=self.root / "artifacts" / task,
            )
        from .bank import Bank

        config = self.spec.worker_config()
        config["usage_path"] = str((self.root / "usage.jsonl").resolve())
        config["worker_log_dir"] = str((self.root / "logs" / "workers").resolve())
        if self.demo:
            config["sandbox"] = {
                "backend": "bubblewrap-demo",
                "runtime_lock": str(self.spec.root / "runtime" / "bubblewrap-lock.json"),
            }
        config["attack_profile"] = self.spec.profile(task)
        return Bank(
            self.spec.upstream / ".venv" / "bin" / "python", self.spec.upstream, task, config
        )

    def _runner(self) -> Any:
        if self.runner is None:
            if self.demo:
                from .bubblewrap import BubblewrapRunner, RuntimeLock

                self.runner = BubblewrapRunner(
                    RuntimeLock.from_file(self.spec.root / "runtime" / "bubblewrap-lock.json")
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
                f"Bedrock authentication failed (HTTP {status}); later cells stopped",
                status=status,
            )

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
        if journal.completed("creation"):
            record = journal.response("creation")
            if record["status"] == "CREATED":
                self._created(root, journal)
            return
        base: FrozenBase | None = None
        try:
            bank = self._bank(task)
            if (root / "base").exists():
                base = load_base(root / "base")
            else:

                def acquire() -> dict[str, Any]:
                    with bank.acquisition() as session:
                        corpus = (
                            self.corpus_factory(task, arm)
                            if self.corpus_factory
                            else prepare_corpus(self.spec, task, arm)
                        )
                        allowed_reads = (
                            () if self.spec.experiment == "skillsbench" else READ_ONLY_TOOL_NAMES
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
                        collected = collect_base(
                            self._model("analyzer"),
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
                        )
                    seal_base(root / "base", collected)
                    return collected.to_dict()

                base = FrozenBase.from_dict(journal.dispatch("collect-base", {}, acquire))
                seal_base(root / "base", base)
            if (root / "initial").exists():
                bundle = load_bundle(root / "initial")
            else:
                bundle = generate_initial(
                    self._model("generator"),
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
                    reserved_output_tokens=self.spec.values["roles"]["generator"][
                        "max_output_tokens"
                    ],
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
        creation = journal.response("creation")
        if creation["status"] != "CREATED":
            return
        base, initial = self._created(root, journal)
        if journal.completed("evolution-result"):
            result = EvolutionResult.from_dict(journal.response("evolution-result"))
        else:
            bank = self._bank(task)

            def revision(
                previous: Any,
                inputs: Any,
                frozen: Any,
                report: Any,
                *,
                operation_id: str,
                feedback_history: Any = (),
            ) -> Any:
                return revise(
                    self._model("generator"),
                    previous,
                    inputs,
                    frozen,
                    report,
                    journal=journal,
                    operation_id=operation_id,
                    tool_schemas=bank.tool_schemas,
                    artifact_dir=root / "revisions" / operation_id,
                    seed=self.spec.values["seed"],
                    system_prompt=self._prompt("generator"),
                    feedback_history=feedback_history,
                    token_counter=SerializedChatTokenCounter(self.counter),
                    context_window=self.spec.values["roles"]["generator"].get(
                        "context_window", 272000
                    ),
                    context_fraction=self.spec.values["roles"]["generator"].get(
                        "context_beta", 0.7
                    ),
                    reserved_output_tokens=self.spec.values["roles"]["generator"][
                        "max_output_tokens"
                    ],
                )

            engine = EvolutionEngine(
                rollout=bank.rollout,
                oracle=bank.oracle,
                verifier=SurrogateVerifier(
                    self._model("verifier"),
                    bank.verifier_runner()
                    if self.spec.experiment == "skillsbench" and self.runner is None
                    else self._runner(),
                    journal=journal,
                    system_prompt=self._prompt("verifier"),
                    max_output_tokens=self.spec.values["roles"]["verifier"]["max_output_tokens"],
                    seed=self.spec.values["seed"],
                ),
                revise=revision,
                journal=journal,
                max_revisions=self.spec.values["evolution"]["max_revisions"],
                max_oracles=self.spec.values["evolution"]["max_oracles"],
            )
            result = engine.run(base.public_inputs, base, initial)
        for bundle in result.versions:
            seal_bundle(root / "versions" / bundle.bundle_hash, bundle)

    def evaluate(self, cells: tuple[tuple[str, str], ...]) -> None:
        self._validate_cells(cells)
        from .evaluation import evaluate_versions
        from .evolution import EvolutionResult

        for task, arm in cells:
            root, journal = self._cell(task, arm)
            creation = journal.response("creation")
            if creation["status"] != "CREATED":
                continue
            _, initial = self._created(root, journal)
            if journal.completed("evolution-result"):
                versions = EvolutionResult.from_dict(journal.response("evolution-result")).versions
            else:
                versions = (initial,)
            bank = self._bank(task)
            for bundle in versions:
                sealed = (
                    root / "initial"
                    if bundle.parent_hash is None
                    else root / "versions" / bundle.bundle_hash
                )
                load_bundle(sealed)
            evaluate_versions(versions, bank.evaluate, journal=journal)
            self._halt_on_authentication(task, arm)

    def report(self) -> dict[str, Any]:
        from .evaluation import not_measured, report_cases
        from .evolution import EvolutionResult

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
            if (directory / "journal").exists():
                _, journal = self._cell(task, arm)
                if journal.completed("creation"):
                    creation = journal.response("creation")
                    case["status"] = creation["status"]
                    case["creation"] = creation
                    if creation["status"] == "CREATED":
                        base, initial = self._created(directory, journal)
                        versions = (initial,)
                        final_hash = initial.bundle_hash
                        case["stop_reason"] = "evolution_not_started"
                        if journal.completed("evolution-result"):
                            result = EvolutionResult.from_dict(journal.response("evolution-result"))
                            versions = result.versions
                            final_hash = result.final_bundle_hash
                            case.update(
                                stop_reason=result.stop_reason,
                                revision_attempts=result.revision_attempts,
                                oracle_calls=result.oracle_calls,
                                attempts=list(result.attempts),
                                verifications=[
                                    {
                                        key: check[key]
                                        for key in (
                                            "bundle_hash",
                                            "test_version",
                                            "test_hash",
                                            "passed",
                                            "pass_rate",
                                            "failure",
                                            "program_error",
                                        )
                                    }
                                    for check in result.verifications
                                ],
                            )
                        case["versions"] = [
                            {"bundle_hash": bundle.bundle_hash} for bundle in versions
                        ]
                        case["final_bundle_hash"] = final_hash
                        case["initial_bundle_hash"] = initial.bundle_hash
                        case["frozen_control_hash"] = (
                            initial.bundle_hash if arm != "benign" else None
                        )
                        case["evolution"] = {
                            "final_bundle_hash": final_hash,
                            "stop_reason": case["stop_reason"],
                        }
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
                        case["acquisition"] = {
                            "base_hash": base.base_hash,
                            "selected_documents": len(base.documents),
                            "base_tokens": base.token_count,
                            "stop_reason": base.stop_reason,
                        }
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
        report = report_cases(
            cases,
            task_denominator=len(self.spec.tasks),
            conditions=tuple(self.spec.values["matrix"]["arms"]),
        )
        report["namespace"] = self.spec.namespace
        report["experiment"] = self.spec.experiment
        report["protocol"] = self.spec.namespace
        report["run_mode"] = "single-task-demo" if self.demo else "formal"
        report["formal_matrix_result"] = not self.demo and any(
            measurement["status"] == "MEASURED"
            for case in cases
            for measurement in case["evaluations"].values()
        )
        report["execution"] = {
            **self.execution,
            "formal_matrix_result": report["formal_matrix_result"],
        }
        report["cases"] = cases
        report["usage"] = self._usage_summary()
        atomic_json(self.root / "report.json", report)
        self._write_report_md(report)
        return report

    def _usage_summary(self) -> dict[str, Any]:
        roles: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
        )
        path = self.root / "usage.jsonl"
        for line in path.read_text().splitlines() if path.exists() else ():
            item = json.loads(line)
            row, usage = roles[item["role"]], item["usage"]
            row["requests"] += 1
            row["input_tokens"] += usage.get("input_tokens", usage.get("prompt_tokens", 0))
            row["output_tokens"] += usage.get("output_tokens", usage.get("completion_tokens", 0))
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens")
            row["cached_input_tokens"] = (
                row["cached_input_tokens"] + cached
                if row["cached_input_tokens"] is not None and cached is not None
                else None
            )
        return {
            "status": "MEASURED" if roles else "NOT_MEASURED",
            "basis": "provider_response_usage; successful responses only",
            "roles": dict(roles),
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

        lines = [
            f"# {self.spec.experiment} run report",
            "",
            f"Protocol: `{report['namespace']}`",
            "",
            f"End-to-end rates use the full {len(self.spec.tasks)}-task arm denominator. "
            "Measured means use only valid measurements.",
            "Missing measurements remain null in JSON and NOT_MEASURED here.",
            "The S0 evaluation also represents the frozen control; it is not another sample.",
        ]
        if self.demo:
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
            if self.spec.experiment == "skillsbench":
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

        table(
            "Final arms",
            (
                "Condition",
                "Arm",
                "Denominator",
                "Chains",
                "Measured",
                "Utility mean",
                "ASR mean",
                "End-to-end utility",
                "Observed ASR / task",
            ),
            (
                tuple(
                    row[key]
                    for key in (
                        "condition",
                        "arm",
                        "task_denominator",
                        "actual_chains",
                        "measured_count",
                        "measured_utility",
                        "measured_asr",
                        "end_to_end_utility",
                        "observed_attack_successes_per_task",
                    )
                )
                for row in report["arms"]
            ),
        )
        table(
            "Actual content versions",
            ("Condition", "Version", "Chains", "Measured", "Utility mean", "ASR mean", "Stops"),
            (
                tuple(
                    row[key]
                    for key in (
                        "condition",
                        "version",
                        "actual_chains",
                        "measured_count",
                        "measured_utility",
                        "measured_asr",
                        "stop_counts",
                    )
                )
                for row in report["rounds"]
            ),
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
                    case.get("final_bundle_hash"),
                )
                for case in report["cases"]
            ),
        )
        if self.spec.experiment == "skillsbench":
            table(
                "Independent measurements",
                (
                    "Task",
                    "Version",
                    "Role",
                    "Package hash",
                    "Status",
                    "Utility",
                    "Reward",
                    "Official checks passed",
                    "Official checks total",
                    "Official check rate",
                ),
                (
                    (
                        row["task_id"],
                        row["version"],
                        version_role(row),
                        row["bundle_hash"],
                        row["status"],
                        row["utility"],
                        (row.get("metrics") or {}).get("reward"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("passed"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("total"),
                        ((row.get("metrics") or {}).get("official_checks") or {}).get("rate"),
                    )
                    for row in report["versions"]
                ),
            )
            lines.extend(
                [
                    "",
                    "Official reward comes from the pinned grader's reward file. "
                    "Unavailable check counts remain NOT_MEASURED. "
                    "Bank reference actions and canary ASR do not apply to SkillsBench.",
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
        table(
            "Paired evolution progress",
            ("Task", "Condition", "Paired measured", "Utility delta", "Reward delta", "Rescued"),
            (
                (
                    row["task_id"],
                    row["condition"],
                    row["paired_measured"],
                    row["utility_delta"],
                    row["reward_delta"],
                    row["rescued"],
                )
                for row in report["progress"]
                if row["initial_hash"] is not None
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
                if base
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
