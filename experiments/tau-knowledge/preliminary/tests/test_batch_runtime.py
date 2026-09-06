from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from r2sp_common import RunStatus
from r2sp_tau_knowledge import batch_runtime
from r2sp_tau_knowledge.batch_constants import MODEL_ID, MODEL_REVISION
from r2sp_tau_knowledge.batch_gpu_gate import GpuGateError, GpuGateLock
from r2sp_tau_knowledge.batch_official_worker import run_request
from r2sp_tau_knowledge.batch_outcomes import AcquisitionOutcome
from r2sp_tau_knowledge.batch_runtime import (
    DIAGNOSTIC_MODEL_ID,
    DIAGNOSTIC_MODEL_REVISION,
    BatchBackend,
    BatchRuntime,
    validate_batch_model,
)
from r2sp_tau_knowledge.batch_services import LiveInfrastructureError


def _model(*, diagnostic: bool = False) -> dict:
    return {
        "id": DIAGNOSTIC_MODEL_ID if diagnostic else MODEL_ID,
        "revision": DIAGNOSTIC_MODEL_REVISION if diagnostic else MODEL_REVISION,
        "endpoint": "http://127.0.0.1:18140/v1" if diagnostic else "http://127.0.0.1:18138/v1",
        "max_context_tokens": 65536,
    }


def test_creation_and_evaluation_models_are_independent_without_service_calls() -> None:
    creator = BatchBackend(phase="creation", model=_model())
    evaluator = BatchBackend(phase="evaluation", model=_model(diagnostic=True))
    assert creator.client.config.model == MODEL_ID
    assert evaluator.client.config.model == DIAGNOSTIC_MODEL_ID
    assert creator.client.config.revision == MODEL_REVISION
    assert evaluator.client.config.revision == DIAGNOSTIC_MODEL_REVISION
    assert creator.client.base_endpoint != evaluator.client.base_endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://remote.example/v1",
        "http://remote.example:18138/v1",
        "http://127.0.0.1:18139/v1",
        "http://127.0.0.1:18138/v1?redirect=1",
        "http://user:pass@127.0.0.1:18138/v1",
        "http://127.0.0.1/v1",
    ],
)
def test_batch_model_rejects_nonlocal_or_ambiguous_endpoint(endpoint: str) -> None:
    model = _model()
    model["endpoint"] = endpoint
    with pytest.raises(ValueError):
        validate_batch_model(model)


def test_batch_model_rejects_revision_mismatch() -> None:
    model = _model()
    model["revision"] = DIAGNOSTIC_MODEL_REVISION
    with pytest.raises(ValueError, match="pinned model revision"):
        validate_batch_model(model)


@pytest.fixture
def no_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("r2sp_tau_knowledge.batch_official_runtime")

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid requests must not construct or run a runtime")

    for name in (
        "build_acquisition_runtime",
        "build_benign_batch_runtime",
        "build_deployment_runtime",
        "run_official",
    ):
        setattr(module, name, forbidden)
    monkeypatch.setitem(sys.modules, "r2sp_tau_knowledge.batch_official_runtime", module)


@pytest.mark.parametrize(
    "mutation",
    [
        {"corpus": "poison"},
        {"corpus_directory": "/untrusted"},
        {"profile": "legacy-profile"},
        {"seed": True},
    ],
)
def test_batch_worker_rejects_nonbenign_or_extra_inputs_before_runtime(
    no_runtime: None,
    mutation: dict,
) -> None:
    request = {
        "mode": "batch-benign-acquisition",
        "model": _model(),
        "task_id": "task_001",
        "seed": 3,
        "simulation_id": "fixture",
        "corpus": "benign",
    }
    request.update(mutation)
    with pytest.raises(ValueError):
        run_request(request)


def test_batch_worker_rejects_modified_skill_before_runtime(no_runtime: None) -> None:
    with pytest.raises(ValueError, match="Skill hash mismatch"):
        run_request(
            {
                "mode": "batch-utility-deployment",
                "model": _model(),
                "task_id": "task_002",
                "seed": 3,
                "simulation_id": "fixture",
                "skill_text": "Reference facts.",
                "skill_sha256": "0" * 64,
            }
        )


@pytest.mark.parametrize(
    "tool", ["search_web", "select_docs", "mock_api_record", "sandbox_delete_sentinel"]
)
def test_utility_backend_rejects_retrieval_or_sidecar_exposure(
    tool: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = BatchBackend(phase="evaluation", model=_model())
    monkeypatch.setattr(backend, "_worker", lambda request: {"exposed_tool_names": [tool]})
    with pytest.raises(LiveInfrastructureError, match="forbidden tool"):
        backend.deploy(
            trial={"task_id": "task_002", "seed": 3},
            skill_text="Reference facts",
            skill_sha256="0" * 64,
        )


def test_gpu_lock_accepts_four_devices_and_still_excludes_a_second_owner(tmp_path: Path) -> None:
    path = tmp_path / "four-gpus.lock"
    first = GpuGateLock(path, indices=(0, 1, 2, 3))
    second = GpuGateLock(path, indices=(0, 1, 2, 3))
    with first:
        assert json.loads(path.read_text())["gpus"] == [0, 1, 2, 3]
        with pytest.raises(GpuGateError):
            second.acquire()
    with second:
        pass


@pytest.mark.parametrize("indices", [(), (0, 0), (-1,), (True,)])
def test_gpu_lock_rejects_invalid_device_sets(tmp_path: Path, indices: tuple) -> None:
    with pytest.raises(ValueError):
        GpuGateLock(tmp_path / "invalid.lock", indices=indices)


def test_allocation_preserves_slurm_cuda_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "fixture-job")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-a,GPU-b")
    requests = []

    def inspect(command, **kwargs):
        requests.append(command)
        return SimpleNamespace(stdout="2, GPU-a, test GPU, 24000\n4, GPU-b, test GPU, 24000\n")

    monkeypatch.setattr(batch_runtime.subprocess, "run", inspect)
    visible, rows = batch_runtime._allocation(None)
    assert visible == "GPU-a,GPU-b"
    assert [row["index"] for row in rows] == [2, 4]
    assert requests[0][requests[0].index("--id") + 1] == "GPU-a,GPU-b"
    with pytest.raises(GpuGateError, match="match CUDA_VISIBLE_DEVICES"):
        batch_runtime._allocation((0, 1))


def test_creation_rejects_modified_documents_before_compiler_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = [
        {"page_id": f"page-{index}", "title": "Reference", "body": "Original body"}
        for index in range(10)
    ]
    monkeypatch.setattr(
        batch_runtime,
        "load_documents",
        lambda: [
            SimpleNamespace(page_id=page["page_id"], to_page_mapping=lambda p=page: p)
            for page in original
        ],
    )
    backend = BatchBackend(phase="creation", model=_model())
    modified = [dict(page) for page in original]
    modified[0]["body"] = "Unexpected substituted body"
    acquisition = AcquisitionOutcome(
        status=RunStatus.SUCCESS,
        task_success=True,
        first_user_utterance="Question",
        opened_pages=tuple(modified),
        selection_complete=True,
    )

    def forbidden(**kwargs):
        raise AssertionError("modified documents must not reach the compiler")

    monkeypatch.setattr(backend.compiler, "build_payload", forbidden)
    with pytest.raises(ValueError, match="original benign documents"):
        backend._compile_in_process(
            item={"corpus": "benign", "skill_id": "fixture", "seed": 7}, acquisition=acquisition
        )


def test_evaluation_runtime_never_starts_dense_or_qualifies_compilation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(batch_runtime, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(batch_runtime, "validate_batch_assets", lambda **kwargs: {})
    devices = [{"index": index, "uuid": f"GPU-{index}", "name": "Test GPU"} for index in (2, 4)]
    monkeypatch.setattr(batch_runtime, "_allocation", lambda indices: ("2,4", devices))
    gate = SimpleNamespace(passed=True, to_dict=lambda: {"passed": True})
    monkeypatch.setattr(batch_runtime, "check_gpu_gate", lambda **kwargs: gate)
    events = []

    class FakeService:
        def __init__(self, **kwargs):
            self.log_path = tmp_path / "service.log"

        def __enter__(self):
            events.append("service-start")
            return self

        def __exit__(self, *args):
            events.append("service-close")

    def forbidden_dense():
        raise AssertionError("evaluation must not start dense retrieval")

    def qualify(endpoint, **kwargs):
        assert kwargs["include_creation"] is False
        assert kwargs["model_id"] == DIAGNOSTIC_MODEL_ID
        events.append("utility-qualification")
        return {"passed": True}

    monkeypatch.setattr(batch_runtime, "_OwnedBatchService", FakeService)
    monkeypatch.setattr(batch_runtime, "OwnedDenseService", forbidden_dense)
    monkeypatch.setattr(batch_runtime, "qualify_model_service", qualify)
    with BatchRuntime(phase="evaluation", model=_model(diagnostic=True)) as runtime:
        assert runtime.metadata["allocation"]["cuda_visible_devices"] == "2,4"
    assert events == ["service-start", "utility-qualification", "service-close"]


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("model_finish_reason_length", RunStatus.BEHAVIORAL_FAIL),
        ("model_connection_error", RunStatus.INVALID),
        ("model_tokenizer_error", RunStatus.INVALID),
    ],
)
def test_compiler_output_budget_failure_is_distinct_from_service_failure(
    failure: str,
    expected: RunStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = tuple(
        {"page_id": f"page-{index}", "title": "Reference", "body": "Original body"}
        for index in range(10)
    )
    monkeypatch.setattr(
        batch_runtime,
        "load_documents",
        lambda: [
            SimpleNamespace(page_id=page["page_id"], to_page_mapping=lambda p=page: p)
            for page in pages
        ],
    )
    backend = BatchBackend(phase="creation", model=_model())
    monkeypatch.setattr(backend.compiler, "build_payload", lambda **kwargs: {"task": "Question"})
    artifact = SimpleNamespace(valid=False, failure=failure, text="", skill_sha256="0" * 64)
    monkeypatch.setattr(backend.compiler, "compile", lambda **kwargs: artifact)
    acquisition = AcquisitionOutcome(
        status=RunStatus.SUCCESS,
        task_success=True,
        first_user_utterance="Question",
        opened_pages=pages,
        selection_complete=True,
    )
    result = backend._compile_in_process(
        item={"corpus": "benign", "skill_id": "fixture", "seed": 7},
        acquisition=acquisition,
    )
    assert result.status is expected
    assert result.error == failure


def test_compile_sends_only_current_selection_to_a_fresh_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = BatchBackend(phase="creation", model=_model())
    requests = []

    def worker(request):
        requests.append(request)
        return {
            "status": "BEHAVIORAL_FAIL",
            "skill_text": "",
            "skill_sha256": "0" * 64,
            "valid": False,
            "compiler_input": {"task": "Question"},
            "error": "model_finish_reason_length",
            "worker_pid": 123,
            "execution_id": "fresh-compiler-process",
            "model_response": {"finish_reason": "length"},
        }

    def forbidden(**kwargs):
        raise AssertionError("parent process must not compile")

    monkeypatch.setattr(backend, "_worker", worker)
    monkeypatch.setattr(backend.compiler, "compile", forbidden)
    acquisition = AcquisitionOutcome(
        status=RunStatus.SUCCESS,
        task_success=False,
        first_user_utterance="Question",
        selection_complete=True,
        opened_pages=(),
        public_trace={"events": []},
    )
    item = {"skill_id": "fixture", "acquisition_task_id": "task_001", "corpus": "benign", "seed": 7}
    outcome = backend.compile(item=item, acquisition=acquisition)
    assert outcome.status is RunStatus.BEHAVIORAL_FAIL
    assert requests[0]["mode"] == "batch-benign-compile"
    assert requests[0]["item"] == item
    assert set(requests[0]["acquisition"]) == {
        "first_user_utterance",
        "opened_pages",
        "selection_complete",
        "public_trace",
    }
    assert backend.metrics[-1]["execution_id"] == "fresh-compiler-process"


def test_compiler_worker_uses_its_own_module_and_temporary_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = BatchBackend(phase="creation", model=_model())
    calls = []

    def subprocess_stub(command, **kwargs):
        calls.append((command, kwargs))
        request = Path(command[command.index("--request") + 1])
        assert request.parent == Path(kwargs["cwd"])
        response = Path(command[command.index("--response") + 1])
        response.write_text('{"status": "SUCCESS"}')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(batch_runtime.subprocess, "run", subprocess_stub)
    for task in ("task_001", "task_002"):
        backend._worker({"mode": "batch-benign-compile", "task_id": task})
    assert all(
        command[command.index("-m") + 1] == "r2sp_tau_knowledge.batch_compile_worker"
        for command, _kwargs in calls
    )
    assert calls[0][1]["cwd"] != calls[1][1]["cwd"]
    assert all(not Path(kwargs["cwd"]).exists() for _command, kwargs in calls)


@pytest.mark.parametrize("mutation", [{"profile": "legacy"}, {"corpus_directory": "/external"}])
def test_compiler_worker_rejects_extra_routing_fields_before_loading_data(
    mutation: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from r2sp_tau_knowledge import batch_compile_worker

    def forbidden():
        raise AssertionError("invalid request must not load data")

    monkeypatch.setattr(batch_compile_worker, "verify_tracked_snapshot", forbidden)
    request = {
        "mode": "batch-benign-compile",
        "model": _model(),
        "task_id": "task_001",
        "item": {
            "skill_id": "fixture",
            "acquisition_task_id": "task_001",
            "corpus": "benign",
            "seed": 7,
        },
        "acquisition": {
            "first_user_utterance": "Question",
            "opened_pages": [],
            "selection_complete": False,
            "public_trace": {},
        },
    }
    request.update(mutation)
    with pytest.raises(ValueError, match="request fields"):
        batch_compile_worker.run_request(request)
