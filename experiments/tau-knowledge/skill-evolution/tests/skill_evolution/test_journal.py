from __future__ import annotations

import json

import pytest
from tau_skill_evolution.journal import Journal, UnknownOperation


def test_dispatch_is_durable_and_reuses_raw_response_after_parse_crash(tmp_path):
    journal = Journal(tmp_path / "journal", identity={"config_hash": "c"})
    calls = []

    def call():
        requests = list((tmp_path / "journal").glob("*/request.json"))
        assert len(requests) == 1
        assert json.loads(requests[0].read_text())["payload"] == {"request": 1}
        calls.append(1)
        return {"content": "invalid JSON; raw response still preserved"}

    raw = journal.dispatch("s0", {"request": 1}, call)
    assert journal.completed("s0")
    restored = Journal(tmp_path / "journal", identity={"config_hash": "c"})
    assert restored.dispatch("s0", {"request": 1}, lambda: pytest.fail("must not resend")) == raw
    assert len(calls) == 1
    restored.record_result("s0", {"failed": True})
    assert restored.result("s0") == {"failed": True}
    with pytest.raises(ValueError, match="different"):
        restored.record_result("s0", {"failed": False})
    with pytest.raises(ValueError, match="differs"):
        restored.dispatch("s0", {"request": 2}, call)


def test_unknown_dispatch_is_never_automatically_repeated(tmp_path):
    journal = Journal(tmp_path)
    calls = []

    def unknown():
        calls.append(1)
        raise TimeoutError("could have completed remotely")

    with pytest.raises(UnknownOperation):
        journal.dispatch("s0", {}, unknown)
    with pytest.raises(UnknownOperation):
        journal.dispatch("s0", {}, unknown)
    assert len(calls) == 1
    assert journal.result("s0") is None


def test_authentication_failure_is_numeric_and_stays_non_retriable(tmp_path):
    from tau_skill_evolution.model import ModelClientError

    journal = Journal(tmp_path)

    def failure():
        raise ModelClientError("http_error", "private body must not be persisted", status=401)

    with pytest.raises(UnknownOperation):
        journal.dispatch("s0", {}, failure)
    assert journal.authentication_failure() == 401
    assert "private body" not in "".join(path.read_text() for path in tmp_path.rglob("*.json"))
    with pytest.raises(UnknownOperation):
        journal.dispatch("s0", {}, lambda: pytest.fail("unknown S0 is not retried"))


def test_checkpoint_rejects_old_or_changed_identity(tmp_path):
    journal = Journal(tmp_path / "new", identity={"corpus_hash": "a"})
    journal.dispatch("a", {}, lambda: {"result": 1})
    with pytest.raises(ValueError, match="identity"):
        Journal(tmp_path / "new", identity={"corpus_hash": "b"})
    old = tmp_path / "old"
    old.mkdir()
    (old / "checkpoint.json").write_text("{}")
    with pytest.raises(ValueError, match="identity"):
        Journal(old)


def test_journal_response_and_derived_result_tampering_detected(tmp_path):
    journal = Journal(tmp_path)
    journal.dispatch("phase", {}, lambda: {"base": "a"})
    journal.record_result("phase", {"sealed": True})
    result_path = next(tmp_path.glob("*/result.json"))
    damaged = json.loads(result_path.read_text())
    damaged["result"]["sealed"] = False
    result_path.write_text(json.dumps(damaged))
    with pytest.raises(ValueError, match="integrity"):
        journal.result("phase")
    response_path = next(tmp_path.glob("*/response.json"))
    damaged = json.loads(response_path.read_text())
    damaged["response"]["base"] = "b"
    response_path.write_text(json.dumps(damaged))
    with pytest.raises(ValueError, match="integrity"):
        journal.response("phase")
