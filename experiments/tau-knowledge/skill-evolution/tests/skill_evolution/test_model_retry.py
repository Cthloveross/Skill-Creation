"""Bounded retries for rejected model requests and flaky loopback helpers."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from tau_skill_evolution.dense import DenseServiceError, OpenAICompatibleEmbeddingClient
from tau_skill_evolution.model import (
    ModelClientError,
    OpenAICompatibleClient,
    VllmTextTokenCounter,
    retry_delay_seconds,
)

ENDPOINT = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200
        self.headers = {}

    def read(self, *_args) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc) -> None:
        return None


def _completed(text: str = "ok") -> dict:
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


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://x", code, "err", headers, io.BytesIO(b"{}"))


def test_retry_delay_honours_retry_after_and_caps() -> None:
    assert retry_delay_seconds(1, None, base_seconds=2.0) == 2.0
    assert retry_delay_seconds(3, None, base_seconds=2.0) == 8.0
    assert retry_delay_seconds(9, None, base_seconds=2.0) == 60.0
    assert retry_delay_seconds(1, "7", base_seconds=2.0) == 7.0
    assert retry_delay_seconds(1, "garbage", base_seconds=2.0) == 2.0


def test_model_request_retries_429_then_succeeds() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(429, retry_after="0")
        return _Response(_completed())

    client = OpenAICompatibleClient(
        ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0, usage_role="analyzer"
    )
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result["content"] == "ok"
    assert len(calls) == 3
    assert [event["reason"] for event in client.retry_events] == ["http_429", "http_429"]


def test_model_request_gives_up_after_bounded_attempts() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        raise _http_error(503)

    client = OpenAICompatibleClient(
        ENDPOINT, api_key="k", opener=opener, retry_attempts=3, retry_backoff_seconds=0
    )
    with pytest.raises(ModelClientError) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.code == "http_error" and info.value.status == 503
    assert len(calls) == 3


def test_model_request_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        raise _http_error(400)

    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    with pytest.raises(ModelClientError):
        client.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


def test_model_request_timeouts_are_resent_a_bounded_number_of_times() -> None:
    for failure in (TimeoutError("slow"), urllib.error.URLError(TimeoutError("timed out"))):
        calls: list[int] = []

        def opener(request, timeout, failure=failure, calls=calls):
            calls.append(1)
            if len(calls) < 3:
                raise failure
            return _Response(_completed())

        client = OpenAICompatibleClient(
            ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0
        )
        assert client.complete([{"role": "user", "content": "hi"}])["content"] == "ok"
        assert len(calls) == 3
        assert [event["reason"] for event in client.retry_events] == ["timeout", "timeout"]


def test_model_request_timeout_retries_can_be_disabled_and_are_bounded() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        raise TimeoutError("slow")

    client = OpenAICompatibleClient(
        ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0, timeout_retry_attempts=0
    )
    with pytest.raises(ModelClientError) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.code == "transport_error" and len(calls) == 1
    calls.clear()
    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    with pytest.raises(ModelClientError):
        client.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 3


def test_model_request_retries_connection_refused() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.URLError(ConnectionRefusedError("refused"))
        return _Response(_completed())

    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    assert client.complete([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert len(calls) == 2


def test_tokenizer_retries_transport_then_counts() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionResetError("reset")
        return _Response({"count": 4})

    counter = VllmTextTokenCounter(
        "http://127.0.0.1:18140/v1", model="m", opener=opener, retry_backoff_seconds=0
    )
    assert counter("text") == 4
    assert len(calls) == 2


def test_embedding_client_retries_gateway_errors_then_fails_closed() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        raise _http_error(502)

    client = OpenAICompatibleEmbeddingClient(
        opener=opener, retry_attempts=2, retry_backoff_seconds=0
    )
    with pytest.raises(DenseServiceError) as info:
        client.embed_query("q")
    assert info.value.code == "http_error"
    assert len(calls) == 2


def test_model_request_retries_failed_status_body_then_succeeds() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            return _Response({"status": "failed", "error": {"code": "server_error"}, "output": []})
        return _Response(_completed())

    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    assert client.complete([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert len(calls) == 2
    assert client.retry_events[0]["reason"] == "response_status_failed"


def test_model_request_failed_status_exhausts_as_server_failure(capsys) -> None:
    def opener(request, timeout):
        return _Response({"status": "failed", "output": []})

    client = OpenAICompatibleClient(
        ENDPOINT, api_key="k", opener=opener, retry_attempts=2, retry_backoff_seconds=0
    )
    with pytest.raises(ModelClientError) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.code == "server_failed_response"


def test_invalid_response_logs_shape_without_text(capsys) -> None:
    def opener(request, timeout):
        return _Response(
            {
                "status": "completed",
                "output": [{"type": "mystery_item", "content": [{"type": "x", "text": "SECRET"}]}],
                "usage": {"input_tokens": 1},
            }
        )

    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    with pytest.raises(ModelClientError) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert info.value.code == "invalid_response"
    err = capsys.readouterr().err
    assert "bedrock_invalid_response" in err and "mystery_item" in err and "SECRET" not in err


def test_empty_completed_output_is_an_empty_assistant_message() -> None:
    calls: list[int] = []

    def opener(request, timeout):
        calls.append(1)
        return _Response({"status": "completed", "output": [], "usage": {"input_tokens": 3}})

    client = OpenAICompatibleClient(ENDPOINT, api_key="k", opener=opener, retry_backoff_seconds=0)
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result["content"] == "" and result["tool_calls"] == []
    assert result["finish_reason"] == "stop"
    assert len(calls) == 1 and client.retry_events == []
