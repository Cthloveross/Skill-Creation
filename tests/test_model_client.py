import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from r2sp.model_client import (
    ModelClientError,
    OpenAICompatibleClient,
    QwenGenerationConfig,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


class ModelClientTests(unittest.TestCase):
    def test_protocol_defaults_are_frozen_in_request(self):
        seen = {}

        def opener(request, timeout):
            seen["request"] = request
            seen["timeout"] = timeout
            return _Response({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        client = OpenAICompatibleClient("http://model:8000/v1", api_key="secret", opener=opener)
        message = client.complete([{"role": "user", "content": "task"}], seed=7)
        payload = json.loads(seen["request"].data)

        self.assertEqual(message["content"], "ok")
        self.assertEqual(seen["request"].full_url, "http://model:8000/v1/chat/completions")
        self.assertEqual(payload["model"], "Qwen/Qwen3.8-27B")
        self.assertEqual(payload["temperature"], 1.0)
        self.assertEqual(payload["top_p"], 0.95)
        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["reasoning_effort"], "xhigh")
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(payload["seed"], 7)
        self.assertTrue(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertFalse(payload["chat_template_kwargs"]["preserve_thinking"])
        self.assertEqual(seen["request"].headers["Authorization"], "Bearer secret")

    def test_tools_enable_auto_tool_choice(self):
        client = OpenAICompatibleClient(opener=lambda *_args, **_kwargs: None)
        payload = client.build_payload(
            [{"role": "user", "content": "x"}],
            tools=[{"type": "function", "function": {"name": "finish"}}],
        )
        self.assertEqual(payload["tool_choice"], "auto")

    def test_client_never_borrows_unrelated_openai_api_key(self):
        seen = {}

        def opener(request, timeout):
            del timeout
            seen["headers"] = dict(request.headers)
            return _Response({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        with patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-leak"}):
            client = OpenAICompatibleClient("http://127.0.0.1:8000/v1", opener=opener)
            client.complete([{"role": "user", "content": "task"}])

        self.assertNotIn("Authorization", seen["headers"])

    def test_token_count_uses_vllm_tokenize_endpoint(self):
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["payload"] = json.loads(request.data)
            return _Response({"count": 3, "tokens": [1, 2, 3]})

        client = OpenAICompatibleClient("http://127.0.0.1:8000/v1", opener=opener)

        self.assertEqual(client.count_tokens("hello"), 3)
        self.assertEqual(seen["url"], "http://127.0.0.1:8000/tokenize")
        self.assertEqual(seen["payload"]["prompt"], "hello")
        self.assertFalse(seen["payload"]["add_special_tokens"])

    def test_tool_contract_probe_requires_structured_finish_call(self):
        def opener(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload["tool_choice"]["function"]["name"], "finish")
            return _Response(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_content": "internal",
                                "tool_calls": [
                                    {
                                        "id": "probe",
                                        "type": "function",
                                        "function": {
                                            "name": "finish",
                                            "arguments": '{"status":"probe-ok"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )

        client = OpenAICompatibleClient(opener=opener)
        self.assertTrue(client.verify_tool_contract()["arguments_valid"])

    def test_selection_contract_probe_requires_exact_unique_resource_ids(self):
        selected = [f"candidate-{index}" for index in range(5)]

        def opener(request, timeout):
            del timeout
            payload = json.loads(request.data)
            function = payload["tools"][0]["function"]
            self.assertEqual(payload["tool_choice"]["function"]["name"], "select_docs")
            self.assertEqual(function["parameters"]["properties"]["resource_ids"]["minItems"], 5)
            self.assertEqual(function["parameters"]["properties"]["resource_ids"]["maxItems"], 5)
            self.assertTrue(function["parameters"]["properties"]["resource_ids"]["uniqueItems"])
            return _Response(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "selection-probe",
                                        "type": "function",
                                        "function": {
                                            "name": "select_docs",
                                            "arguments": json.dumps({"resource_ids": selected}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )

        client = OpenAICompatibleClient(opener=opener)
        evidence = client.verify_selection_contract(selection_k=5)

        self.assertEqual(evidence["selection_k"], 5)
        self.assertEqual(evidence["resource_ids"], selected)

    def test_selection_contract_probe_rejects_duplicate_or_wrong_count(self):
        variants = (["a", "b"], ["a", "a", "b", "c", "d"])
        for selected in variants:
            with self.subTest(selected=selected):
                response = _Response(
                    {
                        "choices": [
                            {
                                "message": {
                                    "tool_calls": [
                                        {
                                            "function": {
                                                "name": "select_docs",
                                                "arguments": json.dumps({"resource_ids": selected}),
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                )
                client = OpenAICompatibleClient(
                    opener=lambda *_args, response=response, **_kwargs: response
                )
                with self.assertRaises(ModelClientError) as caught:
                    client.verify_selection_contract(selection_k=5)
                self.assertEqual(caught.exception.code, "selection_contract_probe_failed")

    def test_http_error_is_normalized(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "failure",
                {},
                io.BytesIO(b'{"error":{"message":"worker unavailable"}}'),
            )

        client = OpenAICompatibleClient(opener=opener)
        with self.assertRaises(ModelClientError) as caught:
            client.complete([{"role": "user", "content": "x"}])
        self.assertEqual(caught.exception.code, "http_error")
        self.assertEqual(caught.exception.status, 503)

    def test_revision_constant_matches_protocol(self):
        self.assertEqual(
            QwenGenerationConfig().revision,
            "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
        )


if __name__ == "__main__":
    unittest.main()
