"""Facade evidence/selection hooks only; native control branches are tested separately."""

import asyncio
import contextlib
import contextvars
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution import skillsbench_evolution as facade
from tau_skill_evolution.artifacts import FrozenBase, SkillBundle
from tau_skill_evolution.author_verifier import author_module
from tau_skill_evolution.container import ProcessResult
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded


@pytest.fixture
def mapped_run(tmp_path, monkeypatch):
    original = author_module(
        "agents.terminus_2.harbor_terminus_2_evolution"
    ).HarborTerminus2Evolution
    verification = author_module("evolution.models").VerificationResult
    initial = SkillBundle(
        {
            "SKILL.md": "---\nname: evo-current\ndescription: Fixture.\n---\nA\n",
            "scripts/main.py": "print('public')\n",
            "references/context.md": "Full sealed reference.\n",
        }
    )
    base = FrozenBase((), {"opening": "Public task fixture."})
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.toml").write_text("version='1.0'\n")
    memory = SimpleNamespace(
        files=dict(initial.files),
        suite="def test_a(): assert True\n",
        agents=[],
        oracle_calls=[],
        generator_calls=[],
        scenario=None,
        reward=1.0,
        parent_checks=0,
        partial_exports=[],
    )

    @contextlib.contextmanager
    def workspace():
        yield {}

    runner = SimpleNamespace(
        task_directory=task,
        snapshot_workspace=workspace,
        phase_remaining=lambda: 7200,
        author_exec=lambda *_args, **_kwargs: ProcessResult(0, memory.suite.encode()),
    )

    def oracle(bundle, *, phase):
        memory.oracle_calls.append((bundle, phase))
        return {
            "status": "MEASURED",
            "passed": memory.reward == 1.0,
            "canonical_reward": memory.reward,
            "resolved_reward": memory.reward,
            "tests_passed": int(memory.reward == 1.0),
            "total_tests": 1,
            "test_details": [{"name": "PRIVATE_GT_NAME", "status": "failed"}],
            "bundle_hash": bundle.bundle_hash,
            "parent_hash": bundle.parent_hash,
            "phase": phase,
        }

    adapter = SimpleNamespace(
        task_id="fixture",
        oracle=oracle,
        _seal_public_workspace=lambda *_args, **_kwargs: {"public_artifacts_hash": "fixture"},
    )
    session = SimpleNamespace(
        adapter=adapter,
        runner=runner,
        files=lambda: dict(memory.files),
        snapshot=lambda: {"candidate_manifest": dict(memory.files)},
        state={"execution_id": "fixture-learning"},
        record_tool_result=None,
    )
    memory.session = session

    class Parent:
        def __init__(self, *, logs_dir, **_kwargs):
            self.logs_dir = Path(logs_dir)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            self._exit_reason = "fixture"
            self._host_intervention_count = self._surrogate_retry_count = 0
            self._intervention_history = []
            self.report = verification(source="script", total_tests=1, tests_passed=1)

            async def verify(*_args, **_kwargs):
                return self.report

            self._verifier = SimpleNamespace(verify=verify)
            self._independent_verifier = SimpleNamespace(generate_and_run=verify)
            memory.agents.append(self)

        async def setup(self, _environment):
            pass

        async def run(self, _instruction, environment, _context):
            await memory.scenario(self, environment)
            self._write_evolution_log(gt_oracle_result={})

        async def _check_episode_exit(self, **_kwargs):
            memory.parent_checks += 1
            return "schema_repair_fixture" if "SKILL.md" not in memory.files else None

        async def _record_intervention(self, *_args, **_kwargs):
            entry = {"surrogate_result": self.report.to_dict()}
            self._intervention_history.append(entry)
            return entry

        async def _export_skills_from_container(
            self, _environment, skill_names, target_dir, include_references=False
        ):
            # The unchanged author exporter writes SKILL.md/scripts and optionally
            # references. The local transport hook must retain all safe files.
            memory.partial_exports.append((target_dir, include_references))
            for name in skill_names:
                for path, content in memory.files.items():
                    if (
                        path == "SKILL.md"
                        or path.startswith("scripts/")
                        or (include_references and path.startswith("references/"))
                    ):
                        destination = target_dir / name / path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(content)
            return sorted(skill_names)

        def _write_evolution_log(self, **_kwargs):
            (self.logs_dir / "evolution_run_log.json").write_text('{"best_gt_snapshot":null}')

        _rollback_host_skills = original._rollback_host_skills
        _gt_full_score_and_reward = staticmethod(original._gt_full_score_and_reward)

    monkeypatch.setattr(
        facade, "author_module", lambda _name: SimpleNamespace(HarborTerminus2Evolution=Parent)
    )
    generator = SimpleNamespace(
        config=SimpleNamespace(model="fixture-generator"),
        complete=lambda *_args, **_kwargs: memory.generator_calls.append(True),
    )
    verifier = SimpleNamespace(config=SimpleNamespace(model="fixture-verifier"))
    journal = Journal(tmp_path / "journal", identity={"scope": "facade_mapping_only"})

    def run(scenario):
        memory.scenario = scenario
        return facade.run_author_evolution(
            session,
            initial,
            base,
            generator,
            verifier,
            journal=journal,
            root=tmp_path / "result",
            token_counter=lambda value: len(value) // 4,
            settings={"max_input_tokens": 200000, "context_window": 272000, "max_episodes": 8},
            deadline=time.time() + 300,
            adapter_prompt="Public fixture adapter.",
        )

    def export(bundle, name):
        parent = tmp_path / name
        for path, content in bundle.files.items():
            target = parent / "evo-current" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return parent

    memory.export = export
    return run, memory, initial, journal


async def submit(agent, environment, episode):
    return await agent._check_episode_exit(
        episode=episode, result=SimpleNamespace(is_task_complete=True), environment=environment
    )


@pytest.mark.parametrize("window,expected", [(258400, 258400), (400000, 272000)])
def test_actual_provider_context_reaches_original_episode_budget_hook(mapped_run, window, expected):
    run, memory, _initial, _journal = mapped_run

    class Chat:
        _last_input_tokens = 12000

        @property
        def last_input_tokens(self):
            return self._last_input_tokens

    async def scenario(agent, environment):
        agent._chat = Chat()
        agent._llm.last_context_budget = {
            "context_window": window,
            "input_tokens": 185730,
            "output_tokens": 2096,
            "reserve_tokens": 32768,
        }
        await submit(agent, environment, 1)
        assert memory.parent_checks == 1
        assert agent._chat.last_input_tokens == 220594
        assert agent._get_max_context_tokens() == expected
        assert agent._chat.last_input_tokens >= expected * 0.7

    run(scenario)


@pytest.mark.parametrize("final_log_available", [True, False])
def test_known_predispatch_stop_requires_native_finalization(mapped_run, final_log_available):
    run, memory, initial, journal = mapped_run

    async def scenario(agent, environment):
        owner = agent._llm.run.owner
        owner.max_input_tokens = 1
        try:
            agent._llm.call("Too large; never dispatched")
        except InputTokenBudgetExceeded as error:
            assert agent._exit_reason == "token_budget"
            # Model the unchanged author's catch -> post-final -> rethrow order.
            await agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=memory.export(initial, "final"),
                oracle_label="gt-oracle-final",
            )
            if final_log_available:
                (agent.logs_dir / "evolution_run_log.json").write_text(
                    '{"best_gt_snapshot":null,"timing":{"exit_reason":"token_budget",'
                    '"interrupted_by":"InputTokenBudgetExceeded"}}'
                )
            raise error

    if not final_log_available:
        with pytest.raises(UnknownOperation):
            run(scenario)
        assert not journal.completed("published-author-controller")
    else:
        result = run(scenario)
        assert result.stop_reason == "token_budget"
        assert result.oracle_history[0]["phase"] == "post_final"
        assert journal.completed("published-author-controller")
    assert not memory.generator_calls and len(memory.oracle_calls) == 1


def test_success_retains_references_despite_native_partial_host_export(mapped_run):
    run, memory, initial, journal = mapped_run

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        gt = await agent._run_gt_oracle_check(
            "Public task", environment, evolved_skills_dir=memory.export(initial, "gt")
        )
        assert gt["test_details"] == []  # Private official check names are not returned.
        # The published final host importer only writes SKILL.md and scripts.
        host = environment.environment_dir / "skills" / "evo-current"
        host.mkdir(parents=True)
        (host / "SKILL.md").write_text(initial.files["SKILL.md"])
        agent._exit_reason = "gt_oracle_pass"

    result = run(scenario)
    assert result.final_bundle.to_dict() == initial.to_dict()
    assert len(result.versions) == 1
    assert result.best_oracle_ref["bundle_hash"] == initial.bundle_hash
    assert result.oracle_history[0]["test_details"][0]["name"] == "PRIVATE_GT_NAME"
    assert journal.completed("published-author-controller")
    assert run(scenario).to_dict() == result.to_dict()
    assert len(memory.agents) == len(memory.oracle_calls) == 1


@pytest.mark.parametrize("with_attachments", [False, True])
def test_native_partial_export_is_completed_before_gt_best_and_rollback(
    mapped_run, with_attachments
):
    run, memory, initial, _journal = mapped_run
    full = SkillBundle(
        {
            **initial.files,
            **(
                {
                    "evals/evals.json": '{"evals": [{"prompt": "Public example"}]}\n',
                    "assets/schema.csv": "column,type\nvalue,float\n",
                    "scripts/run.sh": "#!/bin/sh\npython3 scripts/main.py\n",
                    "README.md": "Public usage.\n",
                }
                if with_attachments
                else {}
            ),
        }
    )

    async def scenario(agent, environment):
        memory.files = dict(full.files)
        await submit(agent, environment, 1)
        exported = environment.environment_dir / "gt-export"
        names = await agent._export_skills_from_container(
            environment, {"evo-current"}, exported, include_references=False
        )
        assert names == ["evo-current"]
        directory = exported / "evo-current"
        assert {
            p.relative_to(directory).as_posix(): p.read_text()
            for p in directory.rglob("*")
            if p.is_file()
        } == full.files
        assert not (directory / "manifest.json").exists()
        await agent._run_gt_oracle_check("Public task", environment, evolved_skills_dir=exported)
        memory.files = {**full.files, "SKILL.md": full.files["SKILL.md"] + "Later draft.\n"}
        await submit(agent, environment, 2)
        agent._rollback_host_skills(environment, exported)

    result = run(scenario)
    assert len(memory.partial_exports) == 1
    scored = memory.oracle_calls[0][0]
    assert scored.bundle_hash == full.bundle_hash
    assert scored.files == full.files
    assert result.best_oracle_ref["bundle_hash"] == full.bundle_hash
    assert result.final_bundle_hash == full.bundle_hash
    assert result.final_bundle.files == full.files
    assert result.best_snapshot["rollback"]["status"] == "COMPLETED"


def test_unknown_gt_latches_after_native_catch_and_blocks_all_later_dispatch(mapped_run):
    run, memory, initial, journal = mapped_run
    blocked = []

    async def scenario(agent, environment):
        await submit(agent, environment, 1)

        def unknown(*_args, **_kwargs):
            memory.oracle_calls.append("UNKNOWN_FIXTURE")
            raise UnknownOperation("gt_fixture_unknown")

        # This is host dispatch failure, caught by the stub as the author catches it.
        original_oracle = memory.export(initial, "gt")
        memory.session.adapter.oracle = unknown
        with pytest.raises(UnknownOperation):
            await agent._run_gt_oracle_check(
                "Public task", environment, evolved_skills_dir=original_oracle
            )
        for action in (
            lambda: agent._llm.call("Do not dispatch after UNKNOWN."),
            lambda: environment.exec("Do not dispatch after UNKNOWN."),
            lambda: agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=original_oracle,
                oracle_label="gt-oracle-final",
            ),
        ):
            with pytest.raises(UnknownOperation):
                value = action()
                if hasattr(value, "__await__"):
                    await value
            blocked.append(True)

    with pytest.raises(UnknownOperation):
        run(scenario)
    assert len(blocked) == 3
    assert memory.generator_calls == []
    assert memory.oracle_calls == ["UNKNOWN_FIXTURE"]
    assert journal.status("author-gt-0") == "UNKNOWN"
    with pytest.raises(UnknownOperation, match="requires_new_trial"):
        run(scenario)


def test_original_passed_reports_and_suite_aba_keep_content_version_ids(mapped_run):
    run, memory, _initial, journal = mapped_run

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        for suite in (
            "def test_a(): assert True\n",
            "def test_b(): assert 1 == 1\n",
            "def test_a(): assert True\n",
        ):
            memory.suite = suite
            await agent._verifier.verify(environment)
            await agent._record_intervention(environment, trigger="mapping_fixture")

    result = run(scenario)
    assert [check["test_version"] for check in result.verifications] == [1, 2, 1]
    assert all(
        check["passed"] and check["author_result"]["error"] is None
        for check in result.verifications
    )
    assert [check["author_result"]["tests_passed"] for check in result.verifications] == [1, 1, 1]
    assert journal.completed("author-verification-source-0-verify")
    assert journal.completed("author-verification-source-1-verify")
    assert journal.completed("author-verification-source-2-verify")


def test_aba_best_snapshot_retains_scored_parent_and_initial_has_no_parent(mapped_run):
    run, memory, initial, _journal = mapped_run
    b = SkillBundle({**initial.files, "SKILL.md": initial.files["SKILL.md"] + "B\n"})
    c = SkillBundle({**initial.files, "SKILL.md": initial.files["SKILL.md"] + "C\n"})

    async def scenario(agent, environment):
        for episode, (bundle, reward) in enumerate(
            ((initial, 0.1), (b, 0.2), (initial, 0.75), (c, 0.3)), 1
        ):
            memory.files = dict(bundle.files)
            await submit(agent, environment, episode)
            memory.reward = reward
            await agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=memory.export(bundle, f"gt-{episode}"),
            )
        agent._rollback_host_skills(environment, memory.export(initial, "best"))

    result = run(scenario)
    assert len(result.versions) == 3
    assert result.versions[0].bundle_hash == initial.bundle_hash
    assert result.versions[0].parent_hash is None
    assert result.final_bundle_hash == initial.bundle_hash
    assert result.final_bundle.parent_hash == b.bundle_hash
    assert result.best_oracle_ref["resolved_reward"] == 0.75
    assert result.best_oracle_ref["parent_hash"] == b.bundle_hash
    assert result.best_snapshot["rollback"]["status"] == "COMPLETED"


def test_invalid_draft_is_not_sealed_and_parent_schema_can_repair(mapped_run):
    run, memory, initial, _journal = mapped_run

    async def scenario(agent, environment):
        memory.files = {"scripts/draft.py": "print('incomplete')\n"}
        assert await submit(agent, environment, 1) == "schema_repair_fixture"
        memory.files = dict(initial.files)
        await submit(agent, environment, 2)

    result = run(scenario)
    assert memory.parent_checks == 2
    assert len(result.versions) == len(result.submissions) == 1
    assert result.versions[0].to_dict() == initial.to_dict()
    assert result.attempts[0]["status"] == "invalid"
    assert result.attempts[0]["parent_hash"] == initial.bundle_hash


def test_original_copytree_failure_does_not_claim_successful_rollback(
    mapped_run, monkeypatch, caplog
):
    run, memory, initial, _journal = mapped_run
    b = SkillBundle({**initial.files, "SKILL.md": initial.files["SKILL.md"] + "B\n"})

    async def scenario(agent, environment):
        for episode, (bundle, reward) in enumerate(((initial, 0.75), (b, 0.3)), 1):
            memory.files = dict(bundle.files)
            await submit(agent, environment, episode)
            memory.reward = reward
            await agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=memory.export(bundle, f"gt-{episode}"),
            )

        def fail(*_args, **_kwargs):
            raise OSError("fixture-copytree-failed")

        monkeypatch.setattr(shutil, "copytree", fail)
        agent._rollback_host_skills(environment, memory.export(initial, "best"))

    result = run(scenario)
    assert result.best_oracle_ref["bundle_hash"] == initial.bundle_hash
    assert result.best_snapshot["rollback"]["status"] == "FAILED"
    assert result.final_bundle_hash == b.bundle_hash
    assert result.final_bundle.parent_hash == initial.bundle_hash
    assert "fixture-copytree-failed" in caplog.text


def test_invalid_file_after_valid_submission_does_not_preempt_parent_intervention(mapped_run):
    run, memory, initial, journal = mapped_run

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        read_files = memory.session.files

        def invalid_files():
            raise ValueError("non_utf8_package_file: scripts/draft.py")

        memory.session.files = invalid_files
        entry = await agent._record_intervention(environment, trigger="schema_repair_fixture")
        assert entry in agent._intervention_history
        memory.session.files = read_files

    result = run(scenario)
    assert len(result.versions) == len(result.submissions) == 1
    assert result.final_bundle.to_dict() == initial.to_dict()
    assert result.attempts[0]["status"] == "invalid"
    assert journal.completed("published-author-controller")


def test_unsealed_draft_public_suite_is_not_attributed_to_the_last_valid_parent(mapped_run):
    run, memory, initial, _journal = mapped_run

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        memory.files = {"scripts/draft.py": "print('incomplete')\n"}
        await agent._verifier.verify(environment)
        await agent._record_intervention(environment, trigger="schema_repair_fixture")
        memory.files = dict(initial.files)

    result = run(scenario)
    assert len(result.versions) == 1
    assert result.final_bundle.to_dict() == initial.to_dict()
    assert len(result.verifications) == 1
    check = result.verifications[0]
    assert check["bundle_hash"] is None
    assert check["passed"] is None
    assert check["failure"] == "invalid_candidate"
    assert check["candidate_status"] == "UNSEALED"
    assert check["author_result"]["tests_passed"] == 1
    assert check["author_result"]["total_tests"] == 1
    assert check["author_result"]["pass_rate"] == 1.0


@pytest.mark.parametrize("method", ["verify", "generate_and_run"])
def test_invalid_candidate_snapshot_is_audited_without_blocking_verifier(mapped_run, method):
    run, memory, initial, journal = mapped_run

    async def scenario(agent, environment):
        await submit(agent, environment, 1)

        def invalid_snapshot():
            raise ValueError("candidate_special_file_fixture")

        memory.session.snapshot = invalid_snapshot
        component = agent._verifier if method == "verify" else agent._independent_verifier
        value = await getattr(component, method)(environment)
        assert value.tests_passed == 1

    result = run(scenario)
    assert result.final_bundle.to_dict() == initial.to_dict()
    changes = journal.response(f"author-verification-source-0-{method}")
    assert (
        changes["before"]
        == changes["after"]
        == {"invalid_candidate": "candidate_special_file_fixture"}
    )
    assert not changes["changed"]


def test_post_final_best_snapshot_uses_the_scored_parent_after_aba(mapped_run):
    run, memory, initial, _journal = mapped_run
    b = SkillBundle({**initial.files, "SKILL.md": initial.files["SKILL.md"] + "B\n"})
    c = SkillBundle({**initial.files, "SKILL.md": initial.files["SKILL.md"] + "C\n"})

    async def scenario(agent, environment):
        for episode, (bundle, reward) in enumerate(
            ((initial, 0.1), (b, 0.2), (initial, 0.75), (c, 0.3)), 1
        ):
            memory.files = dict(bundle.files)
            await submit(agent, environment, episode)
            memory.reward = reward
            await agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=memory.export(bundle, f"gt-{episode}"),
            )
        memory.reward = 0.4
        await agent._run_gt_oracle_check(
            "Public task",
            environment,
            evolved_skills_dir=memory.export(initial, "best-post-final"),
            oracle_label="gt-oracle-final",
        )

    result = run(scenario)
    measured, phase = memory.oracle_calls[-1]
    assert phase == "post_final"
    assert measured.bundle_hash == initial.bundle_hash
    assert measured.parent_hash == b.bundle_hash
    assert result.oracle_history[-1]["parent_hash"] == b.bundle_hash
    assert result.oracle_history[-1]["resolved_reward"] == 0.4
    assert result.best_oracle_ref["resolved_reward"] == 0.75
    assert result.versions[0].parent_hash is None
    assert len(result.versions) == 3


@pytest.mark.parametrize(
    "failure",
    ["missing_export", "multiple_packages", "non_utf8", "special_file", "unsealed_content"],
)
def test_gt_pre_dispatch_failure_is_fatal_after_native_catch(mapped_run, failure):
    run, memory, initial, journal = mapped_run
    blocked = []

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        exported = memory.export(initial, "gt")
        if failure == "missing_export":
            exported = None
        elif failure == "multiple_packages":
            (exported / "evo-other").mkdir()
        elif failure == "non_utf8":
            (exported / "evo-current/assets").mkdir()
            (exported / "evo-current/assets/image.bin").write_bytes(b"\xff\x00")
        elif failure == "special_file":
            (exported / "evo-current/assets").symlink_to(exported.parent, target_is_directory=True)
        else:
            (exported / "evo-current/SKILL.md").write_text(
                initial.files["SKILL.md"] + "Unsubmitted.\n"
            )
        # Simulate the native controller catching a GT exception. Every later
        # actor must still see the fatal bridge state, without a model/GT call.
        with pytest.raises(ValueError):
            await agent._run_gt_oracle_check(
                "Public task", environment, evolved_skills_dir=exported
            )
        for action in (
            lambda: agent._llm.call("Do not dispatch after failed package admission."),
            lambda: environment.exec("Do not dispatch after failed package admission."),
            lambda: agent._run_gt_oracle_check(
                "Public task",
                environment,
                evolved_skills_dir=exported,
                oracle_label="gt-oracle-final",
            ),
        ):
            with pytest.raises(ValueError):
                value = action()
                if hasattr(value, "__await__"):
                    await value
            blocked.append(True)

    with pytest.raises(UnknownOperation) as exc:
        run(scenario)
    assert isinstance(exc.value.__cause__, ValueError)
    assert len(blocked) == 3
    assert memory.generator_calls == memory.oracle_calls == []
    assert journal.status("author-gt-0") == "NOT_SENT"
    assert journal.status("published-author-controller") == "UNKNOWN"


@pytest.mark.parametrize("failure", ["partial_mismatch", "write_error", "candidate_changed"])
def test_export_completion_failure_blocks_all_later_dispatch(mapped_run, monkeypatch, failure):
    run, memory, initial, journal = mapped_run
    blocked = []

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        target = environment.environment_dir / "export"
        full = {**initial.files, "evals/evals.json": '{"evals": []}\n'}
        if failure == "partial_mismatch":
            full["SKILL.md"] += "Changed during native export.\n"
        reads = 0

        def files():
            nonlocal reads
            reads += 1
            if failure == "candidate_changed" and reads > 1:
                return {**full, "README.md": "Changed during completion.\n"}
            return dict(full)

        memory.session.files = files
        if failure == "write_error":
            original_write = Path.write_text

            def write(path, *args, **kwargs):
                if path == target / "evo-current/evals/evals.json":
                    raise OSError("fixture-package-write-failed")
                return original_write(path, *args, **kwargs)

            monkeypatch.setattr(Path, "write_text", write)
        with pytest.raises((ValueError, OSError)):
            await agent._export_skills_from_container(
                environment, {"evo-current"}, target, include_references=True
            )
        for action in (
            lambda: agent._llm.call("Do not dispatch after inconsistent export."),
            lambda: environment.exec("Do not dispatch after inconsistent export."),
            lambda: agent._run_gt_oracle_check(
                "Public task", environment, evolved_skills_dir=target
            ),
        ):
            with pytest.raises((ValueError, OSError)):
                value = action()
                if hasattr(value, "__await__"):
                    await value
            blocked.append(True)

    with pytest.raises(UnknownOperation) as exc:
        run(scenario)
    assert isinstance(exc.value.__cause__, (ValueError, OSError))
    assert len(blocked) == 3
    assert memory.generator_calls == memory.oracle_calls == []
    assert journal.status("author-gt-0") == "NOT_SENT"


def test_native_async_controller_can_call_sync_oracle_with_its_own_event_loop(mapped_run):
    from tau_skill_evolution.author_verifier import _RUN

    run, memory, initial, journal = mapped_run
    marker = contextvars.ContextVar("test_oracle_task_scope")
    observed = []
    original_oracle = memory.session.adapter.oracle

    async def scenario(agent, environment):
        await submit(agent, environment, 1)
        controller_thread = threading.get_ident()
        author_scope = _RUN.get()
        token = marker.set("fixture-task-only")

        def oracle(bundle, *, phase):
            observed.append((threading.get_ident(), _RUN.get(), marker.get()))

            async def fresh_codex_runtime():
                return original_oracle(bundle, phase=phase)

            pending = fresh_codex_runtime()
            try:
                return asyncio.run(pending)
            except BaseException:
                pending.close()
                raise

        memory.session.adapter.oracle = oracle
        try:
            value = await agent._run_gt_oracle_check(
                "Public task", environment, evolved_skills_dir=memory.export(initial, "gt")
            )
        finally:
            marker.reset(token)
        assert value["passed"]
        assert len(observed) == 1
        worker_thread, inherited_author_scope, inherited_marker = observed[0]
        assert worker_thread != controller_thread
        assert inherited_author_scope is author_scope
        assert inherited_marker == "fixture-task-only"
        assert _RUN.get() is author_scope

    result = run(scenario)
    assert result.oracle_calls == 1
    assert memory.oracle_calls == [(initial, "normal")]
    assert journal.completed("author-gt-0")
    assert journal.completed("published-author-controller")
