"""Terra model allowlist, refreshable Midway token files, per-cell locks and launchers."""

from __future__ import annotations

import importlib.util
import io
import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import test_workflow as workflow_tests
import yaml
from tau_skill_evolution import cli
from tau_skill_evolution import preflight as admission
from tau_skill_evolution.constants import SUPPORTED_MODELS, WORKER_PYTHON_VERSION
from tau_skill_evolution.credentials import (
    TOKEN_FILE_ENV,
    bearer_token_source,
    describe_credential,
    read_token_file,
)
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import (
    CredentialError,
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
    is_credential_error,
)
from tau_skill_evolution.spec import BEDROCK_MODEL, DEFAULT_CONFIG, load_spec
from tau_skill_evolution.workflow import Workflow

ENDPOINT = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _future(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_token(path: Path, token: str, expires_at: str | None = None) -> Path:
    path.write_text(json.dumps({"token": token, "expires_at": expires_at or _future()}))
    return path


@pytest.fixture(autouse=True)
def gold_metadata(tmp_path, monkeypatch):
    """Same offline upstream stand-in as test_workflow so fake workflows evaluate."""
    from tau_skill_evolution.spec import ExperimentSpec

    upstream = workflow_tests._gold_upstream(tmp_path / "upstream", load_spec().tasks)
    original = ExperimentSpec.upstream.fget
    monkeypatch.setattr(
        ExperimentSpec,
        "upstream",
        property(lambda self: upstream if self.experiment == "tau" else original(self)),
    )


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------------
# A. model allowlist
# ----------------------------------------------------------------------------


def test_supported_models_keep_the_historical_default_first():
    assert SUPPORTED_MODELS == (
        "openai.gpt-5.5",
        "openai.gpt-5.6-terra",
        "openai.gpt-5.4",
        "anthropic.claude-opus-4-8",
    )
    assert BEDROCK_MODEL == "openai.gpt-5.5" == GenerationConfig().model


@pytest.mark.parametrize("model", SUPPORTED_MODELS)
def test_generation_config_accepts_every_supported_model(model):
    transport = "bedrock-messages" if model == "anthropic.claude-opus-4-8" else "bedrock-responses"
    assert GenerationConfig(model=model, transport=transport).model == model


@pytest.mark.parametrize("model", ["openai.gpt-5.2", "openai.gpt-oss-120b", "gpt-5.6-terra"])
def test_generation_config_rejects_other_models(model):
    with pytest.raises(ValueError, match="model and supported Bedrock Mantle transport must match"):
        GenerationConfig(model=model)


@pytest.mark.parametrize("model", ["openai.gpt-5.6-terra", "openai.gpt-5.4"])
def test_configured_model_binds_identity_worker_and_responses_request(tmp_path, model):
    values = yaml.safe_load(DEFAULT_CONFIG.read_text())
    values["provider"]["model"] = model
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(values, sort_keys=False))
    spec = load_spec(path)
    assert spec.values["provider"]["model"] == model
    assert spec.identity["provider"]["model"] == model
    default = load_spec()
    assert (spec.identity["identity_hash"] == default.identity["identity_hash"]) == (
        model == default.values["provider"]["model"]
    )
    config = spec.worker_config()
    assert config["model"] == config["user_model"] == config["judge_model"] == model
    assert config["transport"] == "bedrock-responses"
    assert config["api_base"] == ENDPOINT
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        return io.BytesIO(json.dumps(workflow_tests_response()).encode())

    client = OpenAICompatibleClient(
        config["api_base"],
        config=GenerationConfig(model=config["model"], transport=config["transport"]),
        api_key="offline-secret",
        opener=opener,
    )
    client.complete([{"role": "user", "content": "offline model routing check"}])
    assert len(requests) == 1
    request = requests[0]
    assert request.get_method() == "POST"
    assert request.full_url == f"{ENDPOINT}/responses"
    assert request.get_header("Authorization") == "Bearer offline-secret"
    payload = json.loads(request.data)
    assert payload["model"] == model
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["max_output_tokens"] == GenerationConfig().max_output_tokens
    assert payload["store"] is False
    values["provider"]["model"] = "openai.gpt-5.2"
    path.write_text(yaml.safe_dump(values, sort_keys=False))
    with pytest.raises(ValueError, match="model and supported Bedrock Mantle transport must match"):
        load_spec(path)


@pytest.mark.parametrize("model", ["openai.gpt-5.6-terra", "openai.gpt-5.4"])
def test_bedrock_authentication_checks_the_configured_model(monkeypatch, model):
    spec = load_spec()
    spec.values["provider"]["model"] = model
    monkeypatch.setenv(spec.values["provider"]["region_env"], "us-east-1")
    monkeypatch.delenv(TOKEN_FILE_ENV, raising=False)
    monkeypatch.setenv(spec.values["provider"]["api_key_env"], "offline-secret")
    seen = {}

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return Response(json.dumps({"data": [{"id": seen["catalog"]}]}).encode())

    monkeypatch.setattr(admission.urllib.request, "urlopen", urlopen)
    seen["catalog"] = "openai.gpt-5.5"
    with pytest.raises(ValueError, match=model):
        admission.bedrock_authentication(spec)
    seen["catalog"] = model
    result = admission.bedrock_authentication(spec)
    assert result == {"status": 200, "model": model, "generation_requested": False}
    assert seen["url"] == "https://bedrock-mantle.us-east-1.api.aws/v1/models"
    assert seen["auth"] == "Bearer offline-secret"


# ----------------------------------------------------------------------------
# B. credentials
# ----------------------------------------------------------------------------


def test_token_file_round_trip_and_reread(tmp_path, monkeypatch):
    path = _write_token(tmp_path / "123.json", "first-token")
    assert read_token_file(path) == "first-token"
    monkeypatch.setenv(TOKEN_FILE_ENV, str(path))
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "static-must-lose")
    source = bearer_token_source("AWS_BEARER_TOKEN_BEDROCK")
    assert source() == "first-token"
    _write_token(path, "second-token")
    assert source() == "second-token"
    description = describe_credential("AWS_BEARER_TOKEN_BEDROCK")
    assert str(path) in description and "second-token" not in description


def test_expired_or_nearly_expired_token_file_is_rejected(tmp_path):
    expired = _write_token(tmp_path / "a.json", "old", _future(-5))
    with pytest.raises(ModelClientError) as info:
        read_token_file(expired)
    assert info.value.code == "credential_expired" and "old" not in str(info.value)
    soon = _write_token(tmp_path / "b.json", "soon", _future(30))
    with pytest.raises(ModelClientError) as info:
        read_token_file(soon)
    assert info.value.code == "credential_expired"
    assert read_token_file(_write_token(tmp_path / "c.json", "ok", _future(120))) == "ok"


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[]", '{"token": ""}', '{"token": "x"}', '{"token": "x", "expires_at": 5}'],
)
def test_malformed_or_missing_token_file_is_unavailable(tmp_path, content):
    path = tmp_path / "t.json"
    path.write_text(content)
    with pytest.raises(ModelClientError) as info:
        read_token_file(path)
    assert info.value.code == "credential_unavailable"
    with pytest.raises(ModelClientError) as info:
        read_token_file(tmp_path / "missing.json")
    assert info.value.code == "credential_unavailable"


def test_static_env_fallback_and_missing_both(monkeypatch):
    monkeypatch.delenv(TOKEN_FILE_ENV, raising=False)
    monkeypatch.setenv("TAU_TEST_KEY", "static-secret")
    assert bearer_token_source("TAU_TEST_KEY")() == "static-secret"
    assert describe_credential("TAU_TEST_KEY") == "TAU_TEST_KEY is present (value not recorded)"
    monkeypatch.delenv("TAU_TEST_KEY")
    with pytest.raises(ValueError, match="TAU_TEST_KEY or AWS_BEARER_TOKEN_BEDROCK_FILE"):
        bearer_token_source("TAU_TEST_KEY")
    with pytest.raises(ValueError, match="TAU_TEST_KEY or AWS_BEARER_TOKEN_BEDROCK_FILE"):
        describe_credential("TAU_TEST_KEY")


def test_client_resolves_callable_api_key_per_request(tmp_path):
    headers = []
    tokens = iter(["token-one", "token-two"])

    def opener(request, *, timeout):
        headers.append(request.get_header("Authorization"))
        return io.BytesIO(json.dumps(workflow_tests_response()).encode())

    client = OpenAICompatibleClient(ENDPOINT, api_key=lambda: next(tokens), opener=opener)
    client.complete([{"role": "user", "content": "a"}])
    client.complete([{"role": "user", "content": "b"}])
    assert headers == ["Bearer token-one", "Bearer token-two"]
    assert "token-one" not in repr(client)

    def expired():
        raise ModelClientError("credential_expired", "redacted")

    failing = OpenAICompatibleClient(ENDPOINT, api_key=expired, opener=opener)
    with pytest.raises(ModelClientError) as info:
        failing.complete([{"role": "user", "content": "c"}])
    assert info.value.code == "credential_expired" and len(headers) == 2


def workflow_tests_response():
    return {
        "id": "resp_1",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def test_workflow_model_uses_token_file_when_configured(tmp_path, monkeypatch):
    spec = load_spec()
    path = _write_token(tmp_path / "acct.json", "file-token")
    monkeypatch.setenv(TOKEN_FILE_ENV, str(path))
    monkeypatch.delenv(spec.provider_settings["api_key_env"], raising=False)
    workflow = Workflow(spec, tmp_path / "run", counter=len)
    client = workflow._model("analyzer")
    assert callable(client.api_key) and client.api_key() == "file-token"


# ----------------------------------------------------------------------------
# C. parallel-safe execution
# ----------------------------------------------------------------------------


def test_lock_path_single_cell_versus_whole_run(tmp_path):
    assert cli.lock_path(tmp_path, (("task_001", "benign"),)) == (
        tmp_path / "locks" / "task_001__benign.lock"
    )
    assert cli.lock_path(tmp_path, (("task_001", "benign"), ("task_001", "poison-5"))) == (
        tmp_path / ".lock"
    )
    assert cli.lock_path(tmp_path, ()) == tmp_path / ".lock"


def test_run_without_interim_report_skips_report_json(tmp_path):
    workflow, _, _ = workflow_tests._workflow(tmp_path)
    workflow.interim_report = False
    workflow.evolve = lambda selected: None
    cell = (workflow.spec.tasks[0], "benign")
    result = workflow.run((cell,))
    assert result["interim_report"] is False and result["cells"] == [list(cell)]
    assert result["stage"] == "run" and result["run_dir"] == str(workflow.root)
    assert not (workflow.root / "report.json").exists()
    report = workflow.report()
    assert (workflow.root / "report.json").exists()
    cases = {case["task_id"]: case for case in report["cases"] if case["condition"] == "benign"}
    assert cases[cell[0]]["status"] == "CREATED"


def test_run_default_still_writes_interim_report(tmp_path):
    workflow, _, _ = workflow_tests._workflow(tmp_path)
    assert workflow.interim_report is True
    workflow.evolve = lambda selected: None
    report = workflow.run(((workflow.spec.tasks[0], "benign"),))
    assert (workflow.root / "report.json").exists() and "cases" in report


def test_workflow_accepts_pre_created_launcher_entries(tmp_path):
    root = tmp_path / "run"
    for name in ("locks", "logs"):
        (root / name).mkdir(parents=True)
    (root / ".lock").touch()
    (root / "launcher-status.json").write_text("{}")
    workflow_tests._workflow(tmp_path)
    assert (root / "journal" / "identity.json").exists()
    (tmp_path / "other" / "stray.txt").parent.mkdir()
    (tmp_path / "other" / "stray.txt").write_text("x")
    with pytest.raises(ValueError, match="identity"):
        Workflow(load_spec(), tmp_path / "other", counter=len)


def test_journal_identity_creation_ignores_concurrent_temporaries(tmp_path):
    root = tmp_path / "journal"
    root.mkdir()
    (root / ".identity.json.abc123").write_text("{}")
    Journal(root, identity={"a": 1})
    assert json.loads((root / "identity.json").read_text())["identity"] == {"a": 1}
    Journal(root, identity={"a": 1})
    with pytest.raises(ValueError, match="identity"):
        Journal(root, identity={"a": 2})


def test_cli_run_with_single_cell_locks_only_that_cell(tmp_path, monkeypatch, capsys):
    spec = load_spec()
    monkeypatch.setattr(cli, "load_spec", lambda _: spec)
    monkeypatch.setattr(cli, "preflight", lambda *args, **kwargs: {"ready": True})
    seen = {}

    class FakeWorkflow:
        def __init__(self, spec, run_dir, **kwargs):
            seen["kwargs"] = kwargs
            seen["run_dir"] = run_dir

        def run(self, cells):
            seen["cells"] = cells
            return {"ok": True}

    monkeypatch.setattr(cli, "Workflow", FakeWorkflow)
    run_dir = tmp_path / "run"
    task = spec.tasks[0]
    code = cli.main(
        ["run", "--run-dir", str(run_dir), "--task", task, "--arm", "benign", "--no-interim-report"]
    )
    assert code == 0 and json.loads(capsys.readouterr().out) == {"ok": True}
    assert (run_dir / "locks" / f"{task}__benign.lock").exists()
    # Single-cell runs also hold ".lock" SHARED (see test_run_locks_hierarchy).
    assert (run_dir / ".lock").exists()
    assert seen["kwargs"] == {
        "demo": False,
        "demo_task": None,
        "interim_report": False,
        "runtime": "docker",
    }
    assert seen["cells"] == ((task, "benign"),)
    code = cli.main(["run", "--run-dir", str(run_dir), "--task", task])
    assert code == 0 and (run_dir / ".lock").exists()
    assert seen["kwargs"] == {
        "demo": False,
        "demo_task": None,
        "interim_report": True,
        "runtime": "docker",
    }
    assert len(seen["cells"]) == 3


# ----------------------------------------------------------------------------
# D. worker python pin
# ----------------------------------------------------------------------------


def test_worker_python_pin_is_exact_tuple():
    assert WORKER_PYTHON_VERSION == (3, 12, 12)
    assert isinstance(WORKER_PYTHON_VERSION, tuple)


# ----------------------------------------------------------------------------
# E. token daemon helpers
# ----------------------------------------------------------------------------


def test_daemon_pure_helpers(tmp_path):
    daemon = _load_script("bedrock_token_daemon")
    now = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
    assert daemon.is_expired("2026-10-05T00:00:30Z", now)
    assert daemon.is_expired("2026-10-04T23:00:00Z", now)
    assert not daemon.is_expired("2026-10-05T00:01:01Z", now)
    assert not daemon.is_expired("2026-10-05T01:00:00+00:00", now)
    ada = json.dumps(
        {
            "Version": 1,
            "AccessKeyId": "AKIA",
            "SecretAccessKey": "secret",
            "SessionToken": "session",
            "Expiration": "2026-10-05T01:00:00Z",
        }
    )
    credentials = daemon.parse_ada_credentials(ada)
    assert credentials["AccessKeyId"] == "AKIA" and credentials["Expiration"].endswith("Z")
    with pytest.raises(ValueError, match="missing fields"):
        daemon.parse_ada_credentials(json.dumps({"AccessKeyId": "x"}))
    with pytest.raises(ValueError):
        daemon.parse_ada_credentials("nope")
    env = daemon.credential_environment(
        {"AWS_PROFILE": "default", "PATH": "/bin", "AWS_BEARER_TOKEN_BEDROCK": "old"},
        credentials,
        "us-east-1",
    )
    assert "AWS_PROFILE" not in env and "AWS_BEARER_TOKEN_BEDROCK" not in env
    assert env["AWS_SESSION_TOKEN"] == "session" and env["AWS_DEFAULT_REGION"] == "us-east-1"
    payload = daemon.build_token_payload(
        "123456789012", "us-east-1", "tok", "2026-10-05T01:00:00Z", "2026-10-05T00:00:00Z"
    )
    assert set(payload) == {"account", "region", "token", "expires_at", "minted_at"}
    with pytest.raises(ValueError):
        daemon.build_token_payload("1", "us-east-1", "", "2026-10-05T01:00:00Z", "x")
    assert daemon.parse_mint_output('{"token": "t", "expires_at": "2026-10-05T01:00:00Z"}') == {
        "token": "t",
        "expires_at": "2026-10-05T01:00:00Z",
    }
    assert daemon.ada_command("/ada", "1", "Role", "conduit") == [
        "/ada", "credentials", "print", "--account", "1", "--provider", "conduit",
        "--role", "Role", "--format", "json",
    ]  # fmt: skip
    command = daemon.mint_command("/s.py", "/py", "1", "us-east-1", "/ada", "Role", "conduit")
    assert command[:5] == ["/py", "/s.py", "--mint", "1", "us-east-1"]
    assert daemon.parse_accounts(" 1, 2 ,,3") == ["1", "2", "3"]
    with pytest.raises(ValueError):
        daemon.parse_accounts("1,1")
    out = tmp_path / "123.json"
    daemon.write_atomic_json(out, payload)
    assert json.loads(out.read_text()) == payload and oct(out.stat().st_mode & 0o777) == "0o600"
    assert not list(tmp_path.glob(".123.json.*"))
    entry = daemon.status_entry(None, minted_at="m", expires_at="e", now="n")
    assert entry["last_error"] is None and entry["expires_at"] == "e"
    failed = daemon.status_entry(entry, error="boom", now="n2")
    assert failed["last_error"] == "boom" and failed["expires_at"] == "e"


def test_daemon_keeps_previous_file_when_mint_fails(tmp_path, monkeypatch):
    daemon = _load_script("bedrock_token_daemon")
    out_dir = tmp_path / "tokens"
    out_dir.mkdir()
    previous = daemon.build_token_payload(
        "1", "us-east-1", "old-token", "2026-10-05T01:00:00Z", "2026-10-05T00:00:00Z"
    )
    daemon.write_atomic_json(out_dir / "1.json", previous)
    calls = []

    def fake_mint(account, region, **kwargs):
        calls.append(account)
        if account == "1":
            raise RuntimeError("ada failed")
        # Far in the future: the daemon refuses to publish tokens already near expiry.
        return {"token": "new-token", "expires_at": "2099-01-01T00:00:00Z"}

    monkeypatch.setattr(daemon, "run_mint_child", fake_mint)
    monkeypatch.setattr(daemon, "log", lambda message: calls.append(message))
    status = daemon.refresh_all(
        ["1", "2"], "us-east-1", out_dir, {"accounts": {}}, ada="a", role="r", provider="p"
    )
    assert json.loads((out_dir / "1.json").read_text()) == previous
    assert json.loads((out_dir / "2.json").read_text())["token"] == "new-token"
    assert status["accounts"]["1"]["last_error"] == "RuntimeError: ada failed"
    assert status["accounts"]["2"]["last_error"] is None
    written = json.loads((out_dir / "status.json").read_text())
    assert "new-token" not in json.dumps(written) and "old-token" not in json.dumps(written)
    assert not any("new-token" in str(item) for item in calls)


# ----------------------------------------------------------------------------
# F. launcher helpers
# ----------------------------------------------------------------------------


def test_launcher_pure_helpers(tmp_path):
    launcher = _load_script("launch_matrix")
    cells = (("t1", "benign"), ("t1", "poison-5"), ("t2", "benign"), ("t2", "poison-5"))
    assert launcher.filter_cells(cells, None, None) == list(cells)
    assert launcher.filter_cells(cells, ["t2"], None) == [("t2", "benign"), ("t2", "poison-5")]
    assert launcher.filter_cells(cells, None, ["benign"]) == [("t1", "benign"), ("t2", "benign")]
    assigned = launcher.assign_accounts(list(cells), ["A", "B", "C"])
    assert assigned == {"t1|benign": "A", "t1|poison-5": "B", "t2|benign": "C", "t2|poison-5": "A"}
    with pytest.raises(ValueError):
        launcher.assign_accounts(list(cells), [])
    command = launcher.build_command(
        "/r2sp", "tau", Path("/cfg.yaml"), Path("/run"), "t1", "benign"
    )
    assert command == [
        "/r2sp", "run", "--runtime", "docker", "--experiment", "tau",
        "--config", "/cfg.yaml", "--task", "t1",
        "--arm", "benign", "--run-dir", "/run", "--no-interim-report",
    ]  # fmt: skip
    env = launcher.build_env(
        {"AWS_PROFILE": "x", "AWS_BEARER_TOKEN_BEDROCK": "static", "PATH": "/bin"},
        Path("/tokens/1.json"),
    )
    assert env == {"PATH": "/bin", "AWS_BEARER_TOKEN_BEDROCK_FILE": "/tokens/1.json"}
    assert launcher.report_command("/r2sp", "tau", Path("/c"), Path("/r"))[:2] == [
        "/r2sp",
        "report",
    ]
    assert launcher.log_path(Path("/run"), "t1", "benign") == Path("/run/logs/t1__benign.log")
    assert launcher.entrypoint(None) == [launcher.sys.executable, "-m", "tau_skill_evolution.cli"]
    workspace = launcher.build_command(
        None, "tau", Path("/c"), Path("/r"), "t", "benign", runtime="workspace"
    )
    assert workspace[workspace.index("--runtime") + 1] == "workspace"
    report = launcher.report_command(None, "tau", Path("/c"), Path("/r"), runtime="workspace")
    assert report[report.index("--runtime") + 1] == "workspace"
    (tmp_path / "123.json").write_text("{}")
    (tmp_path / "456.json").write_text("{}")
    (tmp_path / "status.json").write_text("{}")
    assert launcher.discover_accounts(tmp_path) == ["123", "456"]

    def entry(account, pid, started, finished, code):
        return {
            "account": account,
            "pid": pid,
            "started_at": started,
            "finished_at": finished,
            "exit_code": code,
        }

    status = launcher.build_status(
        started_at="s",
        experiment="tau",
        config=Path("/c"),
        cells={
            "t1|benign": entry("A", 1, "x", "y", 0),
            "t1|poison-5": entry("B", 2, "x", "y", 2),
            "t2|benign": entry("C", 3, "x", None, None),
            "t2|poison-5": entry("A", None, None, None, None),
        },
    )
    assert (status["running"], status["finished"], status["failed"], status["total"]) == (
        1,
        2,
        1,
        4,
    )
    assert status["experiment"] == "tau" and status["config"] == "/c"


def test_launcher_dry_run_prints_plan_without_spawning(tmp_path, capsys):
    launcher = _load_script("launch_matrix")
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    (token_dir / "111111111111.json").write_text("{}")
    spec = load_spec()
    code = launcher.main(
        [
            "--experiment",
            "tau",
            "--config",
            str(DEFAULT_CONFIG),
            "--run-dir",
            str(tmp_path / "run"),
            "--token-dir",
            str(token_dir),
            "--task",
            spec.tasks[0],
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0 and "planned 3 cells x 1 stage(s) over 1 accounts" in out
    assert out.count("--no-interim-report") == 3 and "111111111111.json" in out
    assert not (tmp_path / "run").exists()


# ----------------------------------------------------------------------------
# Review fixes: credential errors never seal, path/lock/cold-start safety
# ----------------------------------------------------------------------------


def test_credential_error_is_a_model_client_error_with_cause_detection():
    error = CredentialError("credential_expired", "redacted")
    assert isinstance(error, ModelClientError) and error.code == "credential_expired"
    wrapped = RuntimeError("outer")
    wrapped.__cause__ = error
    assert is_credential_error(wrapped) and not is_credential_error(RuntimeError("plain"))


def test_client_resolves_token_before_building_any_request(tmp_path):
    def expired():
        raise CredentialError("credential_expired", "redacted")

    def opener(request, *, timeout):
        raise AssertionError("no request may be built without a credential")

    client = OpenAICompatibleClient(ENDPOINT, api_key=expired, opener=opener)
    with pytest.raises(CredentialError):
        client.complete([{"role": "user", "content": "c"}], max_output_tokens=-1)


def test_journal_withdraws_unsent_operation_on_credential_error(tmp_path):
    journal = Journal(tmp_path / "journal", identity={"a": 1})
    calls = []

    def callback():
        calls.append(1)
        raise CredentialError("credential_expired", "redacted")

    with pytest.raises(CredentialError):
        journal.dispatch("op", {"x": 1}, callback)
    assert not journal.dispatched("op") and not list((tmp_path / "journal").glob("*/"))
    # Later invocation sends the request for the first time (not a retry).
    assert journal.dispatch("op", {"x": 1}, lambda: {"ok": True}) == {"ok": True}
    assert calls == [1]

    def transport():
        raise RuntimeError("transport interrupted")

    with pytest.raises(UnknownOperation):
        journal.dispatch("other", {}, transport)
    assert journal.dispatched("other")  # unchanged semantics for real transport failures


def test_workflow_create_aborts_without_sealing_on_credential_error(tmp_path):
    def expired(payload):
        raise CredentialError("credential_unavailable", "redacted")

    workflow, _, requests = workflow_tests._workflow(tmp_path, output=expired)
    cell = (workflow.spec.tasks[0], "benign")
    with pytest.raises(CredentialError):
        workflow.run((cell,))
    _, journal = workflow._cell(*cell)
    assert not journal.completed("creation") and not journal.dispatched("generate-initial")
    # Earlier sealed acquisition operations stay; nothing is left pending/unknown.
    pending = [
        p for p in journal.root.glob("*/request.json") if not (p.parent / "response.json").exists()
    ]
    assert pending == []
    resumed, _, _ = workflow_tests._workflow(tmp_path)
    resumed.evolve = lambda selected: None
    report = resumed.run((cell,))
    case = next(
        c for c in report["cases"] if c["task_id"] == cell[0] and c["condition"] == "benign"
    )
    assert case["status"] == "CREATED"


def test_evaluation_and_bank_credential_errors_abort_instead_of_not_measured(tmp_path):
    from tau_skill_evolution.evaluation import evaluate_versions

    workflow, log, _ = workflow_tests._workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    _, initial = workflow._created(*workflow._cell(*cell))

    def evaluate(bundle):
        raise CredentialError("credential_expired", "redacted")

    with pytest.raises(CredentialError):
        evaluate_versions((initial,), evaluate, journal=workflow._cell(*cell)[1])


def test_token_file_path_is_absolute_even_when_cwd_changes(tmp_path, monkeypatch):
    path = _write_token(tmp_path / "acct.json", "file-token")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(TOKEN_FILE_ENV, "acct.json")
    source = bearer_token_source("TAU_TEST_KEY")
    description = describe_credential("TAU_TEST_KEY")
    monkeypatch.chdir(tmp_path.parent)  # bank worker runs with cwd=upstream root
    assert source() == "file-token"
    assert str(path) in description and "file-token" not in description


def test_describe_credential_fails_closed_on_unusable_token_file(tmp_path, monkeypatch):
    path = tmp_path / "acct.json"
    monkeypatch.setenv(TOKEN_FILE_ENV, str(path))
    with pytest.raises(CredentialError) as info:
        describe_credential("TAU_TEST_KEY")
    assert info.value.code == "credential_unavailable"
    _write_token(path, "s3cr3t-bearer-value", expires_at=_future(10))
    with pytest.raises(CredentialError) as info:
        describe_credential("TAU_TEST_KEY")
    assert info.value.code == "credential_expired"
    spec = load_spec()
    result = admission.preflight(spec)
    credential = next(c for c in result["checks"] if c["name"] == "credential")
    assert credential["ok"] is False and "expired" in credential["detail"]
    assert "s3cr3t-bearer-value" not in json.dumps(result)


def _locked_out(run_dir, cells, message):
    with pytest.raises(RuntimeError, match=message), cli.run_locks(run_dir, cells):
        pass


def test_run_locks_hierarchy(tmp_path):
    one, two = ("task_001", "benign"), ("task_002", "benign")
    with cli.run_locks(tmp_path, (one,)) as owned:
        assert owned == tmp_path / "locks" / "task_001__benign.lock"
        with cli.run_locks(tmp_path, (two,)):  # other cells run alongside
            pass
        _locked_out(tmp_path, (one,), "owns this cell")
        _locked_out(tmp_path, (one, two), "owns this run directory")  # whole-run excluded
        _locked_out(tmp_path, (), "owns this run directory")  # report excluded
    with cli.run_locks(tmp_path, ()) as owned:
        assert owned == tmp_path / ".lock"
        _locked_out(tmp_path, (one,), "owns this run directory")  # cell excluded by whole-run
    with cli.run_locks(tmp_path, (one,)):
        pass


def test_workflow_tolerates_concurrent_identity_creation_in_progress(tmp_path):
    root = tmp_path / "run"
    (root / "journal").mkdir(parents=True)
    (root / "journal" / ".identity.json.tmp123").write_text("{}")
    workflow_tests._workflow(tmp_path)
    assert (root / "journal" / "identity.json").exists()
    (tmp_path / "busy" / "journal").mkdir(parents=True)
    (tmp_path / "busy" / "journal" / "deadbeef").mkdir()
    with pytest.raises(ValueError, match="identity"):
        Workflow(load_spec(), tmp_path / "busy", counter=len)


def test_journal_identity_first_writer_wins_without_overwrite(tmp_path):
    from tau_skill_evolution.journal import _create_identity_exclusive

    root = tmp_path / "journal"
    root.mkdir()
    _create_identity_exclusive(root / "identity.json", {"first": True})
    _create_identity_exclusive(root / "identity.json", {"second": True})
    assert json.loads((root / "identity.json").read_text()) == {"first": True}
    assert list(root.iterdir()) == [root / "identity.json"]
    with pytest.raises(ValueError, match="differs"):
        Journal(root, identity={"a": 1})


def test_dense_cache_publication_tolerates_concurrent_builders(tmp_path):
    from tau_skill_evolution import retrieval

    cache = tmp_path / "dense" / "key"
    cache.parent.mkdir()
    builds = []

    def racing_build(output: Path) -> None:
        builds.append(output)
        output.mkdir()
        (output / "vectors.bin").write_bytes(b"mine")
        # Another process published the same key first.
        cache.mkdir()
        (cache / "vectors.bin").write_bytes(b"theirs")

    assert retrieval.ensure_cache(cache, racing_build) == cache
    assert (cache / "vectors.bin").read_bytes() == b"theirs" and len(builds) == 1
    assert not list(cache.parent.glob("build-*"))
    assert retrieval.ensure_cache(cache, racing_build) == cache and len(builds) == 1

    def plain_build(output: Path) -> None:
        output.mkdir()
        (output / "vectors.bin").write_bytes(b"fresh")

    fresh = tmp_path / "dense" / "other"
    assert retrieval.ensure_cache(fresh, plain_build) == fresh
    assert (fresh / "vectors.bin").read_bytes() == b"fresh"
    with pytest.raises(OSError):
        retrieval.publish_cache(tmp_path / "missing", tmp_path / "dense" / "x")


def test_run_without_interim_report_skips_report_json_on_failure(tmp_path):
    workflow, _, _ = workflow_tests._workflow(tmp_path)
    workflow.interim_report = False

    def boom(selected):
        raise RuntimeError("evolution crashed")

    workflow.evolve = boom
    with pytest.raises(RuntimeError, match="evolution crashed"):
        workflow.run(((workflow.spec.tasks[0], "benign"),))
    assert not (workflow.root / "report.json").exists()
    workflow.interim_report = True
    with pytest.raises(RuntimeError, match="evolution crashed"):
        workflow.run(((workflow.spec.tasks[0], "benign"),))
    assert (workflow.root / "report.json").exists()


def test_daemon_adaptive_sleep_and_near_expired_rejection(tmp_path, monkeypatch):
    daemon = _load_script("bedrock_token_daemon")
    now = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
    status = {
        "accounts": {
            "1": {"expires_at": "2026-10-05T01:00:00Z", "last_error": None},
            "2": {"expires_at": "2026-10-05T00:08:00Z", "last_error": None},
            "3": {"expires_at": "2026-10-05T00:01:00Z", "last_error": "ada failed"},
        }
    }
    assert daemon.next_sleep_seconds(status, now, 1200) == 8 * 60 - 2 * 60
    assert daemon.next_sleep_seconds({"accounts": {}}, now, 1200) == 1200.0
    assert daemon.next_sleep_seconds(status, now + timedelta(minutes=7), 1200) == float(
        daemon.MIN_SLEEP_SECONDS
    )
    monkeypatch.setattr(
        daemon,
        "run_mint_child",
        lambda account, region, **kwargs: {"token": "t", "expires_at": _future(30)},
    )
    account, minted, error = daemon._mint_or_error("1", "us-east-1", "a", "r", "p")
    assert minted is None and "expiry margin" in error and error != "t"
    monkeypatch.setattr(
        daemon,
        "run_mint_child",
        lambda account, region, **kwargs: (_ for _ in ()).throw(ImportError("no boto3")),
    )
    assert daemon._mint_or_error("1", "us-east-1", "a", "r", "p")[2] == "ImportError: no boto3"


def test_daemon_refresh_all_uses_bounded_pool_and_writes_from_main_thread(tmp_path, monkeypatch):
    import threading

    daemon = _load_script("bedrock_token_daemon")
    out_dir = tmp_path / "tokens"
    out_dir.mkdir()
    threads = set()

    def fake_mint(account, region, **kwargs):
        threads.add(threading.current_thread().name)
        return {"token": f"tok-{account}", "expires_at": _future()}

    monkeypatch.setattr(daemon, "run_mint_child", fake_mint)
    monkeypatch.setattr(daemon, "log", lambda message: None)
    status = daemon.refresh_all(
        [str(i) for i in range(6)],
        "us-east-1",
        out_dir,
        {"accounts": {}},
        ada="a",
        role="r",
        provider="p",
        parallel=3,
    )
    assert all(status["accounts"][str(i)]["last_error"] is None for i in range(6))
    assert all(
        json.loads((out_dir / f"{i}.json").read_text())["token"] == f"tok-{i}" for i in range(6)
    )
    assert "MainThread" not in threads and 1 <= len(threads) <= 3
    assert "tok-" not in (out_dir / "status.json").read_text()


def test_launcher_rejects_missing_r2sp_and_terminates_children_on_error(tmp_path, capsys):
    launcher = _load_script("launch_matrix")
    assert not launcher.executable(str(tmp_path / "missing"))
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    _write_token(token_dir / "111111111111.json", "t")
    with pytest.raises(SystemExit) as info:
        launcher.main(
            [
                "--experiment",
                "tau",
                "--config",
                str(DEFAULT_CONFIG),
                "--run-dir",
                str(tmp_path / "run"),
                "--token-dir",
                str(token_dir),
                "--r2sp",
                str(tmp_path / "missing"),
                "--dry-run",
            ]
        )
    assert info.value.code == 2 and "not an executable" in capsys.readouterr().err

    args = types.SimpleNamespace(
        r2sp=str(tmp_path / "missing"),
        experiment="tau",
        config=DEFAULT_CONFIG,
        run_dir=tmp_path / "run",
        token_dir=token_dir,
        accounts=["111111111111"],
        max_concurrent=4,
        stagger_seconds=0.0,
    )
    terminated = []
    instance = launcher.Launcher(args, [("task_001", "benign")])
    instance.terminate_children = lambda: terminated.append(True)
    with pytest.raises(FileNotFoundError):
        instance.run()
    assert terminated == [True]
    assert json.loads((tmp_path / "run" / "launcher-status.json").read_text())["running"] == 0


@pytest.mark.parametrize("code", [401, 403])
def test_launcher_stops_before_starting_next_cell_after_authentication_failure(tmp_path, code):
    launcher = _load_script("launch_matrix")
    args = types.SimpleNamespace(
        r2sp=None,
        experiment="tau",
        config=DEFAULT_CONFIG,
        run_dir=tmp_path,
        token_dir=tmp_path,
        accounts=["111"],
        max_concurrent=1,
        stagger_seconds=0,
    )
    instance = launcher.Launcher(args, [("first", "benign"), ("next", "benign")])
    journal = tmp_path / "cells/first/benign/journal/op"
    journal.mkdir(parents=True)
    (journal / "failure.json").write_text(
        json.dumps({"code": "authentication_failed", "status": code})
    )
    process = types.SimpleNamespace(poll=lambda: 2)
    instance.processes["first|benign"] = (process, io.BytesIO())
    started = []
    instance.start = lambda *cell: started.append(cell)
    assert instance.run() == 2
    assert not started and instance.authentication_status == code


def _formal_report(trial, cases, identity=None):
    return {
        "identity": identity or {"identity_hash": "same-method"},
        "trial_id": trial,
        "namespace": "tau.skill-evolution.v3",
        "experiment": "tau",
        "run_mode": "formal",
        "execution": {"backend": "docker"},
        "cases": cases,
    }


def test_trial_collection_retains_primary_and_original_hashes():
    merge = _load_script("merge_reports")
    original = {
        "task_id": "t",
        "condition": "benign",
        "status": "CREATED",
        "stop_reason": "oracle_success",
        "initial_bundle_hash": "S0-original",
        "acquisition": {"base_hash": "B-original"},
    }
    rerun = {
        **original,
        "initial_bundle_hash": "S0-rerun",
        "acquisition": {"base_hash": "B-rerun"},
        "stop_reason": "oracle_budget_exhausted",
    }
    primary, retry = _formal_report("primary", [original]), _formal_report("retry", [rerun])
    collected = merge.resampled_cases(primary, retry, {"t|benign"})
    assert primary["cases"] == [original]
    assert collected[0]["primary_initial_bundle_hash"] == "S0-original"
    assert collected[0]["primary_base_hash"] == "B-original"
    assert collected[0]["case"] == rerun
    assert collected[0]["kind"] == "whole_chain_resample"


@pytest.mark.parametrize("change", ["identity", "demo", "duplicate", "missing_trial"])
def test_trial_collection_rejects_unbound_or_mixed_reports(change):
    merge = _load_script("merge_reports")
    case = {"task_id": "t", "condition": "benign"}
    identity = {"identity_hash": "same-method"}
    report = _formal_report("trial", [case], identity)
    if change == "identity":
        report["identity"] = {"identity_hash": "changed-model-source-or-config"}
    elif change == "demo":
        report["run_mode"] = "single-task-demo"
        report["execution"]["backend"] = "bubblewrap-demo"
    elif change == "duplicate":
        report["cases"].append(case)
    else:
        report.pop("trial_id")
    with pytest.raises(ValueError):
        merge.validate_report(report, identity, "tau", "tau.skill-evolution.v3")


def test_unstarted_or_missing_trial_cell_is_rejected():
    merge = _load_script("merge_reports")
    case = {"task_id": "t", "condition": "benign", "stop_reason": "not_started"}
    with pytest.raises(ValueError, match="not started"):
        merge.resampled_cases(
            _formal_report("primary", [case]), _formal_report("retry", [case]), {"t|benign"}
        )
    with pytest.raises(ValueError, match="missing"):
        merge.resampled_cases(
            _formal_report("primary", [case]), _formal_report("retry", []), {"t|benign"}
        )


def test_launcher_binds_default_docker_and_rejects_runtime_change(tmp_path, monkeypatch):
    launcher = _load_script("launch_matrix")
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    (token_dir / "111.json").write_text("{}")
    calls = []

    def report(command, **kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    def run(instance):
        assert instance.args.max_concurrent == 96
        for item in instance.status_cells.values():
            item["exit_code"] = 0
        return 0

    monkeypatch.setattr(launcher.subprocess, "run", report)
    monkeypatch.setattr(launcher.Launcher, "run", run)
    argv = [
        "--experiment",
        "tau",
        "--config",
        str(DEFAULT_CONFIG),
        "--run-dir",
        str(tmp_path / "run"),
        "--token-dir",
        str(token_dir),
        "--task",
        load_spec().tasks[0],
        "--arm",
        "benign",
        "--skip-final-report",
    ]
    assert launcher.main(argv) == 0
    assert calls[0][calls[0].index("--runtime") + 1] == "docker"
    identity = json.loads((tmp_path / "run/launcher-identity.json").read_text())
    assert identity["runtime"] == "docker"
    with pytest.raises(SystemExit) as error:
        launcher.main([*argv, "--runtime", "workspace"])
    assert error.value.code == 2 and len(calls) == 1


@pytest.mark.parametrize(
    ("options", "runtime", "concurrency"),
    [
        ([], "docker", 96),
        (["--runtime", "docker"], "docker", 96),
        (["--runtime", "workspace"], "workspace", 1),
        (["--max-concurrent", "4"], "docker", 4),
    ],
)
def test_launcher_concurrency_defaults_follow_runtime(
    tmp_path, monkeypatch, options, runtime, concurrency
):
    launcher = _load_script("launch_matrix")
    observed = []
    monkeypatch.setattr(
        launcher,
        "_dry_run",
        lambda args, cells: observed.append((args.runtime, args.max_concurrent)),
    )
    assert (
        launcher.main(
            [
                "--experiment",
                "tau",
                "--config",
                str(DEFAULT_CONFIG),
                "--run-dir",
                str(tmp_path / "run"),
                "--token-dir",
                str(tmp_path / "tokens"),
                "--accounts",
                "1",
                "--dry-run",
                *options,
            ]
        )
        == 0
    )
    assert observed == [(runtime, concurrency)]


@pytest.mark.parametrize("runtime", ["workspace", "docker"])
def test_workspace_trial_collection_preserves_runtime_and_primary(tmp_path, monkeypatch, runtime):
    from tau_skill_evolution import spec as spec_module
    from tau_skill_evolution.workflow import Workflow

    merge = _load_script("merge_reports")
    identity = {"identity_hash": "method"}
    spec = types.SimpleNamespace(
        identity=identity,
        experiment="tau",
        namespace="tau.skill-evolution.v3",
        tasks=("t",),
        arms=("benign",),
        cells=(("t", "benign"),),
    )
    monkeypatch.setattr(spec_module, "load_spec", lambda path: spec)
    monkeypatch.setattr(
        Workflow,
        "_write_report_md",
        lambda self, report: (self.root / "REPORT.md").write_text(report["run_mode"]),
    )
    original = {
        "task_id": "t",
        "condition": "benign",
        "status": "CREATION_FAILED",
        "stop_reason": "creation_failed",
        "versions": [],
        "evaluations": {},
    }
    rerun = {**original, "stop_reason": "generation_result_unknown"}
    primary_dir, retry_dir, output = (tmp_path / name for name in ("primary", "retry", "output"))
    for directory, trial, case in ((primary_dir, "primary", original), (retry_dir, "retry", rerun)):
        directory.mkdir()
        report = _formal_report(trial, [case], identity)
        report.update(
            run_mode="workspace" if runtime == "workspace" else "formal", formal_matrix_result=False
        )
        report["execution"] = {
            "backend": runtime,
            "runtime_lock_hash": "same-lock",
            "aggregate_limits_enforced": False,
            "formal_matrix_result": False,
        }
        (directory / "report.json").write_text(json.dumps(report))
    cells = tmp_path / "cells.json"
    cells.write_text('["t|benign"]')
    argv = [
        "merge_reports.py",
        "--config",
        str(DEFAULT_CONFIG),
        "--runtime",
        runtime,
        "--primary",
        str(primary_dir),
        "--retry",
        str(retry_dir),
        "--cells",
        str(cells),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(merge.sys, "argv", argv)
    assert merge.main() == 0
    report = json.loads((output / "report.json").read_text())
    assert report["run_mode"] == ("workspace-trials" if runtime == "workspace" else "formal-trials")
    assert report["execution"]["backend"] == runtime and report["formal_matrix_result"] is False
    assert report["cases"] == [original] and report["resampled_trials"][0]["case"] == rerun
    changed = json.loads((retry_dir / "report.json").read_text())
    changed["execution"]["runtime_lock_hash"] = "changed-lock"
    (retry_dir / "report.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="runtime or lock"):
        merge.main()


@pytest.mark.parametrize(
    "mode,backend",
    [("formal", "workspace"), ("workspace", "docker"), ("single-task-demo", "workspace")],
)
def test_trial_collection_rejects_mismatched_runtime_modes(mode, backend):
    merge = _load_script("merge_reports")
    identity = {"identity_hash": "same-method"}
    report = _formal_report("trial", [], identity)
    report["run_mode"], report["execution"]["backend"] = mode, backend
    with pytest.raises(ValueError, match="matching Docker or workspace"):
        merge.validate_report(report, identity, "tau", "tau.skill-evolution.v3")


def test_launcher_stage_commands_and_order():
    launcher = _load_script("launch_matrix")
    command = launcher.build_command(
        None,
        "skillsbench",
        Path("/c.yaml"),
        Path("/run"),
        "dialogue-parser",
        "benign",
        stage="no-skill",
    )
    assert command[3] == "evaluate" and command[-2:] == ["--no-interim-report", "--no-skill"]
    assert "--no-skill" not in launcher.build_command(
        None, "skillsbench", Path("/c.yaml"), Path("/run"), "dialogue-parser", "benign"
    )
    assert launcher.parse_stages("no-skill,run") == ("no-skill", "run")
    assert launcher.parse_stages("run") == ("run",)
    for bad in ("run,no-skill", "run,run", "", "smoke"):
        with pytest.raises(ValueError):
            launcher.parse_stages(bad)


def test_launcher_requeues_failed_stage_then_continues(tmp_path, monkeypatch):
    launcher = _load_script("launch_matrix")
    args = types.SimpleNamespace(
        r2sp=None,
        experiment="skillsbench",
        config=DEFAULT_CONFIG,
        run_dir=tmp_path,
        token_dir=tmp_path,
        accounts=["111"],
        max_concurrent=1,
        stagger_seconds=0,
        stages=("no-skill", "run"),
        max_attempts=2,
        retry_delay_seconds=0,
    )
    instance = launcher.Launcher(args, [("t", "benign")])
    started = []

    class Process:
        pid = 1

        def __init__(self, code):
            self.code = code

        def poll(self):
            return self.code

    codes = iter([2, 0, 0])

    def fake_start(task, arm):
        key = launcher.cell_key(task, arm)
        stage = instance.next_stage(key)
        started.append(stage)
        previous = instance.status_cells[key]["stages"].get(stage) or {}
        instance.status_cells[key]["stages"][stage] = {
            "pid": 1,
            "started_at": "t",
            "finished_at": None,
            "exit_code": None,
            "attempts": int(previous.get("attempts", 0)) + 1,
            "history": list(previous.get("history", [])),
            "requeued": False,
        }
        instance.status_cells[key].update(stage=stage, started_at="t")
        instance.processes[key] = (Process(next(codes)), io.BytesIO())

    instance.start = fake_start
    assert instance.run() == 0
    assert started == ["no-skill", "no-skill", "run"]
    cell = instance.status_cells["t|benign"]
    assert cell["stages"]["no-skill"]["attempts"] == 2
    assert cell["stages"]["no-skill"]["history"] == [{"exit_code": 2}]
    assert cell["exit_code"] == 0 and cell["finished_at"] is not None


def test_launcher_live_concurrency_file_overrides_argument(tmp_path):
    launcher = _load_script("launch_matrix")
    control = tmp_path / "max.txt"
    args = types.SimpleNamespace(
        r2sp=None,
        experiment="tau",
        config=DEFAULT_CONFIG,
        run_dir=tmp_path,
        token_dir=tmp_path,
        accounts=["111"],
        max_concurrent=7,
        stagger_seconds=0,
        max_concurrent_file=control,
    )
    instance = launcher.Launcher(args, [("t", "benign")])
    assert instance.max_concurrent() == 7
    control.write_text("3\n")
    assert instance.max_concurrent() == 3
    control.write_text("garbage")
    assert instance.max_concurrent() == 7
