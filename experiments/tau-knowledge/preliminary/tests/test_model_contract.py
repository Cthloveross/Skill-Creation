from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from r2sp_tau_knowledge.constants import MODEL_ID, MODEL_REVISION
from r2sp_tau_knowledge.live import _vllm_environment, _worker_environment
from r2sp_tau_knowledge.model import (
    GenerationConfig,
    ModelClientError,
    OpenAICompatibleClient,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class RecordingOpener:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[Any, float]] = []

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        return FakeResponse(self.responses.pop(0))


def test_generation_config_pins_model_revision_and_user_simulator_safe_defaults() -> None:
    config = GenerationConfig()
    assert config.model == MODEL_ID == "Qwen/Qwen3.8-27B-FP8"
    assert config.revision == MODEL_REVISION
    assert config.enable_thinking is False


def test_openai_client_sends_only_current_context_and_fixed_generation_fields() -> None:
    opener = RecordingOpener(
        [
            {"choices": [{"message": {"role": "assistant", "content": "first"}}]},
            {"choices": [{"message": {"role": "assistant", "content": "second"}}]},
        ]
    )
    client = OpenAICompatibleClient(opener=opener, timeout_seconds=7)
    first_message = [{"role": "user", "content": "one"}]
    second_message = [{"role": "user", "content": "two"}]
    tools = [{"type": "function", "function": {"name": "search_web"}}]

    assert (
        client.complete(first_message, tools=tools, seed=41, max_output_tokens=123)["content"]
        == "first"
    )
    assert client.complete(second_message, seed=42)["content"] == "second"

    first_payload = json.loads(opener.requests[0][0].data)
    second_payload = json.loads(opener.requests[1][0].data)
    assert opener.requests[0][0].full_url == "http://127.0.0.1:18138/v1/chat/completions"
    assert opener.requests[0][1] == 7
    assert first_payload["messages"] == first_message
    assert second_payload["messages"] == second_message
    assert first_payload["model"] == MODEL_ID
    assert first_payload["seed"] == 41
    assert first_payload["max_tokens"] == 123
    assert first_payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert first_payload["tools"] == tools
    assert first_payload["tool_choice"] == "auto"
    assert "one" not in json.dumps(second_payload)
    assert "tools" not in second_payload
    assert "tool_choice" not in second_payload


def test_invalid_service_shape_has_stable_infrastructure_error() -> None:
    opener = RecordingOpener([{"choices": []}])
    client = OpenAICompatibleClient(opener=opener)
    with pytest.raises(ModelClientError) as caught:
        client.complete([{"role": "user", "content": "question"}])
    assert caught.value.code == "invalid_response"


@pytest.mark.parametrize(
    "name",
    [
        "AWS_SECRET_ACCESS_KEY",
        "HOME",
        "HTTP_PROXY",
        "LD_PRELOAD",
        "OPENAI_API_KEY",
        "PYTHONSTARTUP",
        "R2SP_PARENT_SECRET_CANARY",
    ],
)
def test_worker_environment_does_not_inherit_parent_secrets_or_hooks(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    monkeypatch.setenv(name, "must-not-cross-process-boundary")

    environment = _worker_environment()

    assert name not in environment
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONPATH"].endswith("/src")
    assert environment["NO_PROXY"] == "127.0.0.1,localhost"


def test_vllm_environment_is_explicit_and_uses_controlled_cache(tmp_path: Path) -> None:
    environment = _vllm_environment((2, 4), tmp_path)

    assert environment["CUDA_VISIBLE_DEVICES"] == "2,4"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["HF_HOME"] == str(tmp_path / "huggingface")
    assert environment["TRITON_CACHE_DIR"] == str(tmp_path / "triton")
    assert environment["XDG_CACHE_HOME"] == str(tmp_path / "xdg")
    for forbidden in ("HOME", "OPENAI_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "LD_PRELOAD"):
        assert forbidden not in environment
