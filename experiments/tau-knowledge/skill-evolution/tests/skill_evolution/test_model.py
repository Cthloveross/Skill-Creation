from __future__ import annotations

import copy
import io
import json

import pytest
from tau_skill_evolution import model as model_module
from tau_skill_evolution.generator import SKILL_BUNDLE_RESPONSE_FORMAT
from tau_skill_evolution.model import (
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
    SerializedChatTokenCounter,
)

ENDPOINT = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Time",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _response(output=None):
    return {
        "id": "resp_1",
        "status": "completed",
        "output": output
        if output is not None
        else [
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 2, "secret": "discard", "flag": True},
        },
    }


def test_usage_log_only_contains_provider_numbers_and_role(tmp_path):
    path = tmp_path / "usage.jsonl"
    client = OpenAICompatibleClient(
        ENDPOINT,
        api_key="private-key",
        usage_path=path,
        usage_role="generator",
        opener=lambda *args, **kwargs: io.BytesIO(json.dumps(_response()).encode()),
    )
    client.complete([{"role": "user", "content": "private task"}])
    record = json.loads(path.read_text())
    assert record["role"] == "generator"
    assert record["usage"]["input_tokens"] == 11
    assert "private" not in path.read_text() and "discard" not in path.read_text()


def _client(config=None, *, raw=None, counter=None):
    requests = []

    def opener(request, *, timeout):
        assert request.full_url == ENDPOINT + "/responses"
        assert request.get_header("Authorization") == "Bearer private-api-secret"
        requests.append(json.loads(request.data))
        if isinstance(raw, Exception):
            raise raw
        response = raw if raw is not None else _response()
        return io.BytesIO(
            response if isinstance(response, bytes) else json.dumps(response).encode()
        )

    return OpenAICompatibleClient(
        ENDPOINT, config=config, api_key="private-api-secret", opener=opener, token_counter=counter
    ), requests


@pytest.mark.parametrize("effort", ["none", "low", "medium", "high", "xhigh"])
def test_stateless_bedrock_wire_reasoning_and_sanitized_usage(effort):
    client, requests = _client(GenerationConfig(reasoning_effort=effort, max_output_tokens=32768))
    result = client.complete(
        [{"role": "system", "content": "policy"}, {"role": "user", "content": "first"}], seed=1
    )
    assert requests[0]["input"][0] == {"role": "developer", "content": "policy"}
    client.complete([{"role": "user", "content": "second"}], seed=2)
    payload = requests[-1]
    assert payload["input"] == [{"role": "user", "content": "second"}]
    assert payload["model"] == "openai.gpt-5.5"
    assert payload["reasoning"] == {"effort": effort}
    assert payload["max_output_tokens"] == 32768 and payload["store"] is False
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert "text" not in payload and "response_format" not in payload
    assert not (
        {
            "seed",
            "thinking",
            "temperature",
            "top_p",
            "top_k",
            "max_tokens",
            "max_completion_tokens",
            "chat_template_kwargs",
            "previous_response_id",
        }
        & payload.keys()
    )
    assert (
        result["content"] == "ok" and result["_bedrock_output_items"][0]["phase"] == "final_answer"
    )
    assert "private-api-secret" not in repr(client)
    assert client.last_usage == {
        "input_tokens": 11,
        "output_tokens": 7,
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "output_tokens_details": {"reasoning_tokens": 2},
    }
    copied = client.last_usage
    copied["output_tokens_details"]["reasoning_tokens"] = 999
    assert client.last_usage["output_tokens_details"]["reasoning_tokens"] == 2


def test_strict_skill_bundle_format_uses_responses_text_format_with_independent_copy(monkeypatch):
    response_format = copy.deepcopy(SKILL_BUNDLE_RESPONSE_FORMAT)
    client, requests = _client(GenerationConfig(response_format=response_format))
    original_dumps = json.dumps

    def serialize(value, **kwargs):
        encoded = original_dumps(value, **kwargs)
        if isinstance(value, dict) and "text" in value:
            outgoing = value["text"]["format"]
            assert outgoing is not response_format
            assert outgoing["schema"] is not response_format["schema"]
            outgoing["schema"]["properties"]["files"]["items"]["required"].clear()
        return encoded

    monkeypatch.setattr(model_module.json, "dumps", serialize)
    for _ in range(2):
        client.complete([{"role": "user", "content": "Generate the package"}])
    expected = {
        "type": "json_schema",
        "name": "skill_bundle",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["files"],
            "additionalProperties": False,
        },
    }
    assert response_format == SKILL_BUNDLE_RESPONSE_FORMAT == expected
    assert all(request["text"] == {"format": expected} for request in requests)
    assert all("response_format" not in request for request in requests)


def test_native_tool_calls_and_private_encrypted_reasoning_roundtrip():
    output = [
        {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "opaque"},
        {
            "id": "fc_1",
            "type": "function_call",
            "call_id": "call-original",
            "name": "get_time",
            "arguments": "{}",
        },
    ]
    client, requests = _client(raw=_response(output))
    first = {"role": "user", "content": "what time?"}
    result = client.complete([first], tools=[TOOL])
    assert result["finish_reason"] == "tool_calls" and result["content"] is None
    assert result["tool_calls"][0]["id"] == "call-original"
    assert requests[0]["reasoning"] == {"effort": "medium"}
    assert requests[0]["tools"] == [{"type": "function", **TOOL["function"], "strict": False}]
    client.complete(
        [first, result, {"role": "tool", "tool_call_id": "call-original", "content": "now"}],
        tools=[TOOL],
    )
    assert requests[-1]["input"] == [
        first,
        *output,
        {"type": "function_call_output", "call_id": "call-original", "output": "now"},
    ]
    result["_bedrock_output_items"][0]["encrypted_content"] = "changed"
    assert output[0]["encrypted_content"] == "opaque"


def test_serialized_tool_history_maps_original_call_ids():
    client, requests = _client()
    client.complete(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_time", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "now"},
        ]
    )
    assert requests[0]["input"] == [
        {"type": "function_call", "call_id": "call_1", "name": "get_time", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "now"},
    ]


def test_input_admission_before_send_and_no_invented_272k_cap():
    client, requests = _client(
        GenerationConfig(max_input_tokens=10), counter=SerializedChatTokenCounter(lambda text: 11)
    )
    with pytest.raises(ModelClientError) as error:
        client.complete([{"role": "user", "content": "over budget"}])
    assert error.value.code == "input_token_budget_exceeded" and requests == []
    client, requests = _client(
        GenerationConfig(max_input_tokens=400000),
        counter=SerializedChatTokenCounter(lambda text: 300000),
    )
    client.complete([{"role": "user", "content": "under configured budget"}])
    assert len(requests) == 1


def test_admission_uses_same_original_message_estimate_as_analyzer():
    messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "request"}]
    counter = SerializedChatTokenCounter(len)
    limit = counter.count(messages)
    client, requests = _client(GenerationConfig(max_input_tokens=limit), counter=counter)
    client.complete(messages)
    assert requests[0]["input"][0]["role"] == "developer"
    assert counter.basis == "serialized_text_estimate"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.deepseek.com",
        "https://api.openai.com/v1",
        "https://bedrock-runtime.us-east-1.amazonaws.com",
        "https://bedrock-mantle.us-west-2.api.aws/openai/v1",
        "https://bedrock-mantle.us-east-1.api.aws/v1",
    ],
)
def test_endpoint_rejects_silent_provider_or_region_fallback(endpoint):
    with pytest.raises(ValueError, match="Bedrock Mantle"):
        OpenAICompatibleClient(endpoint)


@pytest.mark.parametrize(
    "settings",
    [
        {"model": "openai.gpt-oss-120b"},
        {"transport": "deepseek"},
        {"reasoning_effort": "invalid"},
        {"max_output_tokens": True},
        {"response_format": "json_schema"},
    ],
)
def test_only_requested_bedrock_model_and_valid_settings(settings):
    with pytest.raises(ValueError):
        GenerationConfig(**settings)
    client = OpenAICompatibleClient("https://bedrock-mantle.us-east-2.api.aws/openai/v1/responses")
    assert client.endpoint.endswith("us-east-2.api.aws/openai/v1/responses")


@pytest.mark.parametrize(
    "raw,code",
    [
        (TimeoutError("private-api-secret unknown result"), "transport_error"),
        (b"not-json", "invalid_json"),
        # A server-reported "failed" status is a provider failure without a sample and is
        # retried (see test_model_retry.py); an unknown status stays invalid and unretried.
        ({"status": "weird"}, "invalid_response"),
        # An empty output list is a provider failure and is retried (test_model_retry.py);
        # a non-list output stays invalid and unretried.
        ({"status": "completed", "output": "not-a-list", "usage": {}}, "invalid_response"),
        (
            _response([{"type": "message", "role": "assistant", "content": ["bad"]}]),
            "invalid_response",
        ),
    ],
)
def test_unknown_or_invalid_response_is_never_retried(raw, code):
    client, requests = _client(raw=raw)
    with pytest.raises(ModelClientError) as error:
        client.complete([{"role": "user", "content": "hello"}])
    # Timeouts get two bounded re-sends (operator decision 2026-10-05, see README);
    # malformed/unknown responses are still never re-sent.
    expected_requests = 1 + client.timeout_retry_attempts if isinstance(raw, TimeoutError) else 1
    assert error.value.code == code and len(requests) == expected_requests
    assert "private-api-secret" not in str(error.value)
    assert client.usage_history == ()


def test_output_budget_stop_and_server_tools_rejected():
    raw = _response([])
    raw.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    client, requests = _client(raw=raw)
    assert client.complete([{"role": "user", "content": "hello"}])["finish_reason"] == "length"
    for tool in [{"type": "web_search"}, None]:
        with pytest.raises(ValueError, match="host-controlled"):
            client.complete([{"role": "user", "content": "hello"}], tools=[tool])
    assert len(requests) == 1
