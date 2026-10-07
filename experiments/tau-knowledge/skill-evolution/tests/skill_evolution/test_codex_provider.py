"""Native Codex transport boundaries without paid inference or real credentials."""

from __future__ import annotations

import ast
import base64
import contextlib
import http.client
import io
import json
import socket
import sys
import urllib.error

import pytest
from tau_skill_evolution.codex_provider import (
    OUTPUT_TOKEN_BUDGET_STOP,
    _completed_response,
    _response_sse,
    open_provider,
)
from tau_skill_evolution.core._canonical import canonical_json_sha256
from tau_skill_evolution.journal import UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded, ModelClientError

PROVIDER = {
    "api_base": "https://bedrock-mantle.us-east-1.api.aws/openai/v1",
    "api_key_env": "CODEX_PROVIDER_OFFLINE_TOKEN",
    "model": "openai.gpt-5.5",
}
CONTROLS = {
    "agent": {"reasoning_effort": "medium", "max_output_tokens": 8},
    "user": {"reasoning_effort": "medium", "max_output_tokens": 8},
    "max_input_tokens": 1000,
    "assistant_completion_budget": 16,
}
MESSAGES_PROVIDER = {
    **PROVIDER,
    "model": "anthropic.claude-opus-4-8",
    "api_base": "https://bedrock-mantle.us-east-1.api.aws/anthropic/v1",
    "transport": "bedrock-messages",
}
UNBOUNDED_CONTROLS = {
    **CONTROLS,
    "agent": {"reasoning_effort": "high", "max_output_tokens": None},
    "user": {"reasoning_effort": "medium", "max_output_tokens": None},
    "assistant_completion_budget": None,
}


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=5)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(str(self.path))


def completed(output_tokens=2):
    return {
        "id": "resp_offline",
        "object": "response",
        "status": "completed",
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done", "annotations": []}],
            },
            {
                "id": "fc_1",
                "type": "function_call",
                "call_id": "call_1",
                "name": "exec_command",
                "arguments": '{"cmd":"pwd"}',
            },
            {
                "id": "custom_1",
                "type": "custom_tool_call",
                "call_id": "call_2",
                "name": "apply_patch",
                "input": "*** Begin Patch\n*** End Patch",
            },
        ],
        "usage": {"input_tokens": 20, "output_tokens": output_tokens},
    }


def payload(text="task"):
    return {"model": "client-model", "input": text, "stream": True}


def request(gateway, value):
    with contextlib.closing(UnixConnection(gateway.socket_path)) as connection:
        connection.request("POST", "/v1/responses", json.dumps(value))
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv(PROVIDER["api_key_env"], "offline-host-secret")

    def create(opener, **kwargs):
        return open_provider(
            tmp_path / "relay",
            kwargs.pop("provider", PROVIDER),
            kwargs.pop("controls", CONTROLS),
            tmp_path / "journal",
            {"episode": "offline"},
            token_counter=kwargs.pop("token_counter", lambda text: 50),
            timeout_seconds=5,
            opener=opener,
            **kwargs,
        )

    return create


@pytest.mark.parametrize("streaming", [False, True])
def test_messages_bridge_preserves_native_tools_thinking_raw_and_resume(
    factory, tmp_path, streaming
):
    calls, raw_bodies = [], []
    thought = {"type": "thinking", "thinking": "private fixture thought", "signature": "signed"}
    native = {
        **payload(),
        "stream": streaming,
        "instructions": "Use the native tools.",
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "description": "Native execution tools",
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
                    },
                    {"type": "custom", "name": "apply_patch", "format": {"type": "text"}},
                ],
            }
        ],
    }

    def opener(req, timeout):
        assert timeout > 0
        outgoing = json.loads(req.data)
        calls.append(outgoing)
        assert req.full_url == MESSAGES_PROVIDER["api_base"] + "/messages"
        assert req.get_header("Anthropic-version") == "2023-06-01"
        assert outgoing["model"] == "anthropic.claude-opus-4-8"
        assert outgoing["stream"] is False and outgoing["max_tokens"] == 128000
        if len(calls) == 1:
            aliases = [tool["name"] for tool in outgoing["tools"]]
            assert len(set(aliases)) == 2 and all("." not in name for name in aliases)
            content = [
                thought,
                {
                    "type": "tool_use",
                    "id": "native-fn",
                    "name": aliases[0],
                    "input": {"cmd": "pwd"},
                },
                {
                    "type": "tool_use",
                    "id": "native-patch",
                    "name": aliases[1],
                    "input": {"input": "*** Begin Patch\n*** End Patch"},
                },
            ]
            stop = "tool_use"
        else:
            blocks = [block for message in outgoing["messages"] for block in message["content"]]
            assert thought in blocks
            assert {"type": "tool_result", "tool_use_id": "native-fn", "content": "/app"} in blocks
            assert {
                "type": "tool_result",
                "tool_use_id": "native-patch",
                "content": "patched",
            } in blocks
            content, stop = [{"type": "text", "text": "Done."}], "end_turn"
        raw = json.dumps(
            {
                "id": f"msg_fixture_{len(calls)}",
                "type": "message",
                "role": "assistant",
                "model": "anthropic.claude-opus-4-8",
                "content": content,
                "stop_reason": stop,
                "usage": {"input_tokens": 20, "output_tokens": 3},
            }
        ).encode()
        raw_bodies.append(raw)
        return Response(raw)

    kwargs = {"provider": MESSAGES_PROVIDER, "controls": UNBOUNDED_CONTROLS}
    with factory(opener, **kwargs) as gateway:
        original_normalize = gateway._normalize

        def normalize(status, body, **options):
            sealed = list((tmp_path / "journal").glob("*/raw-response.json"))
            assert any(
                base64.b64decode(json.loads(path.read_text())["body_base64"]) == body
                for path in sealed
            )
            return original_normalize(status, body, **options)

        gateway._normalize = normalize
        first_body, content_type = gateway.respond(json.dumps(native).encode())
        first_response, received_stream = _completed_response(first_body)
        assert received_stream is streaming
        assert content_type == ("text/event-stream" if streaming else "application/json")
        reasoning, function, custom = first_response["output"]
        assert reasoning["type"] == "reasoning" and reasoning["summary"] == []
        assert "private fixture thought" not in first_body.decode()
        assert (function["type"], function["name"], function["namespace"]) == (
            "function_call",
            "exec_command",
            "functions",
        )
        assert (custom["type"], custom["name"], custom["namespace"]) == (
            "custom_tool_call",
            "apply_patch",
            "functions",
        )
        assert custom["input"] == "*** Begin Patch\n*** End Patch"
        following = {
            **native,
            "input": [
                {"role": "user", "content": "task"},
                *first_response["output"],
                {"type": "function_call_output", "call_id": "native-fn", "output": "/app"},
                {"type": "custom_tool_call_output", "call_id": "native-patch", "output": "patched"},
            ],
        }
        last = gateway.respond(json.dumps(following).encode())
        assert _completed_response(last[0])[0]["status"] == "completed"
        assert gateway.statistics["requests"] == 2 and gateway.statistics["output_tokens"] == 6
        assert (
            gateway.statistics["input_token_estimation_basis"]
            == "serialized_anthropic_messages_payload"
        )
        records = [
            json.loads(p.read_text())["response"]
            for p in (tmp_path / "journal").glob("*/response.json")
        ]
        assert all(row["provider_transport"] == "bedrock-messages" for row in records)
        assert all(
            row["response_origin"] == "host_messages_to_responses_conversion" for row in records
        )
        assert {base64.b64decode(row["body_base64"]) for row in records} == set(raw_bodies)
        requests = [
            json.loads(p.read_text())["payload"]
            for p in (tmp_path / "journal").glob("*/request.json")
        ]
        assert all(
            row["provider_request"]["model"] == MESSAGES_PROVIDER["model"] for row in requests
        )
        assert all("offline-host-secret" not in json.dumps(row) for row in requests)
    with factory(
        lambda *args, **options: pytest.fail("sealed response must not resend"), **kwargs
    ) as resumed:
        assert resumed.respond(json.dumps(following).encode()) == last
        assert resumed.statistics["requests"] == 2 and resumed.statistics["output_tokens"] == 6


def test_messages_unknown_post_stops_without_retries(factory):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        raise TimeoutError("offline transport loss")

    kwargs = {"provider": MESSAGES_PROVIDER, "controls": UNBOUNDED_CONTROLS}
    with factory(opener, **kwargs) as gateway, pytest.raises(UnknownOperation):
        gateway.respond(json.dumps(payload()).encode())
    with factory(
        lambda *args, **options: pytest.fail("unknown must not resend"), **kwargs
    ) as resumed:
        assert resumed.statistics["unknown_operation"]
        with pytest.raises(ModelClientError, match="halted"):
            resumed.respond(json.dumps(payload()).encode())
    assert len(calls) == 1


@pytest.mark.parametrize("output_tokens", [128000, 128001])
def test_messages_provider_limit_and_raw_only_recovery(factory, tmp_path, output_tokens):
    calls = []
    raw = {
        "id": "msg_limit",
        "type": "message",
        "role": "assistant",
        "model": MESSAGES_PROVIDER["model"],
        "content": [{"type": "text", "text": "Partial fixture result."}],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 10, "output_tokens": output_tokens},
    }

    def opener(req, timeout):
        calls.append(req)
        assert json.loads(req.data)["max_tokens"] == 128000
        return Response(json.dumps(raw).encode())

    kwargs = {"provider": MESSAGES_PROVIDER, "controls": UNBOUNDED_CONTROLS}
    expected_code = (
        OUTPUT_TOKEN_BUDGET_STOP
        if output_tokens == 128000
        else "provider_output_token_limit_exceeded"
    )
    with factory(opener, **kwargs) as gateway:
        if output_tokens == 128000:
            body, _ = gateway.respond(json.dumps(payload()).encode())
            canonical, _ = _completed_response(body)
            assert canonical["status"] == "incomplete"
            assert canonical["incomplete_details"] == {"reason": "max_output_tokens"}
            assert gateway.statistics["terminal_stop"]["kind"] == "budget"
        else:
            with pytest.raises(ModelClientError, match="exceeded requested output limit"):
                gateway.respond(json.dumps(payload()).encode())
            assert gateway.statistics["terminal_stop"] is None
        assert gateway.statistics["failure_code"] == expected_code
        assert gateway.statistics["requests"] == 1
        assert gateway.statistics["output_tokens"] == output_tokens
        directory = next((tmp_path / "journal").glob("*/response.json")).parent
        saved = json.loads((directory / "response.json").read_text())["response"]
        assert json.loads(base64.b64decode(saved["body_base64"])) == raw
        assert saved["response_origin"] == "host_messages_to_responses_conversion"
    (directory / "response.json").unlink()  # Crash after raw receipt, before normalized seal.
    (directory / "state.json").write_text('{"status":"UNKNOWN"}')
    with factory(
        lambda *args, **options: pytest.fail("restore must not POST"), **kwargs
    ) as resumed:
        assert resumed.statistics["halted"] and not resumed.statistics["unknown_operation"]
        assert resumed.statistics["failure_code"] == expected_code
        assert resumed.statistics["output_tokens"] == output_tokens
        with pytest.raises(ModelClientError, match="halted"):
            resumed.respond(json.dumps(payload()).encode())
        assert (directory / "response.json").is_file()
    assert len(calls) == 1


def test_native_sse_and_tools_are_preserved_and_bytes_sealed_before_parse(factory, tmp_path):
    calls = []
    stream = _response_sse(completed())

    def opener(req, timeout):
        calls.append(req)
        return Response(stream)

    with factory(opener) as gateway:
        original = gateway._normalize

        def normalize(status, body):
            raw = json.loads(next((tmp_path / "journal").glob("*/raw-response.json")).read_text())
            assert base64.b64decode(raw["body_base64"]) == stream
            return original(status, body)

        gateway._normalize = normalize
        status, content_type, body = request(gateway, payload())
        assert (status, content_type, body) == (200, "text/event-stream", stream)
        assert request(gateway, payload())[2] == stream
        assert len(calls) == gateway.statistics["requests"] == 1
        outgoing = json.loads(calls[0].data)
        assert outgoing["model"] == "openai.gpt-5.5"
        assert outgoing["reasoning"]["effort"] == "medium"
        assert outgoing["max_output_tokens"] == 8 and outgoing["store"] is False
        assert outgoing["stream"] is True and outgoing["input"] == "task"
        assert gateway.statistics["output_tokens"] == 2
        assert gateway.statistics["input_tokens_estimate"] == 50
        assert "offline-host-secret" not in gateway.relay_path.read_text()
        assert all(
            "offline-host-secret" not in path.read_text()
            for path in (tmp_path / "journal").rglob("*.json")
        )
    assert not gateway.socket_path.exists() and not gateway.relay_path.exists()
    assert gateway.statistics["closed"] and not gateway.statistics["halted"]


def test_nonstream_fallback_emits_function_custom_and_text_events(factory):
    result = completed()
    with factory(lambda *args, **kwargs: Response(json.dumps(result).encode())) as gateway:
        _, content_type, stream = request(gateway, payload())
    events = [
        json.loads(line[6:]) for line in stream.decode().splitlines() if line.startswith("data: ")
    ]
    assert content_type == "text/event-stream"
    kinds = [event["type"] for event in events]
    assert "response.function_call_arguments.delta" in kinds
    assert "response.custom_tool_call_input.done" in kinds
    assert "response.output_text.done" in kinds
    assert events[-1]["response"] == result


def test_host_refreshes_bearer_for_each_request_and_caps_cumulative_output(factory, monkeypatch):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(completed(8)).encode())

    with factory(opener) as gateway:
        gateway.respond(json.dumps(payload("first")).encode())
        monkeypatch.setenv(PROVIDER["api_key_env"], "new-offline-host-secret")
        gateway.respond(json.dumps(payload("second")).encode())
        with pytest.raises(ModelClientError, match="budget exhausted"):
            gateway.respond(json.dumps(payload("third")).encode())
        assert gateway.statistics["requests"] == 2
        assert calls[0].get_header("Authorization") == "Bearer offline-host-secret"
        assert calls[1].get_header("Authorization") == "Bearer new-offline-host-secret"


def test_unbounded_output_omits_client_cap_accounts_usage_and_restores_without_replay(factory):
    calls = []
    controls = {
        **CONTROLS,
        "agent": {"reasoning_effort": "medium", "max_output_tokens": None},
        "user": {"reasoning_effort": "medium", "max_output_tokens": None},
        "assistant_completion_budget": None,
    }

    def opener(req, timeout):
        calls.append(req)
        assert "max_output_tokens" not in json.loads(req.data)
        return Response(json.dumps(completed(70000)).encode())

    first = {**payload("first"), "max_output_tokens": 1}
    with factory(opener, controls=controls) as gateway:
        original = gateway.respond(json.dumps(first).encode())
        assert gateway.statistics["output_tokens"] == 70000
        assert not gateway.statistics["halted"]
    with factory(opener, controls=controls) as resumed:
        assert resumed.respond(json.dumps(first).encode()) == original
        resumed.respond(json.dumps(payload("second")).encode())
        assert resumed.statistics["output_tokens"] == 140000
        assert resumed.statistics["requests"] == len(calls) == 2
        assert [entry["output_tokens"] for entry in resumed.statistics["usage"]] == [70000, 70000]
        assert not resumed.statistics["halted"]
        assert resumed.statistics["terminal_stop"] is None


@pytest.mark.parametrize("per_request,episode,expected", [(None, 16, 16), (8, None, 8)])
def test_optional_output_limits_preserve_the_remaining_finite_limit(
    factory, per_request, episode, expected
):
    calls = []
    controls = {
        **CONTROLS,
        "agent": {"reasoning_effort": "medium", "max_output_tokens": per_request},
        "assistant_completion_budget": episode,
    }

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(completed()).encode())

    with factory(opener, controls=controls) as gateway:
        gateway.respond(json.dumps(payload()).encode())
        assert json.loads(calls[0].data)["max_output_tokens"] == expected
        assert not gateway.statistics["halted"]


def test_provider_incomplete_output_limit_still_halts_without_a_local_cap(factory):
    controls = {
        **CONTROLS,
        "agent": {"reasoning_effort": "medium", "max_output_tokens": None},
        "assistant_completion_budget": None,
    }
    response = {
        **completed(70000),
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    with factory(
        lambda *args, **kwargs: Response(json.dumps(response).encode()), controls=controls
    ) as gateway:
        gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["failure_code"] == OUTPUT_TOKEN_BUDGET_STOP
        assert gateway.statistics["halted"]
        assert gateway.statistics["output_tokens"] == 70000
        assert gateway.statistics["terminal_stop"]["kind"] == "budget"


def test_provider_output_budget_violation_retains_usage_and_never_replays(factory, tmp_path):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(completed(9)).encode())

    with factory(opener) as gateway:
        with pytest.raises(ModelClientError, match="exceeded requested output limit"):
            gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["failure_code"] == "provider_output_token_limit_exceeded"
        assert gateway.statistics["requests"] == 1 and gateway.statistics["output_tokens"] == 9
        assert gateway.statistics["usage"][0]["output_tokens"] == 9
        assert gateway.statistics["output_budget_violation"] == {
            "requested_max_output_tokens": 8,
            "reported_output_tokens": 9,
        }
        assert gateway.statistics["halted"] and not gateway.statistics["unknown_operation"]
        assert next((tmp_path / "journal").glob("*/raw-response.json")).is_file()
    with factory(opener) as resumed:
        with pytest.raises(ModelClientError, match="halted"):
            resumed.respond(json.dumps(payload()).encode())
        assert resumed.statistics["failure_code"] == "provider_output_token_limit_exceeded"
        assert resumed.statistics["output_tokens"] == 9
    assert len(calls) == 1


def test_opaque_continuations_and_native_tool_inputs_are_preserved(factory):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(completed()).encode())

    native = payload()
    native["input"] = [
        {
            "type": "reasoning",
            "id": "rs_fixture",
            "encrypted_content": "opaque-fixture",
            "summary": [],
        },
        {
            "type": "function_call",
            "id": "fc_fixture",
            "call_id": "original-call-id",
            "name": "exec_command",
            "arguments": '{"cmd":"pwd"}',
        },
        {"type": "function_call_output", "call_id": "original-call-id", "output": "/app"},
    ]
    native["include"] = ["reasoning.encrypted_content"]
    with factory(opener) as gateway:
        gateway.respond(json.dumps(native).encode())
    outgoing = json.loads(calls[0].data)
    assert outgoing["input"] == native["input"]
    assert outgoing["include"] == native["include"]


def test_received_authentication_error_is_durable_and_stops_future_posts(factory, tmp_path):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b"{}"))

    with factory(opener) as gateway:
        assert request(gateway, payload())[0] == 401
        assert request(gateway, payload("other"))[0] == 502
        assert gateway.statistics["requests"] == 1 and len(calls) == 1
        assert gateway.statistics["authentication_status"] == 401
        assert gateway.statistics["halted"] and not gateway.statistics["unknown_operation"]
        raw = json.loads(next((tmp_path / "journal").glob("*/raw-response.json")).read_text())
        assert raw["http_status"] == 401 and base64.b64decode(raw["body_base64"]) == b"{}"


def test_unknown_post_halts_same_episode_and_recovery_never_dispatches(factory):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        raise TimeoutError("offline timeout")

    with factory(opener) as gateway:
        with pytest.raises(UnknownOperation):
            gateway.respond(json.dumps(payload()).encode())
        with pytest.raises(ModelClientError, match="halted"):
            gateway.respond(json.dumps(payload("different")).encode())
        assert gateway.statistics["unknown_operation"]
    with factory(opener) as resumed:
        with pytest.raises(ModelClientError, match="halted"):
            resumed.respond(json.dumps(payload()).encode())
        assert resumed.statistics["unknown_operation"] and resumed.statistics["requests"] == 1
    assert len(calls) == 1


def test_completed_recovery_reuses_native_response_and_usage(factory):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(completed()).encode())

    with factory(opener) as gateway:
        first = gateway.respond(json.dumps(payload()).encode())
    with factory(opener) as resumed:
        assert resumed.respond(json.dumps(payload()).encode()) == first
        assert resumed.statistics["requests"] == 1
        assert resumed.statistics["output_tokens"] == 2
        assert resumed.statistics["usage"][0]["operation_key"] == canonical_json_sha256(payload())
    assert len(calls) == 1


@pytest.mark.parametrize(
    "reason,code,kind",
    [
        ("max_output_tokens", OUTPUT_TOKEN_BUDGET_STOP, "budget"),
        ("interrupted", "provider_response_interrupted", "interrupted"),
        ("content_filter", "provider_content_filter", "policy"),
        ("unrecognized", "provider_incomplete_reason_unknown", "provider"),
        (None, "provider_incomplete_reason_unknown", "provider"),
    ],
)
def test_incomplete_response_is_delivered_unchanged_and_restores_terminal_stop(
    factory, tmp_path, reason, code, kind
):
    calls = []
    response = {**completed(8), "status": "incomplete", "incomplete_details": {"reason": reason}}
    stream = _response_sse(response)

    def opener(req, timeout):
        calls.append(req)
        return Response(stream)

    with factory(opener) as gateway:
        assert gateway.respond(json.dumps(payload()).encode()) == (stream, "text/event-stream")
        expected = {
            "kind": kind,
            "reason": reason,
            "operation_key": canonical_json_sha256(payload()),
            "response_status": "incomplete",
        }
        assert gateway.statistics["terminal_stop"] == expected
        assert gateway.statistics["failure_code"] == code and gateway.statistics["halted"]
        assert gateway.statistics["output_tokens"] == 8
        assert gateway.journal.status(expected["operation_key"]) == "COMPLETED"
        with pytest.raises(ModelClientError, match="halted"):
            gateway.respond(json.dumps(payload("next")).encode())
    with factory(opener) as resumed:
        assert resumed.statistics["terminal_stop"] == expected
        assert resumed.statistics["failure_code"] == code and resumed.statistics["halted"]
        assert resumed.statistics["requests"] == 1 and resumed.statistics["output_tokens"] == 8
        assert not resumed.statistics["unknown_operation"]
        with pytest.raises(ModelClientError, match="halted"):
            resumed.respond(json.dumps(payload()).encode())
    assert len(calls) == 1


def test_raw_only_recovery_seals_budget_stop_without_dispatch(factory, tmp_path):
    response = {
        **completed(8),
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(json.dumps(response).encode())

    with factory(opener) as gateway:
        gateway.respond(json.dumps(payload()).encode())
    directory = next((tmp_path / "journal").glob("*/response.json")).parent
    (directory / "response.json").unlink()  # Crash after raw receipt, before normalization seal.
    (directory / "state.json").write_text('{"status":"UNKNOWN"}')
    with factory(lambda *args, **kwargs: pytest.fail("recovery must not dispatch")) as resumed:
        assert resumed.statistics["halted"]
        assert resumed.statistics["failure_code"] == OUTPUT_TOKEN_BUDGET_STOP
        assert resumed.statistics["requests"] == 1 and resumed.statistics["output_tokens"] == 8
        assert not resumed.statistics["unknown_operation"]
        assert (directory / "response.json").is_file()
    assert len(calls) == 1


def test_incomplete_cannot_hide_reported_output_overrun(factory):
    response = {
        **completed(9),
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    with factory(lambda *args, **kwargs: Response(json.dumps(response).encode())) as gateway:
        with pytest.raises(ModelClientError, match="exceeded requested output limit"):
            gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["failure_code"] == "provider_output_token_limit_exceeded"
        assert gateway.statistics["terminal_stop"] is None
        assert gateway.statistics["output_tokens"] == 9


@pytest.mark.parametrize("body", [b"not-json", b'data: {"type":"response.created"}\n\n'])
def test_invalid_received_body_cannot_be_success_or_retry(factory, tmp_path, body):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(body)

    with factory(opener) as gateway:
        with pytest.raises(ModelClientError):
            gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["halted"] and not gateway.statistics["unknown_operation"]
        with pytest.raises(ModelClientError, match="halted"):
            gateway.respond(json.dumps(payload()).encode())
    assert len(calls) == 1 and next((tmp_path / "journal").glob("*/raw-response.json")).is_file()


def test_context_and_response_size_limits_do_not_trigger_retry(factory):
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return Response(b"a" * 100)

    with factory(opener, max_response_bytes=32) as gateway:
        with pytest.raises(UnknownOperation):
            gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["unknown_operation"]
    assert len(calls) == 1


def test_input_admission_happens_before_any_http_post(factory):
    calls = []
    with factory(lambda *args, **kwargs: calls.append(args)) as gateway:
        gateway.token_counter = lambda text: 1001
        with pytest.raises(InputTokenBudgetExceeded):
            gateway.respond(json.dumps(payload()).encode())
        assert gateway.statistics["requests"] == 0 and not calls
        assert not gateway.statistics["unknown_operation"]


def test_public_close_blocks_background_inference_without_auth_failure(factory):
    calls = []
    with factory(lambda *args, **kwargs: calls.append(args)) as gateway:
        gateway.close_public()
        assert request(gateway, payload())[0] == 403
        assert gateway.statistics["closed"] and not gateway.statistics["halted"]
        assert gateway.statistics["authentication_status"] is None
        assert not calls


def test_relay_waits_for_host_timeout_and_sealing_margin(factory, monkeypatch):
    waits = []
    connections = []

    class RelaySocket:
        def settimeout(self, timeout):
            waits.append(timeout)

        def connect(self, path):
            connections.append(path)

    with factory(lambda *args, **kwargs: pytest.fail("no provider POST expected")) as gateway:
        program = ast.parse(gateway.relay_path.read_text())
        program.body.pop()  # Exercise relay definitions without starting its TCP server.
        namespace = {}
        exec(compile(program, str(gateway.relay_path), "exec"), namespace)
        with monkeypatch.context() as patch:
            patch.setattr(socket, "socket", lambda *args: RelaySocket())
            patch.setattr(sys, "argv", ["relay.py", str(gateway.socket_path), "18765"])
            namespace["Connection"]("localhost").connect()
        assert waits == [gateway.timeout_seconds + 30]
        assert connections == [str(gateway.socket_path)]


def _full_resolution_image():
    import random

    from PIL import Image

    buffer = io.BytesIO()
    Image.frombytes("RGB", (512, 512), random.Random(17).randbytes(512 * 512 * 3)).save(
        buffer, format="PNG"
    )
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.mark.parametrize("messages", [False, True])
def test_image_admission_counts_visual_patches_and_preserves_provider_bytes(factory, messages):
    from tau_skill_evolution.codex_provider import _input_estimate

    encoded = _full_resolution_image()
    provider = MESSAGES_PROVIDER if messages else {**PROVIDER, "model": "openai.gpt-5.6-terra"}
    value = {
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Inspect the public task image."},
                    {"type": "input_image", "image_url": "data:image/png;base64," + encoded},
                ],
            }
        ],
        "stream": False,
    }
    payload_copy = json.loads(json.dumps(value))
    estimates = []
    posted = []

    def counter(text):
        assert encoded not in text
        estimates.append(text)
        return len(text)

    direct = (
        {
            "model": provider["model"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": encoded,
                            },
                        },
                    ],
                }
            ],
        }
        if messages
        else {"model": provider["model"], **value}
    )
    before = json.loads(json.dumps(direct))
    detail = _input_estimate(direct, counter)
    assert direct == before
    assert detail["image_count"] == 1
    assert detail["image_tokens"] == (434 if messages else 308)
    assert detail["total_tokens"] < 114688 < len(encoded)

    response = (
        {
            "id": "msg_visual",
            "type": "message",
            "role": "assistant",
            "model": provider["model"],
            "content": [{"type": "text", "text": "done"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 400, "output_tokens": 2},
        }
        if messages
        else completed()
    )

    def opener(req, timeout):
        posted.append(json.loads(req.data))
        return Response(json.dumps(response).encode())

    controls = {**UNBOUNDED_CONTROLS, "max_input_tokens": 114688}
    with factory(opener, provider=provider, controls=controls, token_counter=counter) as gateway:
        body, _ = gateway.respond(json.dumps(value).encode())
        assert body and gateway.statistics["requests"] == 1
        live = gateway.statistics["input_token_estimates"]
        assert live[0]["image_tokens"] == detail["image_tokens"]
    assert value == payload_copy
    assert len(posted) == 1
    if messages:
        assert posted[0]["messages"][0]["content"][1]["source"]["data"] == encoded
    else:
        assert posted[0]["input"][0]["content"][1]["image_url"].endswith(encoded)
    with factory(
        lambda *_args, **_kwargs: pytest.fail("completed request was re-sent"),
        provider=provider,
        controls=controls,
        token_counter=counter,
    ) as restored:
        restored_details = restored.statistics["input_token_estimates"]
        assert restored_details == live
        restored.respond(json.dumps(value).encode())
        assert restored.statistics["requests"] == 1


def test_image_url_admission_is_conservative_without_fetching():
    from tau_skill_evolution.codex_provider import _input_estimate

    v = {
        "model": "openai.gpt-5.6-terra",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "https://public.example/image.png"},
                    {"type": "input_text", "text": "Keep this ordinary base64 text: YWJj"},
                ],
            }
        ],
    }
    counted = []

    def counter(text):
        counted.append(text)
        return 50

    d = _input_estimate(v, counter)
    assert d == {"text_tokens": 50, "image_tokens": 36000, "image_count": 1, "total_tokens": 36050}
    assert "YWJj" in counted[0]


@pytest.mark.parametrize("encoded", ["not-base64", "aGVsbG8=", "truncated-png"])
def test_corrupt_inline_image_is_rejected_before_provider_dispatch(factory, encoded):
    if encoded == "truncated-png":
        encoded = base64.b64encode(base64.b64decode(_full_resolution_image())[:64]).decode()
    with factory(lambda *_args, **_kwargs: pytest.fail("invalid image was dispatched")) as gateway:
        with pytest.raises(ModelClientError, match="inline image dimensions"):
            gateway.respond(
                json.dumps(
                    {
                        "input": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_image",
                                        "image_url": "data:image/png;base64," + encoded,
                                    },
                                ],
                            }
                        ]
                    }
                ).encode()
            )
        assert gateway.statistics["requests"] == 0
        assert gateway.statistics["failure_code"] == "provider_invalid_image"
