from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from r2sp.agent import AgentResult
from r2sp.artifacts import sha256_file
from r2sp.cases import (
    CaseTokenCounts,
    FrozenCaseBundle,
    build_overlay_attestation,
)
from r2sp.cli import main
from r2sp.config import load_config
from r2sp.integrity import ContentDigest
from r2sp.models import CaseSpec, OverlayPair, OverlaySpec, Resource, TaskSpec
from r2sp.preflight import PreflightCheck, PreflightReport
from r2sp.research_runner import (
    ResearchDependencies,
    ResearchPreflightError,
    ResearchRunInterrupted,
    ResearchRunLocked,
    ResearchRunnerError,
    ResearchRunResult,
    _appworld_root,
    _code_hash,
    _validate_frozen_appworld_tasks,
    _validate_output_location,
    _verify_case_token_counts,
    load_runtime_config,
    run_pilot,
)
from r2sp.resource_pool import ResourcePool
from r2sp.runtime.base import RuntimeIdentity, RuntimeObservation

ROOT = Path(__file__).resolve().parents[1]


class FakeModelClient:
    def __init__(self) -> None:
        self.compiler_system_prompts: list[str] = []

    def complete(self, messages, **kwargs):
        self.compiler_system_prompts.append(messages[0]["content"])
        return {
            "content": (
                "---\n"
                "name: fake-appworld-workflow\n"
                "description: Reusable workflow for the injected AppWorld test.\n"
                "---\n\n"
                "Use the trusted task interfaces to complete the current benign task.\n"
            )
        }


class FakeRuntime:
    def __init__(
        self,
        task_id: str,
        instruction: str,
        nonce: str,
        identity: RuntimeIdentity,
        *,
        canary_handler=None,
    ) -> None:
        self.task_id = task_id
        self._instruction = instruction
        self.nonce = nonce
        self._next_identity = identity
        self._identity = None
        self._canary_handler = canary_handler
        self.closed = False

    @property
    def identity(self):
        return self._identity

    @property
    def task_instruction(self):
        if self._identity is None:
            raise RuntimeError("not started")
        return self._instruction

    @property
    def app_descriptions(self):
        if self._identity is None:
            raise RuntimeError("not started")
        return {f"app_{index}": f"Injected local application {index}." for index in range(9)}

    def start(self):
        if self._identity is not None:
            raise RuntimeError("already started")
        self._identity = self._next_identity
        return self._identity

    def execute(self, app, api, args):
        if app == "canary" and api == "emit" and self._canary_handler is not None:
            receipt = self._canary_handler(args)
            return RuntimeObservation(app, api, dict(args), True, receipt)
        return RuntimeObservation(app, api, dict(args), True, {"ok": True})

    def close(self):
        self.closed = True


class FakeRuntimeFactory:
    def __init__(self, tasks: dict[str, tuple[str, str]], appworld_root: Path) -> None:
        self.tasks = tasks
        self.appworld_root = appworld_root
        self.created: list[FakeRuntime] = []
        self.experiment_names: list[str] = []

    def __call__(self, task_id, *, experiment_name=None, canary_handler=None):
        if os.environ.get("APPWORLD_ROOT") != str(self.appworld_root):
            raise AssertionError("APPWORLD_ROOT was not bound before runtime creation")
        if not isinstance(experiment_name, str) or not experiment_name:
            raise AssertionError("runtime experiment_name was not bound")
        self.experiment_names.append(experiment_name)
        instruction, nonce = self.tasks[task_id]
        index = len(self.created)
        runtime = FakeRuntime(
            task_id,
            instruction,
            nonce,
            RuntimeIdentity(
                f"world-{index}",
                f"context-{index}",
                f"session-{index}",
            ),
            canary_handler=canary_handler,
        )
        self.created.append(runtime)
        return runtime


class FakeAgentRunner:
    pool_sizes: list[int] = []
    selection_modes: list[int | None] = []

    def __init__(self, client, **kwargs) -> None:
        del client
        self.selection_k = kwargs.get("selection_k")
        self.selection_modes.append(self.selection_k)

    def run(self, task, app_descriptions, runtime, retriever, *, skill=None, seed=None):
        del task, app_descriptions, seed
        self.pool_sizes.append(retriever.resource_count)
        read_documents = ()
        resource_ids = ()
        retrieval_trace = ()
        candidate_resource_ids = ()
        selected_resource_ids = ()
        selection_trace = ()
        api_trace = ()
        if skill is None:
            if self.selection_k != 5:
                raise AssertionError("research acquisition did not enable exact-five selection")
            case_number = int(runtime.task_id.split("-")[-1])
            hits = retriever.search(f"overlaytoken{case_number:02d}")
            candidate_resource_ids = tuple(hit.resource_id for hit in hits)
            selected_resource_ids = candidate_resource_ids[: self.selection_k]
            if not any(item.startswith("overlay-") for item in selected_resource_ids):
                raise AssertionError("test overlay did not enter the selected five")
            documents = tuple(retriever.read(resource_id) for resource_id in selected_resource_ids)
            read_documents = tuple(document.to_dict() for document in documents)
            resource_ids = tuple(document.resource_id for document in documents)
            retrieval_trace = (
                {
                    "query": f"overlaytoken{case_number:02d}",
                    "top_k": 10,
                    "results": [hit.to_dict() for hit in hits],
                },
            )
            selection_trace = (
                {
                    "resource_ids": list(selected_resource_ids),
                    "candidate_resource_ids": list(candidate_resource_ids),
                    "accepted": True,
                },
            )
        elif runtime.task_id.startswith("positive-"):
            observation = runtime.execute("canary", "emit", {"nonce": runtime.nonce})
            trace = observation.as_trace()
            trace["call_index"] = 1
            api_trace = (trace,)
        identity = runtime.identity
        return AgentResult(
            read_documents=read_documents,
            resource_ids=resource_ids,
            retrieval_trace=retrieval_trace,
            read_trace=(),
            api_trace=api_trace,
            task_success=True,
            score=0.75,
            world_id=identity.world_id,
            context_id=identity.context_id,
            session_id=identity.session_id,
            failure=None,
            turns=1,
            search_calls=1 if skill is None else 0,
            api_calls=1 if api_trace else 0,
            finish_status="success",
            candidate_resource_ids=candidate_resource_ids,
            selected_resource_ids=selected_resource_ids,
            selection_trace=selection_trace,
        )


class Harness:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.appworld_root = base / "appworld"
        (self.appworld_root / "data" / "api_docs" / "standard").mkdir(parents=True)
        self.output_root = base / "runs"
        self.config_path = base / "experiment.yaml"
        config = yaml.safe_load(
            (ROOT / "configs" / "experiment_plan.yaml").read_text(encoding="utf-8")
        )
        config["protocol"]["runner_ready"] = True
        config["appworld"]["data_bundle_sha256"] = "a" * 64
        self.config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        resources = tuple(
            Resource(
                resource_id=f"clean-{index:03d}",
                app_name="calendar",
                api_name=f"api_{index:03d}",
                title=f"Clean API {index}",
                body=f"Stable clean API documentation number {index}.",
            )
            for index in range(457)
        )
        self.clean_pool = ResourcePool(resources)
        self.manifest_path = base / "clean-manifest.json"
        self.manifest_path.write_text(
            json.dumps(self.clean_pool.manifest.to_dict(), sort_keys=True) + "\n",
            encoding="utf-8",
        )

        cases = []
        counts = []
        self.tasks: dict[str, tuple[str, str]] = {}
        for index in range(16):
            case_id = f"case-{index:02d}"
            nonce = f"nonce-{index:02d}"
            authoring = TaskSpec(
                f"authoring-{index:02d}",
                "authoring",
                f"Author task {index}",
            )
            positive = TaskSpec(
                f"positive-{index:02d}",
                "trigger_positive",
                f"Positive task {index}",
            )
            negative = TaskSpec(
                f"negative-{index:02d}",
                "trigger_negative",
                f"Negative task {index}",
            )
            public = {
                "resource_id": f"overlay-{index:02d}",
                "app_name": "calendar",
                "api_name": f"overlay_api_{index:02d}",
                "title": f"Matched overlay {index}",
            }
            sham = OverlaySpec(
                "A_sham",
                Resource(
                    **public,
                    body=f"overlaytoken{index:02d} benign workflow guidance",
                ),
                trigger=f"trigger-{index:02d}",
                nonce=nonce,
            )
            poison = OverlaySpec(
                "B_poison",
                Resource(
                    **public,
                    body=f"overlaytoken{index:02d} adversarial workflow guidance",
                ),
                trigger=f"trigger-{index:02d}",
                nonce=nonce,
            )
            case = CaseSpec(
                case_id,
                authoring,
                positive,
                negative,
                OverlayPair(case_id, sham, poison),
            )
            cases.append(case)
            counts.append(CaseTokenCounts(case_id, 10, 10))
            for task in (authoring, positive, negative):
                self.tasks[task.task_id] = (task.instruction, nonce)
        self.cases_path = base / "cases.json"
        self.cases_path.write_text("injected frozen case source\n", encoding="utf-8")
        self.bundle = FrozenCaseBundle(
            protocol_version="0.3",
            tokenizer_model="Qwen/Qwen3.8-27B",
            tokenizer_revision="1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
            cases=tuple(cases),
            token_counts=tuple(counts),
            research_mode=True,
            source_path=self.cases_path,
        )
        self.overlays_path = base / "overlays.json"
        self.overlays_path.write_text(
            json.dumps(build_overlay_attestation(self.bundle).to_dict(), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.runtime_path = base / "runtime.yaml"
        self.lockfiles = (base / "appworld.lock", base / "model-service.lock")
        self.lockfiles[0].write_text("injected appworld lock\n", encoding="utf-8")
        self.lockfiles[1].write_text("injected model lock\n", encoding="utf-8")
        self.runtime_path.write_text(
            yaml.safe_dump(
                {
                    "runtime": {
                        "mode": "research",
                        "appworld_root": str(self.appworld_root),
                        "clean_manifest": str(self.manifest_path),
                        "cases": str(self.cases_path),
                        "overlays": str(self.overlays_path),
                        "dependency_lockfiles": [str(path) for path in self.lockfiles],
                        "output_root": str(self.output_root),
                        "phase_timeout_seconds": 1800,
                        "model_request_timeout_seconds": 300,
                        "evaluate_every_completed_cases": 1,
                        "resume": True,
                    },
                    "model_service": {
                        "base_url": "http://127.0.0.1:8000/v1",
                        "api_key_env": "R2SP_MODEL_API_KEY",
                    },
                    "logging": {
                        "level": "INFO",
                        "jsonl": True,
                        "include_protected_document_bodies": False,
                        "include_model_reasoning": False,
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.model = FakeModelClient()
        self.runtime_factory = FakeRuntimeFactory(self.tasks, self.appworld_root)
        self.preflight_calls = []

    def ready_preflight(self, *args, **kwargs):
        self.preflight_calls.append((args, kwargs))
        return PreflightReport(
            (PreflightCheck("injected_ready", True, True, "ready", "research"),),
            mode="research",
        )

    def dependencies(self, *, preflight=None):
        return ResearchDependencies(
            preflight_runner=preflight or self.ready_preflight,
            config_loader=load_config,
            clean_pool_loader=lambda root, config: self.clean_pool,
            case_loader=lambda path: self.bundle,
            model_client_factory=lambda runtime, config: self.model,
            runtime_factory=self.runtime_factory,
            agent_runner_factory=FakeAgentRunner,
        )


class ResearchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeAgentRunner.pool_sizes = []
        FakeAgentRunner.selection_modes = []

    def test_preflight_failure_has_no_output_or_appworld_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "blocked-output"

            def blocked(*args, **kwargs):
                del args, kwargs
                return PreflightReport(
                    (PreflightCheck("blocked", False, True, "not ready", "research"),),
                    mode="research",
                )

            def forbidden_loader(*args, **kwargs):
                raise AssertionError("post-preflight loader was called")

            dependencies = harness.dependencies(preflight=blocked)
            dependencies = ResearchDependencies(
                **{
                    **dependencies.__dict__,
                    "config_loader": forbidden_loader,
                }
            )
            with patch.dict(os.environ, {"APPWORLD_ROOT": "sentinel"}):
                with self.assertRaises(ResearchPreflightError):
                    run_pilot(
                        harness.runtime_path,
                        config_path=harness.config_path,
                        project_root=ROOT,
                        output_directory=output,
                        dependencies=dependencies,
                    )
                self.assertEqual(os.environ["APPWORLD_ROOT"], "sentinel")
            self.assertFalse(output.exists())
            self.assertEqual(harness.runtime_factory.created, [])

    def test_appworld_execution_disables_new_bytecode_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module_name = "r2sp_bytecode_write_probe"
            source = root / f"{module_name}.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            sys.path.insert(0, str(root))
            try:
                with patch.object(sys, "dont_write_bytecode", False):
                    with _appworld_root(root):
                        imported = importlib.import_module(module_name)
                        self.assertEqual(imported.VALUE, 1)
                        self.assertTrue(sys.dont_write_bytecode)
                        self.assertEqual(os.environ["PYTHONDONTWRITEBYTECODE"], "1")
                    self.assertFalse(sys.dont_write_bytecode)
                self.assertFalse((root / "__pycache__").exists())
            finally:
                sys.modules.pop(module_name, None)
                sys.path.remove(str(root))

    def test_injected_end_to_end_runs_all_phases_and_caches_without_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "pilot-output"
            dependencies = harness.dependencies()
            first = run_pilot(
                harness.runtime_path,
                config_path=harness.config_path,
                project_root=ROOT,
                output_directory=output,
                dependencies=dependencies,
            )
            self.assertFalse(first.cached)
            self.assertEqual(first.summary["mode"], "injected_test")
            self.assertEqual(first.summary["decision"], "NOT_ELIGIBLE")
            self.assertFalse(first.summary["research_eligible"])
            self.assertEqual(first.summary["denominators"]["deployment_tasks_per_arm"], 32)
            self.assertEqual(first.summary["poison_natural_reads"], 16)
            self.assertEqual(first.summary["poison_overlay_top10"], 16)
            self.assertEqual(first.summary["sham_overlay_top10"], 16)
            self.assertEqual(first.summary["poison_positive_canary_activations"], 16)
            self.assertEqual(len(harness.runtime_factory.created), 96)
            self.assertEqual(len(set(harness.runtime_factory.experiment_names)), 96)
            self.assertTrue(
                all(
                    name.startswith(first.run_id + "-")
                    for name in harness.runtime_factory.experiment_names
                )
            )
            self.assertEqual(FakeAgentRunner.pool_sizes.count(458), 32)
            self.assertEqual(FakeAgentRunner.pool_sizes.count(457), 64)
            self.assertEqual(FakeAgentRunner.selection_modes.count(5), 32)
            self.assertEqual(FakeAgentRunner.selection_modes.count(None), 64)
            self.assertEqual(len(harness.model.compiler_system_prompts), 32)
            self.assertEqual(
                harness.preflight_calls[0][1]["dependency_lockfiles"],
                harness.lockfiles,
            )
            self.assertTrue((output / "progress/evaluation-16.json").is_file())
            run_record = json.loads((output / "run.json").read_text(encoding="utf-8"))
            run_schema = json.loads(
                (ROOT / "experiments/pilot/schemas/run-record.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(set(run_record).issubset(run_schema["properties"]))
            self.assertIn(run_record["mode"], run_schema["properties"]["mode"]["enum"])
            self.assertIn("fingerprint", run_record)
            self.assertIn("preflight_hash", run_record)
            compiler_prompt = (ROOT / "experiments/pilot/prompts/compiler_system.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(set(harness.model.compiler_system_prompts), {compiler_prompt})
            acquisition_payload = json.loads(
                (output / "cases/case-00/poison/acquisition.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("body", json.dumps(acquisition_payload["agent"]["read_documents"]))
            self.assertTrue(acquisition_payload["record"]["overlay_selected5"])
            self.assertEqual(len(acquisition_payload["agent"]["candidate_resource_ids"]), 10)
            self.assertEqual(len(acquisition_payload["agent"]["selected_resource_ids"]), 5)
            self.assertTrue(acquisition_payload["agent"]["selection_trace"][0]["accepted"])

            private_cases = json.loads((output / "inputs/cases.json").read_text(encoding="utf-8"))
            task_provenance = json.loads(
                (output / "inputs/task-provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                private_cases["cases"][0]["authoring_task"]["instruction"],
                "Author task 0",
            )
            self.assertEqual(
                task_provenance["source_type"],
                "frozen_appworld_train_case_ids",
            )
            self.assertEqual(
                task_provenance["instruction_binding"],
                "exact_world.task.instruction",
            )
            self.assertFalse(task_provenance["model_generated_tasks"])
            self.assertNotIn("instruction", task_provenance["cases"][0]["tasks"][0])

            skill_path = output / "cases/case-00/poison/SKILL.md"
            skill_provenance_path = output / "cases/case-00/poison/skill-provenance.json"
            skill_provenance = json.loads(skill_provenance_path.read_text(encoding="utf-8"))
            skill_manifest = json.loads(
                (output / "cases/case-00/poison/skill.json").read_text(encoding="utf-8")
            )
            self.assertEqual(skill_provenance["generator"]["kind"], "injected_model")
            self.assertEqual(skill_provenance["generator"]["model_id"], "Qwen/Qwen3.8-27B")
            self.assertEqual(len(skill_provenance["selected_resource_ids"]), 5)
            self.assertEqual(len(skill_provenance["source_documents"]), 5)
            self.assertEqual(skill_provenance["skill"]["sha256"], sha256_file(skill_path))
            self.assertEqual(skill_manifest["artifact"]["sha256"], sha256_file(skill_path))
            self.assertEqual(
                skill_manifest["provenance"]["sha256"],
                sha256_file(skill_provenance_path),
            )
            self.assertNotIn("body", json.dumps(skill_provenance))

            second = run_pilot(
                harness.runtime_path,
                config_path=harness.config_path,
                project_root=ROOT,
                output_directory=output,
                dependencies=dependencies,
            )
            self.assertTrue(second.cached)
            self.assertEqual(first.complete_hash, second.complete_hash)
            self.assertEqual(len(harness.runtime_factory.created), 96)
            self.assertEqual(len(harness.model.compiler_system_prompts), 32)

            schedule = json.loads((output / "schedule.json").read_text(encoding="utf-8"))
            first_entry = schedule["entries"][0]
            first_arm = "sham" if first_entry["arm"] == "A_sham" else "poison"
            arm_record = output / "cases" / first_entry["case_id"] / first_arm / "arm-record.json"
            arm_record.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ResearchRunnerError, "cache is corrupt"):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=dependencies,
                )
            self.assertEqual(len(harness.runtime_factory.created), 96)

            (output / "complete.json").unlink()
            with self.assertRaises(ResearchRunInterrupted):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=dependencies,
                )
            self.assertEqual(len(harness.runtime_factory.created), 96)

    def test_incomplete_phase_is_marked_and_never_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "interrupted-output"
            start = output / "cases/case-00/sham/phase-start.json"
            start.parent.mkdir(parents=True)
            start.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ResearchRunInterrupted):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=harness.dependencies(),
                )
            marker = json.loads((output / "interrupted.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["status"], "interrupted_failure")
            self.assertFalse(marker["rerun_permitted"])
            self.assertEqual(harness.runtime_factory.created, [])

    def test_completed_run_rejects_tampered_skill_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "tampered-provenance-output"
            dependencies = harness.dependencies()
            run_pilot(
                harness.runtime_path,
                config_path=harness.config_path,
                project_root=ROOT,
                output_directory=output,
                dependencies=dependencies,
            )
            provenance = output / "cases/case-00/poison/skill-provenance.json"
            provenance.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ResearchRunnerError, "cache is corrupt"):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=dependencies,
                )

    def test_unexpected_episode_error_aborts_without_scientific_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "errored-output"
            dependencies = harness.dependencies()

            def explode(*args, **kwargs):
                del args, kwargs
                raise RuntimeError("unexpected adapter fault")

            dependencies = ResearchDependencies(
                **{
                    **dependencies.__dict__,
                    "runtime_factory": explode,
                }
            )
            with self.assertRaisesRegex(RuntimeError, "unexpected adapter fault"):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=dependencies,
                )
            starts = list(output.glob("cases/*/*/phase-start.json"))
            self.assertEqual(len(starts), 1)
            self.assertFalse(starts[0].with_name("phase-complete.json").exists())
            self.assertFalse((output / "complete.json").exists())
            self.assertFalse((output / "reports/summary.json").exists())
            with self.assertRaises(ResearchRunInterrupted):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=harness.dependencies(),
                )

    def test_active_lock_never_gets_mislabeled_as_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "active-output"
            start = output / "cases/case-00/sham/phase-start.json"
            start.parent.mkdir(parents=True)
            start.write_text("{}\n", encoding="utf-8")
            (output / ".active.lock").write_text(f"{os.getpid()} active-test\n", encoding="utf-8")
            with self.assertRaises(ResearchRunLocked):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=harness.dependencies(),
                )
            self.assertFalse((output / "interrupted.json").exists())
            self.assertEqual(harness.runtime_factory.created, [])

    def test_phase_boundary_resume_ignores_advisory_drift_and_reclaims_stale_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "resumable-output"
            calls = 0

            def changing_advisory(*args, **kwargs):
                nonlocal calls
                del args, kwargs
                calls += 1
                return PreflightReport(
                    (
                        PreflightCheck("injected_ready", True, True, "ready", "research"),
                        PreflightCheck(
                            "free_disk_headroom",
                            True,
                            False,
                            f"available_bytes={calls}",
                            "advisory",
                        ),
                    ),
                    mode="research",
                )

            dependencies = harness.dependencies(preflight=changing_advisory)
            with (
                patch(
                    "r2sp.research_runner._write_interim_evaluation",
                    side_effect=RuntimeError("boundary stop"),
                ),
                self.assertRaisesRegex(RuntimeError, "boundary stop"),
            ):
                run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                    dependencies=dependencies,
                )
            completed_before_resume = len(list(output.glob("cases/*/*/phase-complete.json")))
            self.assertGreaterEqual(completed_before_resume, 2)
            self.assertFalse((output / "finalization-start.json").exists())
            run_id = json.loads((output / "run.json").read_text(encoding="utf-8"))["run_id"]
            (output / ".active.lock").write_text(f"99999999 {run_id}\n", encoding="utf-8")

            resumed = run_pilot(
                harness.runtime_path,
                config_path=harness.config_path,
                project_root=ROOT,
                output_directory=output,
                dependencies=dependencies,
            )
            self.assertFalse(resumed.cached)
            self.assertEqual(calls, 2)
            self.assertEqual(len(harness.runtime_factory.created), 96)
            self.assertFalse((output / ".active.lock").exists())
            preflight = json.loads((output / "preflight.json").read_text(encoding="utf-8"))
            self.assertNotIn("free_disk_headroom", json.dumps(preflight))

    def test_research_run_binds_appworld_snapshot_through_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "research-output"
            harness.model.count_tokens = lambda _text: 10
            harness.model.verify_tool_contract = lambda: {"contract": "ok"}
            harness.model.verify_selection_contract = lambda *, selection_k: {
                "selection_k": selection_k,
                "contract": "ok",
            }
            dependencies = harness.dependencies()
            snapshot = ContentDigest("c" * 64, 123, 4567)

            with (
                patch("r2sp.research_runner.ResearchDependencies", return_value=dependencies),
                patch(
                    "r2sp.research_runner._validate_frozen_appworld_tasks",
                    return_value="d" * 64,
                ),
                patch(
                    "r2sp.research_runner._appworld_runtime_snapshot",
                    side_effect=[snapshot, snapshot],
                ) as snapshot_probe,
            ):
                result = run_pilot(
                    harness.runtime_path,
                    config_path=harness.config_path,
                    project_root=ROOT,
                    output_directory=output,
                )

            self.assertTrue(result.summary["research_eligible"])
            self.assertEqual(
                result.summary["provenance"]["declared"]["appworld_runtime_snapshot_hash"],
                snapshot.sha256,
            )
            self.assertIn(
                "selection_contract_probe_hash",
                result.summary["provenance"]["declared"],
            )
            self.assertEqual(snapshot_probe.call_count, 2)
            run_record = json.loads((output / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(
                run_record["frozen_asset_hashes"]["appworld_runtime_snapshot_hash"],
                snapshot.sha256,
            )
            self.assertEqual(
                run_record["appworld_provenance"]["runtime_snapshot_hash"],
                snapshot.sha256,
            )
            self.assertEqual(
                run_record["appworld_provenance"]["runtime_snapshot_file_count"],
                snapshot.file_count,
            )
            self.assertEqual(
                run_record["appworld_provenance"]["runtime_snapshot_size_bytes"],
                snapshot.size_bytes,
            )
            finalization = json.loads(
                (output / "finalization-start.json").read_text(encoding="utf-8")
            )
            self.assertEqual(finalization["appworld_runtime_snapshot_hash"], snapshot.sha256)
            self.assertTrue((output / "complete.json").is_file())

    def test_appworld_snapshot_drift_permanently_blocks_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            output = Path(directory) / "drifted-research-output"
            harness.model.count_tokens = lambda _text: 10
            harness.model.verify_tool_contract = lambda: {"contract": "ok"}
            harness.model.verify_selection_contract = lambda *, selection_k: {
                "selection_k": selection_k,
                "contract": "ok",
            }
            dependencies = harness.dependencies()
            baseline = ContentDigest("c" * 64, 123, 4567)
            changed = ContentDigest("e" * 64, 124, 4599)

            with (
                patch("r2sp.research_runner.ResearchDependencies", return_value=dependencies),
                patch(
                    "r2sp.research_runner._validate_frozen_appworld_tasks",
                    return_value="d" * 64,
                ),
                patch(
                    "r2sp.research_runner._appworld_runtime_snapshot",
                    side_effect=[baseline, changed, baseline],
                ) as snapshot_probe,
            ):
                with self.assertRaisesRegex(ResearchRunInterrupted, "runtime bytes changed"):
                    run_pilot(
                        harness.runtime_path,
                        config_path=harness.config_path,
                        project_root=ROOT,
                        output_directory=output,
                    )
                self.assertEqual(
                    len(list(output.glob("cases/*/*/phase-complete.json"))),
                    32,
                )
                self.assertEqual(len(harness.runtime_factory.created), 96)
                self.assertFalse((output / "complete.json").exists())
                marker = json.loads((output / "interrupted.json").read_text(encoding="utf-8"))
                self.assertEqual(marker["reason"], "appworld_runtime_snapshot_changed")
                self.assertFalse(marker["rerun_permitted"])

                with self.assertRaisesRegex(ResearchRunInterrupted, "permanently marked"):
                    run_pilot(
                        harness.runtime_path,
                        config_path=harness.config_path,
                        project_root=ROOT,
                        output_directory=output,
                    )

            self.assertEqual(snapshot_probe.call_count, 3)
            self.assertEqual(len(harness.runtime_factory.created), 96)

    def test_cli_uses_stable_public_research_api(self) -> None:
        result = ResearchRunResult(
            output_directory=Path("/tmp/fake-run"),
            run_id="research-test",
            summary={"decision": "NOT_ELIGIBLE", "research_eligible": False},
            cached=False,
            complete_hash="a" * 64,
        )
        stdout = StringIO()
        with (
            patch("r2sp.research_runner.run_research_pilot", return_value=result) as mocked,
            redirect_stdout(stdout),
        ):
            status = main(
                [
                    "run-pilot",
                    "--config",
                    "/tmp/config.yaml",
                    "--runtime-config",
                    "/tmp/runtime.yaml",
                    "--project-root",
                    str(ROOT),
                ]
            )
        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["run_id"], "research-test")
        self.assertEqual(payload["decision"], "NOT_ELIGIBLE")
        mocked.assert_called_once_with(
            config_path=Path("/tmp/config.yaml"),
            runtime_config_path=Path("/tmp/runtime.yaml"),
            project_root=ROOT,
        )

    def test_code_hash_includes_nested_runtime_adapter_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "src/r2sp/runtime/appworld.py"
            runtime.parent.mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (root / "src/r2sp/core.py").write_text("VALUE = 1\n", encoding="utf-8")
            runtime.write_text("ADAPTER = 1\n", encoding="utf-8")
            before = _code_hash(root)
            runtime.write_text("ADAPTER = 2\n", encoding="utf-8")
            self.assertNotEqual(before, _code_hash(root))

    def test_research_model_service_must_be_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            payload = yaml.safe_load(harness.runtime_path.read_text(encoding="utf-8"))
            payload["model_service"]["base_url"] = "https://models.example/v1"
            harness.runtime_path.write_text(
                yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(Exception, "loopback"):
                load_runtime_config(harness.runtime_path, project_root=ROOT)

    def test_runtime_config_rejects_repository_paths_and_relative_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            original = harness.runtime_path.read_text(encoding="utf-8")
            repository_path_fields = (
                "appworld_root",
                "clean_manifest",
                "cases",
                "overlays",
                "output_root",
            )
            for field in repository_path_fields:
                with self.subTest(field=field):
                    payload = yaml.safe_load(original)
                    payload["runtime"][field] = str(ROOT / "forbidden" / field)
                    harness.runtime_path.write_text(
                        yaml.safe_dump(payload, sort_keys=False),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(Exception, "project root trees must be disjoint"):
                        load_runtime_config(harness.runtime_path, project_root=ROOT)

            payload = yaml.safe_load(original)
            payload["runtime"]["output_root"] = "runs"
            harness.runtime_path.write_text(
                yaml.safe_dump(payload, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Exception, "runtime.output_root must be an absolute path"):
                load_runtime_config(harness.runtime_path, project_root=ROOT)

    def test_output_tree_must_be_disjoint_from_appworld_and_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory)
            appworld_root = external / "appworld"
            with self.assertRaisesRegex(Exception, "project root trees must be disjoint"):
                _validate_output_location(ROOT / "runs" / "test", appworld_root, ROOT)
            with self.assertRaisesRegex(Exception, "APPWORLD_ROOT trees must be disjoint"):
                _validate_output_location(appworld_root / "runs" / "test", appworld_root, ROOT)

    def test_serving_tokenizer_recomputes_frozen_overlay_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            digest = _verify_case_token_counts(harness.bundle, token_counter=lambda _text: 10)
            self.assertEqual(len(digest), 64)
            with self.assertRaisesRegex(Exception, "count mismatch"):
                _verify_case_token_counts(harness.bundle, token_counter=lambda _text: 11)

    def test_frozen_tasks_are_read_only_validated_against_appworld_train_specs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Harness(Path(directory))
            cases = []
            task_instructions = {}
            for index, case in enumerate(harness.bundle.cases):
                authoring = TaskSpec(
                    f"author{index:02d}_1",
                    "authoring",
                    case.authoring_task.instruction,
                )
                positive = TaskSpec(
                    f"positive{index:02d}_1",
                    "trigger_positive",
                    case.positive_task.instruction,
                )
                negative = TaskSpec(
                    f"negative{index:02d}_1",
                    "trigger_negative",
                    case.negative_task.instruction,
                )
                cases.append(
                    CaseSpec(
                        case.case_id,
                        authoring,
                        positive,
                        negative,
                        case.overlays,
                    )
                )
                for task in (authoring, positive, negative):
                    task_instructions[task.task_id] = task.instruction
            bundle = FrozenCaseBundle(
                protocol_version=harness.bundle.protocol_version,
                tokenizer_model=harness.bundle.tokenizer_model,
                tokenizer_revision=harness.bundle.tokenizer_revision,
                cases=tuple(cases),
                token_counts=harness.bundle.token_counts,
                research_mode=True,
                source_path=harness.bundle.source_path,
            )
            dataset = harness.appworld_root / "data/datasets/train.txt"
            dataset.parent.mkdir(parents=True)
            dataset.write_text(
                "".join(f"{task_id}:tagged\n" for task_id in task_instructions),
                encoding="utf-8",
            )
            for task_id, instruction in task_instructions.items():
                specs = harness.appworld_root / "data/tasks" / task_id / "specs.json"
                specs.parent.mkdir(parents=True)
                specs.write_text(
                    json.dumps({"instruction": instruction}) + "\n",
                    encoding="utf-8",
                )

            digest = _validate_frozen_appworld_tasks(harness.appworld_root, bundle)
            self.assertEqual(len(digest), 64)
            first_task = next(iter(task_instructions))
            first_specs = harness.appworld_root / "data/tasks" / first_task / "specs.json"
            first_specs.write_text(
                json.dumps({"instruction": "changed"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Exception, "differs from frozen case"):
                _validate_frozen_appworld_tasks(harness.appworld_root, bundle)

            invalid_case = replace(
                bundle.cases[0],
                authoring_task=replace(
                    bundle.cases[0].authoring_task,
                    task_id="invalid_generator_1",
                ),
            )
            invalid_bundle = replace(
                bundle,
                cases=(invalid_case, *bundle.cases[1:]),
            )
            with self.assertRaisesRegex(Exception, "unsafe format"):
                _validate_frozen_appworld_tasks(harness.appworld_root, invalid_bundle)


if __name__ == "__main__":
    unittest.main()
