"""Known pre-dispatch limits preserve public work without masking unknown POSTs."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.journal import UnknownOperation
from tau_skill_evolution.model import (
    CredentialError,
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
)
from tau_skill_evolution.skillsbench import SkillsBenchAdapter


@pytest.fixture
def partial_executor(tmp_path):
    counts = iter((1, 101))
    client = OpenAICompatibleClient(
        "https://bedrock-mantle.us-east-1.api.aws/openai/v1",
        api_key="offline-only",
        config=GenerationConfig(
            model="openai.gpt-5.5",
            transport="bedrock-responses",
            max_input_tokens=100,
        ),
        token_counter=SimpleNamespace(count=lambda *_args, **_kwargs: next(counts)),
    )
    posts = []

    def send(request):
        posts.append(request)
        body = {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "write-public-output",
                    "name": "run_terminal_command",
                    "arguments": '{"command":"write output"}',
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
        return 200, json.dumps(body).encode()

    client._send = send
    work = tmp_path / "work"
    work.mkdir()
    episode = SimpleNamespace(work=work)
    phases = []

    @contextmanager
    def fresh_episode(_bundle):
        phases.append("episode")
        try:
            yield episode
        finally:
            phases.append("cleaned")

    def terminal(_episode, **_kwargs):
        (work / "result.json").write_text('{"public_result":42}')
        return ProgramResult(0, output="PRIVATE_EXECUTION_OUTPUT")

    def close_public(_episode):
        assert list((tmp_path / "artifacts").glob("*/snapshot.json"))
        phases.append("closed")

    def grade(_episode):
        assert phases[-1] == "closed"
        phases.append("graded")
        report = {
            "results": {
                "summary": {"tests": 1, "passed": 0, "failed": 1},
                "tests": [{"name": "PRIVATE_GRADER_CHECK", "status": "failed"}],
            }
        }
        evidence = Path(_episode.grader_evidence_dir)
        evidence.mkdir(parents=True)
        contents = {
            "reward.txt": b"0",
            "ctrf.json": json.dumps(report).encode(),
            "stdout.bin": b"private grader output",
            "stderr.bin": b"",
        }
        for name, content in contents.items():
            (evidence / name).write_bytes(content)
        (evidence / "evidence.json").write_text(
            json.dumps(
                {
                    "grader_exit_code": 1,
                    "process_failure": None,
                    "identity": _episode.grader_identity,
                    "files": {
                        name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                        for name, content in contents.items()
                    },
                    "official_items": report["results"]["tests"],
                }
            )
        )
        return {
            "status": "MEASURED",
            "utility": False,
            "reward": 0.0,
            "official_checks": {"status": "MEASURED", "passed": 0, "total": 1, "rate": 0.0},
        }

    adapter = SkillsBenchAdapter.__new__(SkillsBenchAdapter)
    adapter.executor = "local-tools"
    adapter.spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 3,
                "controls": {
                    "assistant_completion_budget": 30,
                    "agent": {"max_output_tokens": 10},
                },
            }
        },
    )
    adapter.task_id = "public-partial-trace"
    adapter.public_inputs = {"opening": "Produce a public result."}
    adapter.model_factory = lambda _role: client
    adapter.runner = SimpleNamespace(
        config={"agent": {"timeout_sec": 60}},
        use_bwrap=True,
        workspace_directory="/app",
        terminal=terminal,
        episode=fresh_episode,
        close_public=close_public,
        grade=grade,
        phase_remaining=lambda: 300,
        _official_report_name=lambda: "ctrf.json",
    )
    adapter.artifact_root = tmp_path / "artifacts"
    adapter.model_journal_dir = tmp_path / "private-models"
    bundle = SkillBundle({"SKILL.md": "PRIVATE_SKILL_SOURCE"})
    return SimpleNamespace(
        adapter=adapter, bundle=bundle, client=client, posts=posts, phases=phases
    )


@pytest.mark.parametrize("wrapped", [False, True])
def test_unsent_input_limit_seals_partial_public_trace_and_app_snapshot(partial_executor, wrapped):
    setup = partial_executor
    if wrapped:
        complete = setup.client.complete_journaled

        def wrapped_complete(*args, **kwargs):
            try:
                return complete(*args, **kwargs)
            except ModelClientError as exc:
                raise UnknownOperation("wrapped admission failure") from exc

        setup.client.complete_journaled = wrapped_complete
    trace = setup.adapter.rollout(setup.bundle)
    assert trace["termination_reason"] == "input_token_budget_exhausted"
    assert trace["termination_metadata"] == {
        "error_code": "input_token_budget_exceeded",
        "input_request_status": "NOT_SENT",
        "observed_input_tokens": 101,
        "max_input_tokens": 100,
    }
    assert trace["assistant_completion_tokens"] == 2 and trace["tool_calls"] == 1
    assert trace["events"] == [
        {
            "type": "tool_status",
            "name": "run_terminal_command",
            "exit_code": 0,
            "failure": None,
            "status": "returned",
        }
    ]
    assert len(setup.posts) == 1
    assert trace["public_artifacts"][0]["sandbox_path"] == "/app/result.json"
    files = Path(trace["public_artifacts_dir"])
    assert (files / "app/result.json").read_text() == '{"public_result":42}'
    assert "PRIVATE_EXECUTION_OUTPUT" not in json.dumps(trace)
    assert "PRIVATE_SKILL_SOURCE" not in json.dumps(trace)
    failures = list(setup.adapter.model_journal_dir.glob("*/*/failure.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())["error_code"] == "input_token_budget_exceeded"
    assert json.loads(failures[0].with_name("state.json").read_text())["status"] == "NOT_SENT"
    assert not failures[0].with_name("raw-response.json").exists()
    assert setup.phases == ["episode", "cleaned"]
    from tau_skill_evolution.verifier import SurrogateVerifier

    verifier_input = SurrogateVerifier._payload({}, {}, trace, None, "initial")
    assert verifier_input["public_trace"]["termination_reason"] == trace["termination_reason"]
    assert "public_artifacts_dir" not in verifier_input["public_trace"]


@pytest.mark.parametrize("phase", ["oracle", "evaluate"])
def test_input_limit_keeps_official_grading_of_known_partial_work(partial_executor, phase):
    setup = partial_executor
    result = getattr(setup.adapter, phase)(setup.bundle)
    assert setup.phases == ["episode", "closed", "graded", "cleaned"]
    assert len(setup.posts) == 1
    if phase == "oracle":
        assert result["status"] == "MEASURED" and result["passed"] is False
        assert result["canonical_reward"] == result["resolved_reward"] == 0
        assert result["tests_passed"] == 0 and result["total_tests"] == 1
        assert result["bundle_hash"] == setup.bundle.bundle_hash and result["parent_hash"] is None
        evidence = Path(result["grader_evidence_ref"])
        assert result["grader_evidence_hash"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
        assert result["test_details"] == [{"name": "PRIVATE_GRADER_CHECK", "status": "failed"}]
    else:
        assert result["status"] == "MEASURED" and result["reward"] == 0.0
        assert result["execution_termination_reason"] == "input_token_budget_exhausted"
    for path in setup.adapter.artifact_root.rglob("*.json"):
        public = path.read_text()
        assert "PRIVATE_GRADER_CHECK" not in public and "PRIVATE_EXECUTION_OUTPUT" not in public


@pytest.mark.parametrize("failure", ["transport", "budget_during_send", "auth", "invalid"])
def test_dispatched_or_invalid_failure_is_never_converted_to_partial_success(
    partial_executor, failure
):
    setup = partial_executor
    sends = []

    def send(_request):
        sends.append(1)
        if failure == "auth":
            return 401, b"{}"
        if failure == "invalid":
            return 200, b"not json"
        code = (
            "input_token_budget_exceeded" if failure == "budget_during_send" else "transport_error"
        )
        raise ModelClientError(code, "private failure details")

    setup.client._send = send
    expected = (
        UnknownOperation if failure in {"transport", "budget_during_send"} else ModelClientError
    )
    with pytest.raises(expected):
        setup.adapter.rollout(setup.bundle)
    assert sends == [1]
    assert not setup.adapter.artifact_root.exists()
    assert setup.phases == ["episode", "cleaned"]


def test_missing_credential_is_not_an_input_budget_termination(partial_executor):
    setup = partial_executor

    def missing():
        raise CredentialError("credential_unavailable", "private credential information")

    setup.client.api_key = missing
    with pytest.raises(CredentialError):
        setup.adapter.rollout(setup.bundle)
    assert setup.posts == [] and not setup.adapter.artifact_root.exists()
    assert setup.phases == ["episode", "cleaned"]
