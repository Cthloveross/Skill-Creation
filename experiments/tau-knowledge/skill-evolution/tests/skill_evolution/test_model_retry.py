"""Bounded re-sends of unobserved transport failures; a received sample is never resent."""

from __future__ import annotations

import base64
import io
import json
import urllib.error

import pytest
from tau_skill_evolution.dense import DenseServiceError, OpenAICompatibleEmbeddingClient
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import (
    CredentialError,
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
    VllmTextTokenCounter,
    retry_delay_seconds,
)

ENDPOINT = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
MESSAGES = [{"role": "user", "content": "offline fixture"}]


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _completed(text="ok"):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 3, "output_tokens": 1},
    }


def _http_error(code):
    return urllib.error.HTTPError("https://offline", code, "error", {}, io.BytesIO(b"{}"))


@pytest.mark.parametrize(
    "failure,posts",
    [
        (TimeoutError("offline timeout"), 3),
        (urllib.error.URLError(TimeoutError("offline timeout")), 3),
        (ConnectionResetError("offline reset"), 6),
        (urllib.error.URLError(ConnectionRefusedError("offline")), 6),
    ],
)
def test_exhausted_transport_failure_is_unknown_and_never_resent_on_resume(
    tmp_path, failure, posts
):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise failure

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    journal = Journal(tmp_path)
    for _ in range(2):
        with pytest.raises(UnknownOperation):
            client.complete_journaled(journal, "s0", {}, MESSAGES)
    # Timeouts are re-sent at most twice, other transport failures up to the attempt
    # budget; once the budget is spent the operation is UNKNOWN and resume never posts.
    assert len(calls) == posts and journal.status("s0") == "UNKNOWN"
    assert [event["reason"] for event in client.retry_events][:1] in (
        ["timeout"],
        [type(getattr(failure, "reason", failure)).__name__],
    )


def test_empty_completed_output_is_resent_then_returned_as_empty_turn(tmp_path):
    empty = json.dumps({"status": "completed", "output": [], "usage": {"input_tokens": 1}})
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return _Response(empty.encode())

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    journal = Journal(tmp_path)
    result = client.complete_journaled(journal, "s0", {}, MESSAGES)
    assert result["content"] == "" and result["empty_output"] and result["tool_calls"] == []
    assert len(calls) == client.retry_attempts and journal.status("s0") == "COMPLETED"
    assert {event["reason"] for event in client.retry_events} == {"empty_output"}
    # Resume reuses the sealed empty turn without another POST.
    assert client.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == ""
    assert len(calls) == client.retry_attempts


def test_empty_output_then_real_output_observes_one_sample(tmp_path):
    empty = json.dumps({"status": "completed", "output": [], "usage": {"input_tokens": 1}})
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return _Response((empty if len(calls) == 1 else json.dumps(_completed())).encode())

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    assert client.complete_journaled(Journal(tmp_path), "s0", {}, MESSAGES)["content"] == "ok"
    assert len(calls) == 2


def test_transport_failure_then_success_observes_exactly_one_sample(tmp_path):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) < 3:
            raise urllib.error.URLError(ConnectionResetError("offline reset"))
        return _Response(json.dumps(_completed()).encode())

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    journal = Journal(tmp_path)
    assert client.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == "ok"
    assert len(calls) == 3 and journal.status("s0") == "COMPLETED"
    assert len(client.usage_history) == 1 and len(client.retry_events) == 2


def test_retry_budget_can_be_disabled_for_single_post_semantics(tmp_path):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise TimeoutError("offline timeout")

    client = OpenAICompatibleClient(
        ENDPOINT, api_key="offline", opener=opener, retry_attempts=1, timeout_retry_attempts=0
    )
    with pytest.raises(UnknownOperation):
        client.complete_journaled(Journal(tmp_path), "s0", {}, MESSAGES)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "code,posts", [(400, 1), (401, 1), (403, 1), (429, 6), (500, 6), (502, 6), (503, 6), (504, 6)]
)
def test_received_http_error_is_preserved_after_bounded_resends(tmp_path, code, posts):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise _http_error(code)

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    journal = Journal(tmp_path)
    for _ in range(2):
        with pytest.raises(ModelClientError) as error:
            client.complete_journaled(journal, "s0", {}, MESSAGES)
        assert error.value.status == code
    # Rejections (429/5xx) prove no sample was produced and are re-sent up to the
    # budget; client errors are final. The last received status is sealed once.
    assert len(calls) == posts and journal.status("s0") == "RECEIVED_INVALID"
    if code in (401, 403):
        assert journal.authentication_failure() == code
        with pytest.raises(ModelClientError):
            client.complete_journaled(journal, "next-cell", {}, MESSAGES)
        assert len(calls) == 1 and journal.status("next-cell") == "NOT_SENT"


@pytest.mark.parametrize(
    "body,code,posts",
    [
        (b"not JSON", "invalid_json", 1),
        (
            json.dumps({"status": "in_progress", "output": []}).encode(),
            "server_failed_response",
            6,
        ),
        (json.dumps({"status": "queued", "output": []}).encode(), "server_failed_response", 6),
        (json.dumps({"status": "failed", "output": []}).encode(), "server_failed_response", 6),
        (
            json.dumps(
                {"status": "completed", "output": [{"type": "unexpected"}], "usage": {}}
            ).encode(),
            "invalid_response",
            1,
        ),
    ],
)
def test_provider_bytes_survive_received_invalid_and_recovery(tmp_path, body, code, posts):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return _Response(body)

    journal = Journal(tmp_path)
    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    for _ in range(2):
        with pytest.raises(ModelClientError) as error:
            client.complete_journaled(journal, "s0", {}, MESSAGES)
        assert error.value.code == code
    raw = json.loads(next(tmp_path.glob("*/raw-response.json")).read_text())
    assert base64.b64decode(raw["body_base64"]) == body
    # Server-side failed/unfinished bodies carry no sample and are re-sent up to the
    # budget; completed-but-invalid bodies are received results and sealed once.
    assert len(calls) == posts and journal.status("s0") == "RECEIVED_INVALID"


def test_received_bytes_are_durable_before_normalization_and_resume(tmp_path):
    body = json.dumps(_completed()).encode()
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return _Response(body)

    journal = Journal(tmp_path)
    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    original = client._normalize

    def crash(status, received, **kwargs):
        raw = json.loads(next(tmp_path.glob("*/raw-response.json")).read_text())
        assert base64.b64decode(raw["body_base64"]) == received == body
        raise KeyboardInterrupt()

    client._normalize = crash
    with pytest.raises(KeyboardInterrupt):
        client.complete_journaled(journal, "s0", {}, MESSAGES)
    client._normalize = original
    assert client.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == "ok"
    assert client.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == "ok"
    assert len(calls) == 1 and journal.status("s0") == "COMPLETED"
    assert len(client.usage_history) == 1


def test_raw_reparse_usage_has_stable_operation_key_without_another_post(tmp_path, monkeypatch):
    body = json.dumps(_completed()).encode()
    calls = []
    usage_path = tmp_path / "usage.jsonl"

    def opener(request, timeout):
        calls.append(request)
        return _Response(body)

    def client():
        return OpenAICompatibleClient(
            ENDPOINT,
            api_key="offline",
            opener=opener,
            usage_path=usage_path,
            usage_role="generator",
        )

    journal = Journal(tmp_path / "journal")
    first = client()
    with monkeypatch.context() as patch:
        patch.setattr(journal, "_seal", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            first.complete_journaled(journal, "s0", {}, MESSAGES)
    resumed = client()
    assert resumed.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == "ok"
    rows = [json.loads(line) for line in usage_path.read_text().splitlines()]
    assert len(calls) == 1 and len(rows) == 2
    assert rows[0]["operation_key"] == rows[1]["operation_key"]
    assert len(rows[0]["operation_key"]) == 64
    assert (
        first.usage_history
        == resumed.usage_history
        == ({"input_tokens": 3, "output_tokens": 1, "prompt_tokens": 3, "completion_tokens": 1},)
    )
    resumed.complete_journaled(journal, "next-operation", {}, MESSAGES)
    rows = [json.loads(line) for line in usage_path.read_text().splitlines()]
    assert rows[-1]["operation_key"] != rows[0]["operation_key"]
    resumed.complete(MESSAGES)
    rows = [json.loads(line) for line in usage_path.read_text().splitlines()]
    assert "operation_key" not in rows[-1]


def test_pre_admission_and_credential_errors_are_not_sent_and_can_resume(tmp_path):
    class Counter:
        value = 200

        def count(self, messages, **kwargs):
            return self.value

    counter = Counter()
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return _Response(json.dumps(_completed()).encode())

    def missing():
        raise CredentialError("credential_unavailable", "offline")

    client = OpenAICompatibleClient(
        ENDPOINT,
        api_key=missing,
        opener=opener,
        config=GenerationConfig(max_input_tokens=100),
        token_counter=counter,
    )
    journal = Journal(tmp_path)
    with pytest.raises(CredentialError):
        client.complete_journaled(journal, "s0", {}, MESSAGES)
    assert journal.status("s0") == "NOT_SENT" and not journal.dispatched("s0")
    client.api_key = "offline"
    with pytest.raises(ModelClientError, match="input exceeds"):
        client.complete_journaled(journal, "s0", {}, MESSAGES)
    assert not calls and journal.status("s0") == "NOT_SENT"
    counter.value = 10
    assert client.complete_journaled(journal, "s0", {}, MESSAGES)["content"] == "ok"
    assert len(calls) == 1


def test_response_read_reset_is_resent_within_budget_then_unknown(tmp_path):
    class BrokenResponse(_Response):
        def read(self):
            raise ConnectionResetError("offline response interrupted")

    calls = []

    def opener(request, timeout):
        calls.append(request)
        return BrokenResponse(b"")

    client = OpenAICompatibleClient(ENDPOINT, api_key="offline", opener=opener)
    with pytest.raises(UnknownOperation):
        client.complete_journaled(Journal(tmp_path), "s0", {}, MESSAGES)
    assert len(calls) == client.retry_attempts


@pytest.mark.parametrize("timeout", [False, True])
def test_initial_generator_real_client_is_one_post_across_resume(tmp_path, timeout):
    from tau_skill_evolution.artifacts import FrozenBase
    from tau_skill_evolution.generator import CreationFailure, generate_initial

    class Counter:
        def count(self, messages, **kwargs):
            return 100

    base = FrozenBase(
        ({"page_id": "policy", "title": "Policy", "content": "Public reference."},),
        {"opening_message": "Help", "clarifications": [], "read_only_observations": []},
    )
    package = {"files": [{"path": "SKILL.md", "content": "Public task instructions."}]}
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if fail:
            raise TimeoutError("offline")
        return _Response(json.dumps(_completed(json.dumps(package))).encode())

    fail = timeout
    client = OpenAICompatibleClient(
        ENDPOINT, api_key="offline", opener=opener, token_counter=Counter()
    )
    journal = Journal(tmp_path)
    bundles = []
    for _ in range(2):
        if timeout:
            with pytest.raises(CreationFailure, match="generation_result_unknown"):
                generate_initial(client, base.public_inputs, base, journal=journal)
        else:
            bundles.append(generate_initial(client, base.public_inputs, base, journal=journal))
    assert len(calls) == (3 if timeout else 1)
    if bundles:
        assert bundles[0].bundle_hash == bundles[1].bundle_hash


def test_retry_delay_honours_retry_after_and_caps():
    assert retry_delay_seconds(1, None, base_seconds=2.0) == 2.0
    assert retry_delay_seconds(3, None, base_seconds=2.0) == 8.0
    assert retry_delay_seconds(9, None, base_seconds=2.0) == 60.0
    assert retry_delay_seconds(1, "7", base_seconds=2.0) == 7.0


def test_tokenizer_retries_deterministic_transport():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise ConnectionResetError("offline")
        return _Response(b'{"count": 4}')

    counter = VllmTextTokenCounter(
        "http://127.0.0.1:18140/v1", model="m", opener=opener, retry_backoff_seconds=0
    )
    assert counter("text") == 4 and len(calls) == 2


def test_embedding_gateway_retries_are_bounded():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise _http_error(502)

    client = OpenAICompatibleEmbeddingClient(
        opener=opener, retry_attempts=2, retry_backoff_seconds=0
    )
    with pytest.raises(DenseServiceError):
        client.embed_query("q")
    assert len(calls) == 2
