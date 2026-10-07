from __future__ import annotations

import copy
import io
import json

import pytest
from tau_skill_evolution import model as model_module
from tau_skill_evolution.generator import SKILL_BUNDLE_RESPONSE_FORMAT
from tau_skill_evolution.model import (
    GenerationConfig,
    InputTokenBudgetExceeded,
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


def test_null_output_limit_is_omitted_from_live_and_journaled_requests(tmp_path):
    from tau_skill_evolution.journal import Journal

    client, requests = _client(GenerationConfig(max_output_tokens=None))
    messages = [{"role": "user", "content": "write a complete package"}]
    assert client.complete(messages)["content"] == "ok"
    journal = Journal(tmp_path)
    client.complete_journaled(journal, "generate_initial", {}, messages)
    assert len(requests) == 2
    assert all("max_output_tokens" not in request for request in requests)
    assert client.last_usage["output_tokens"] == 7
    client.complete(messages, max_output_tokens=20)
    assert requests[-1]["max_output_tokens"] == 20
    assert journal.completed("generate_initial")


MESSAGES_ENDPOINT = "https://bedrock-mantle.us-east-1.api.aws/anthropic/v1"
OPUS = "anthropic.claude-opus-4-8"


def _anthropic_response(content=None, *, stop="end_turn"):
    return {
        "id": "msg_fixture",
        "type": "message",
        "role": "assistant",
        "model": OPUS,
        "content": content if content is not None else [{"type": "text", "text": "ok"}],
        "stop_reason": stop,
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }


@pytest.mark.parametrize("effort", [None, "none", "low", "medium", "high"])
def test_messages_client_uses_documented_route_effort_and_model_maximum(effort):
    requests = []

    def opener(request, *, timeout):
        assert request.full_url == MESSAGES_ENDPOINT + "/messages"
        assert request.get_header("Authorization") == "Bearer private-fixture"
        assert request.get_header("Anthropic-version") == "2023-06-01"
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps(_anthropic_response()).encode())

    client = OpenAICompatibleClient(
        MESSAGES_ENDPOINT,
        api_key="private-fixture",
        opener=opener,
        config=GenerationConfig(
            model=OPUS,
            transport="bedrock-messages",
            reasoning_effort=effort,
            max_output_tokens=None,
            response_format=SKILL_BUNDLE_RESPONSE_FORMAT,
        ),
    )
    result = client.complete(
        [
            {"role": "system", "content": "public policy"},
            {"role": "user", "content": "generate a package"},
        ]
    )
    assert result["content"] == "ok" and result["usage"]["total_tokens"] == 18
    payload = requests[0]
    assert payload["model"] == OPUS and payload["max_tokens"] == 128000
    assert payload["stream"] is False
    assert payload["thinking"] == {"type": "disabled" if effort == "none" else "adaptive"}
    assert payload.get("output_config") == (
        {"effort": effort} if effort not in {None, "none"} else None
    )
    assert "public policy" in payload["system"] and '"files"' in payload["system"]
    assert "format" not in payload.get("output_config", {})
    assert not {"input", "store", "include", "reasoning", "text"} & payload.keys()


@pytest.mark.parametrize(
    "endpoint",
    [
        ENDPOINT,
        MESSAGES_ENDPOINT.replace("us-east-1", "us-east-2"),
        "https://untrusted.example/anthropic/v1",
    ],
)
def test_messages_endpoint_cannot_switch_transport_or_region(endpoint):
    with pytest.raises(ValueError):
        OpenAICompatibleClient(
            endpoint, config=GenerationConfig(model=OPUS, transport="bedrock-messages")
        )


@pytest.mark.parametrize(
    "config",
    [
        {"model": OPUS},
        {"model": "openai.gpt-5.6-terra", "transport": "bedrock-messages"},
        {"model": OPUS, "transport": "bedrock-messages", "reasoning_effort": "xhigh"},
        {"model": OPUS, "transport": "bedrock-messages", "max_output_tokens": 128001},
    ],
)
def test_messages_model_transport_and_output_range_are_strict(config):
    with pytest.raises(ValueError):
        GenerationConfig(**config)


def test_messages_tools_and_signed_reasoning_round_trip_without_exposing_thinking():
    from tau_skill_evolution.model import anthropic_to_responses, responses_to_anthropic

    tools = [
        {
            "type": "namespace",
            "name": "functions",
            "tools": [
                {
                    "type": "function",
                    "name": "terminal",
                    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
                },
            ],
        },
        {
            "type": "custom",
            "name": "apply_patch",
            "format": {"type": "grammar", "syntax": "lark", "definition": "start: /.+/"},
        },
    ]
    payload = {
        "input": [
            {"role": "developer", "content": "policy"},
            {"role": "user", "content": [{"type": "input_text", "text": "task"}]},
        ],
        "tools": tools,
    }
    converted = responses_to_anthropic(payload, model=OPUS, reasoning_effort="high")
    aliases = [tool["name"] for tool in converted["tools"]]
    assert len(set(aliases)) == 2 and all(len(alias) <= 64 for alias in aliases)
    thinking = {
        "type": "thinking",
        "thinking": "private opaque reasoning",
        "signature": "signed-exact",
    }
    redacted = {"type": "redacted_thinking", "data": "opaque-ciphertext"}
    raw = _anthropic_response(
        [
            thinking,
            redacted,
            {
                "type": "tool_use",
                "id": "call_terminal",
                "name": aliases[0],
                "input": {"command": "pwd"},
            },
            {
                "type": "tool_use",
                "id": "call_patch",
                "name": aliases[1],
                "input": {"input": "literal patch"},
            },
        ],
        stop="tool_use",
    )
    canonical = anthropic_to_responses(raw, tools=tools)
    assert canonical["status"] == "completed"
    assert canonical["output"][0]["summary"] == []
    assert "private opaque reasoning" not in json.dumps(canonical)
    assert canonical["output"][2]["namespace"] == "functions"
    assert canonical["output"][2]["name"] == "terminal"
    assert canonical["output"][3]["type"] == "custom_tool_call"
    assert canonical["output"][3]["input"] == "literal patch"
    followup = {
        **payload,
        "input": payload["input"]
        + canonical["output"]
        + [
            {"type": "function_call_output", "call_id": "call_terminal", "output": "public cwd"},
            {"type": "custom_tool_call_output", "call_id": "call_patch", "output": "applied"},
        ],
    }
    resumed = responses_to_anthropic(followup, model=OPUS, reasoning_effort="high")
    assert resumed["messages"][1]["content"][:2] == [thinking, redacted]
    assert resumed["messages"][1]["content"][2]["name"] == aliases[0]
    assert resumed["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_terminal", "content": "public cwd"},
        {"type": "tool_result", "tool_use_id": "call_patch", "content": "applied"},
    ]


def test_messages_chat_continuation_uses_exact_signed_block_and_original_call():
    requests = []
    thinking = {"type": "thinking", "thinking": "opaque", "signature": "untouched"}

    def opener(request, *, timeout):
        payload = json.loads(request.data)
        requests.append(payload)
        content = [
            thinking,
            {
                "type": "tool_use",
                "id": "time_call",
                "name": payload["tools"][0]["name"],
                "input": {},
            },
        ]
        response = (
            _anthropic_response(content, stop="tool_use")
            if len(requests) == 1
            else _anthropic_response()
        )
        return io.BytesIO(json.dumps(response).encode())

    client = OpenAICompatibleClient(
        MESSAGES_ENDPOINT,
        config=GenerationConfig(model=OPUS, transport="bedrock-messages"),
        opener=opener,
    )
    first = [{"role": "user", "content": "what time?"}]
    response = client.complete(first, tools=[TOOL])
    assert response["tool_calls"][0]["function"]["name"] == "get_time"
    client.complete(
        [*first, response, {"role": "tool", "tool_call_id": "time_call", "content": "2026"}],
        tools=[TOOL],
    )
    assert requests[1]["messages"][1]["content"][0] == thinking


@pytest.mark.parametrize(
    "stop",
    [None, "", "pause_turn", "stop_sequence", "model_context_window_exceeded", "future_status"],
)
def test_messages_unknown_stop_is_not_normalized_as_success(stop):
    from tau_skill_evolution.model import anthropic_to_responses

    with pytest.raises(ModelClientError, match="termination"):
        anthropic_to_responses(_anthropic_response(stop=stop))


def test_messages_max_tokens_is_known_incomplete_and_refusal_is_failure():
    from tau_skill_evolution.model import _assistant_response, anthropic_to_responses

    converted = anthropic_to_responses(_anthropic_response([], stop="max_tokens"))
    assert (
        converted["status"] == "incomplete"
        and _assistant_response(converted)["finish_reason"] == "length"
    )
    with pytest.raises(ModelClientError) as failure:
        anthropic_to_responses(_anthropic_response([], stop="refusal"))
    assert failure.value.code == "model_refusal"


@pytest.mark.parametrize(
    "payload",
    [
        {"tools": [{"type": "web_search"}]},
        {"input": [{"type": "reasoning", "encrypted_content": "foreign-reasoning"}]},
        {"previous_response_id": "old_response"},
        {
            "input": [
                {"role": "user", "content": [{"type": "input_image", "image_url": "untrusted"}]}
            ]
        },
    ],
)
def test_messages_bridge_refuses_unsupported_capabilities_before_post(payload):
    from tau_skill_evolution.model import responses_to_anthropic

    with pytest.raises(ValueError):
        responses_to_anthropic(
            {"input": [{"role": "user", "content": "task"}], **payload},
            model=OPUS,
            reasoning_effort="medium",
        )


def test_messages_raw_response_is_sealed_before_normalization_and_never_reposted(tmp_path):
    import base64

    from tau_skill_evolution.journal import Journal, UnknownOperation

    requests = []
    raw = json.dumps(_anthropic_response(stop="pause_turn")).encode()

    def opener(request, *, timeout):
        requests.append(request)
        return io.BytesIO(raw)

    client = OpenAICompatibleClient(
        MESSAGES_ENDPOINT,
        config=GenerationConfig(model=OPUS, transport="bedrock-messages", max_output_tokens=None),
        opener=opener,
    )
    journal = Journal(tmp_path / "journal")
    messages = [{"role": "user", "content": "generate once"}]
    for _ in range(2):
        with pytest.raises(ModelClientError):
            client.complete_journaled(journal, "s0", {}, messages)
    assert len(requests) == 1
    sealed = next(journal.root.glob("*/raw-response.json"))
    assert base64.b64decode(json.loads(sealed.read_text())["body_base64"]) == raw
    assert sealed.stat().st_mode & 0o777 == 0o600
    unknown = OpenAICompatibleClient(
        MESSAGES_ENDPOINT,
        config=client.config,
        opener=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("unknown")),
    )
    for _ in range(2):
        with pytest.raises(UnknownOperation):
            unknown.complete_journaled(journal, "unknown-s0", {}, messages)
    assert journal.status("unknown-s0") == "UNKNOWN"


def test_messages_cached_usage_counts_all_input_without_fabricated_reasoning_count():
    from tau_skill_evolution.model import anthropic_to_responses

    raw = _anthropic_response()
    raw["usage"].update(cache_read_input_tokens=20, cache_creation_input_tokens=30)
    usage = anthropic_to_responses(raw)["usage"]
    assert usage["input_tokens"] == 61 and usage["total_tokens"] == 68
    assert usage["input_tokens_details"] == {"cached_tokens": 20}
    assert "output_tokens_details" not in usage


@pytest.mark.parametrize(
    "content,stop",
    [
        ([], "end_turn"),
        ([{"type": "text", "text": ""}], "end_turn"),
        ([{"type": "thinking", "thinking": "private", "signature": "signed"}], "end_turn"),
        ([{"type": "thinking", "thinking": "unsigned"}], "max_tokens"),
        ([{"type": "server_tool_use", "name": "web_search"}], "tool_use"),
        ([{"type": []}], "end_turn"),
        ([{"type": "text", "text": "ok"}], []),
    ],
)
def test_messages_malformed_or_empty_completion_is_explicit_failure(content, stop):
    from tau_skill_evolution.model import anthropic_to_responses

    with pytest.raises(ModelClientError):
        anthropic_to_responses(_anthropic_response(content, stop=stop))


def test_messages_duplicate_tool_ids_and_colliding_declarations_are_rejected():
    from tau_skill_evolution.model import anthropic_to_responses, responses_to_anthropic

    function = model_module._response_tools([TOOL])[0]
    payload = {"input": [{"role": "user", "content": "time"}], "tools": [function]}
    wire = responses_to_anthropic(payload, model=OPUS, reasoning_effort="medium")
    call = {"type": "tool_use", "id": "duplicate", "name": wire["tools"][0]["name"], "input": {}}
    with pytest.raises(ModelClientError, match="malformed"):
        anthropic_to_responses(_anthropic_response([call, call], stop="tool_use"), tools=[function])
    with pytest.raises(ValueError, match="duplicate"):
        responses_to_anthropic(
            {**payload, "tools": [function, function]}, model=OPUS, reasoning_effort="medium"
        )


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


def test_messages_user_and_tool_images_preserve_bytes_urls_and_block_order():
    from tau_skill_evolution.model import responses_to_anthropic

    image = {"type": "input_image", "image_url": "data:image/png;base64,aW1hZ2U="}
    remote = {"type": "input_image", "image_url": "https://images.example/public.png"}
    content = [{"type": "input_text", "text": "inspect"}, image, remote]
    output = responses_to_anthropic(
        {
            "input": [
                {"role": "user", "content": content},
                {"type": "function_call_output", "call_id": "image_tool", "output": content},
            ]
        },
        model=OPUS,
        reasoning_effort="medium",
    )
    expected = [
        {"type": "text", "text": "inspect"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "aW1hZ2U="},
        },
        {"type": "image", "source": {"type": "url", "url": remote["image_url"]}},
    ]
    assert output["messages"][0]["content"][:3] == expected
    assert output["messages"][0]["content"][3] == {
        "type": "tool_result",
        "tool_use_id": "image_tool",
        "content": expected,
    }


@pytest.mark.parametrize("role", ["system", "developer", "assistant"])
def test_messages_images_are_not_silently_promoted_from_private_or_assistant_roles(role):
    from tau_skill_evolution.model import responses_to_anthropic

    with pytest.raises(ValueError, match="requires text"):
        responses_to_anthropic(
            {
                "input": [
                    {"role": "user", "content": "task"},
                    {
                        "role": role,
                        "content": [
                            {"type": "input_image", "image_url": "data:image/png;base64,aW1hZ2U="}
                        ],
                    },
                ]
            },
            model=OPUS,
            reasoning_effort="medium",
        )


@pytest.mark.parametrize(
    "image",
    [
        {"type": "input_image", "file_id": "file_private"},
        {"type": "input_image", "image_url": "file:///private/image.png"},
        {"type": "input_image", "image_url": "data:application/pdf;base64,cGRm"},
        {"type": "input_image", "image_url": "data:image/png;base64,invalid%%"},
        {"type": "input_file", "file_data": "data:application/pdf;base64,cGRm"},
    ],
)
def test_messages_images_reject_unavailable_files_or_invalid_encodings(image):
    from tau_skill_evolution.model import responses_to_anthropic

    with pytest.raises(ValueError):
        responses_to_anthropic(
            {"input": [{"role": "user", "content": [image]}]}, model=OPUS, reasoning_effort="medium"
        )


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
    assert counter.basis == "responses_input_estimate_with_reasoning_reserve"


def test_admission_counts_native_content_once_and_reserves_measured_reasoning():
    rendered = []
    counter = SerializedChatTokenCounter(lambda text: rendered.append(text) or len(text))
    assistant = {
        "role": "assistant",
        "content": "unique answer",
        "response_id": "client metadata",
        "usage": {"output_tokens": 12, "output_tokens_details": {"reasoning_tokens": 7}},
        "_bedrock_output_items": [
            {"type": "reasoning", "summary": [], "encrypted_content": "encoded" * 10000},
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "unique answer"},
                ],
            },
        ],
    }
    original = copy.deepcopy(assistant)
    estimate = counter.count([assistant], tools=[TOOL])
    assert rendered[-1].count("unique answer") == 1
    assert "client metadata" not in rendered[-1] and "encoded" not in rendered[-1]
    assert estimate == len(rendered[-1]) + 7
    assert counter.count_breakdown([assistant], tools=[TOOL]) == {
        "total_tokens": estimate,
        "visible_tokens": len(rendered[-1]),
        "reasoning_reserve": 7,
        "basis": counter.basis,
    }
    assert assistant == original
    assistant["content"] = "duplicate normalized text" * 10000
    assistant["_bedrock_output_items"][0]["encrypted_content"] = "different ciphertext"
    assistant["usage"]["input_tokens"] = 1000000
    assert counter.count([assistant], tools=[TOOL]) == estimate
    # Estimation must leave the actual continuation bytes untouched on the wire.
    client, requests = _client(GenerationConfig(max_input_tokens=estimate), counter=counter)
    client.complete([assistant], tools=[TOOL])
    assert requests[0]["input"][0]["encrypted_content"] == "different ciphertext"


def test_opaque_reasoning_without_usage_is_not_charged_zero():
    counter = SerializedChatTokenCounter(len)
    assistant = {
        "role": "assistant",
        "_bedrock_output_items": [
            {"type": "reasoning", "summary": [], "encrypted_content": "opaque"},
        ],
    }
    short = counter.count([assistant])
    assert counter.count_breakdown([assistant])["reasoning_reserve"] == 0
    assistant["_bedrock_output_items"][0]["encrypted_content"] *= 100
    assert counter.count([assistant]) > short
    assistant["usage"] = {"output_tokens": 25}
    reserved = counter.count([assistant])
    assert counter.count_breakdown([assistant])["reasoning_reserve"] == 25
    assistant["_bedrock_output_items"][0]["encrypted_content"] *= 100
    assert counter.count([assistant]) == reserved


def test_unsent_admission_records_estimate_and_limit_without_post(tmp_path):
    from tau_skill_evolution.journal import Journal

    journal = Journal(tmp_path / "journal")
    client, requests = _client(
        GenerationConfig(max_input_tokens=10), counter=SerializedChatTokenCounter(lambda _: 11)
    )
    with pytest.raises(InputTokenBudgetExceeded) as error:
        client.complete_journaled(journal, "s0", {}, [{"role": "user", "content": "large"}])
    assert requests == [] and journal.status("s0") == "NOT_SENT"
    assert error.value.details == {"observed_input_tokens": 11, "max_input_tokens": 10}
    failure = json.loads((journal._directory("s0") / "failure.json").read_text())
    assert failure["context_admission"] == error.value.details


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
    "raw,code,posts",
    [
        # A client timeout is re-sent at most twice (bounded operator policy), then unknown.
        (TimeoutError("private-api-secret unknown result"), "transport_error", 3),
        (b"not-json", "invalid_json", 1),
        ({"status": "weird"}, "invalid_response", 1),
        ({"status": "completed", "output": "not-a-list", "usage": {}}, "invalid_response", 1),
        (
            _response([{"type": "message", "role": "assistant", "content": ["bad"]}]),
            "invalid_response",
            1,
        ),
    ],
)
def test_invalid_received_response_is_never_retried(raw, code, posts):
    client, requests = _client(raw=raw)
    with pytest.raises(ModelClientError) as error:
        client.complete([{"role": "user", "content": "hello"}])
    assert error.value.code == code and len(requests) == posts
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
