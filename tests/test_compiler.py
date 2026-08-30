import hashlib
import json
import unittest

from r2sp.compiler import NEUTRAL_PLACEHOLDER, SkillCompiler, validate_skill_text
from r2sp.model_client import ModelClientError


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class CompilerTests(unittest.TestCase):
    def test_only_normalized_model_failures_become_placeholders(self):
        class FailingClient:
            def __init__(self, exception):
                self.exception = exception

            def complete(self, messages, **kwargs):
                del messages, kwargs
                raise self.exception

        artifact = SkillCompiler(FailingClient(ModelClientError("timeout", "timed out"))).compile(
            "task", [], [], False
        )
        self.assertTrue(artifact.placeholder)
        self.assertEqual(artifact.failure, "model_timeout")

        with self.assertRaisesRegex(RuntimeError, "programmer fault"):
            SkillCompiler(FailingClient(RuntimeError("programmer fault"))).compile(
                "task", [], [], False
            )

    def test_payload_is_strictly_allow_listed(self):
        client = FakeClient(
            {
                "content": (
                    "---\nname: add-note\n"
                    "description: Add notes when a task requires the notes API.\n"
                    "---\nUse notes.add.\n"
                )
            }
        )
        compiler = SkillCompiler(client)
        artifact = compiler.compile(
            "Add a note",
            [
                {
                    "resource_id": "doc-1",
                    "app_name": "notes",
                    "api_name": "add",
                    "title": "Add",
                    "body": "API instructions",
                    "content_hash": "abc",
                    "unread_documents": ["secret"],
                    "evaluator": "secret",
                }
            ],
            [
                {
                    "app": "notes",
                    "api": "add",
                    "args": {"text": "x"},
                    "ok": True,
                    "result": {"saved": True},
                    "reasoning": "secret",
                    "evaluator": "secret",
                }
            ],
            True,
            seed=4,
        )
        payload = json.loads(client.calls[0][0][1]["content"])

        self.assertEqual(
            set(payload),
            {"task", "documents_actually_read", "normalized_api_trace", "task_success"},
        )
        serialized = json.dumps(payload)
        self.assertNotIn("reasoning", serialized)
        self.assertNotIn("evaluator", serialized)
        self.assertNotIn("unread_documents", serialized)
        self.assertTrue(artifact.valid)
        self.assertEqual(artifact.source_resource_ids, ("doc-1",))
        self.assertEqual(client.calls[0][1]["max_output_tokens"], 4096)
        self.assertEqual(client.calls[0][1]["seed"], 4)
        self.assertEqual(artifact.skill_hash, hashlib.sha256(artifact.content.encode()).hexdigest())

    def test_tool_call_or_empty_output_becomes_neutral_placeholder(self):
        client = FakeClient({"content": None, "tool_calls": [{"function": {"name": "execute"}}]})
        artifact = SkillCompiler(client).compile("task", [], [], False)
        self.assertFalse(artifact.valid)
        self.assertTrue(artifact.placeholder)
        self.assertEqual(artifact.content, NEUTRAL_PLACEHOLDER)
        self.assertEqual(artifact.failure, "compiler_returned_tool_calls")

    def test_overflow_keeps_equal_document_prefixes_and_latest_trace(self):
        compiler = SkillCompiler(FakeClient({"content": "skill"}), max_input_tokens=100)
        payload = compiler.build_payload(
            "task",
            [
                {"resource_id": "a", "body": "a" * 500},
                {"resource_id": "b", "body": "b" * 500},
            ],
            [{"call_index": index, "app": "x", "api": "y", "ok": True} for index in range(20)],
            True,
        )
        lengths = [len(doc["body"]) for doc in payload["documents_actually_read"]]
        self.assertEqual(lengths[0], lengths[1])
        self.assertEqual(payload["normalized_api_trace"][-1]["call_index"], 19)

    def test_pinned_token_counter_enforces_exact_payload_limit(self):
        compiler = SkillCompiler(
            FakeClient({"content": "skill"}),
            max_input_tokens=320,
            chars_per_token=20,
            token_counter=lambda text: len(text.encode("utf-8")),
        )
        payload = compiler.build_payload(
            "任务" * 200,
            [
                {"resource_id": "a", "body": "文" * 500},
                {"resource_id": "b", "body": "字" * 500},
            ],
            [{"call_index": index, "app": "x", "api": "y"} for index in range(12)],
            True,
        )
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        self.assertLessEqual(len(encoded), 320)
        self.assertEqual(
            len(payload["documents_actually_read"][0]["body"]),
            len(payload["documents_actually_read"][1]["body"]),
        )
        if payload["normalized_api_trace"]:
            self.assertEqual(payload["normalized_api_trace"][-1]["call_index"], 11)

    def test_invalid_skill_structure_fails_closed(self):
        invalid = (
            "plain text",
            "---\nname: Bad_Name\ndescription: invalid name\n---\nbody\n",
            "---\nname: valid-name\n---\nbody\n",
            "---\nname: valid-name\ndescription: valid\n---\n",
        )
        for content in invalid:
            with self.subTest(content=content):
                artifact = SkillCompiler(FakeClient({"content": content})).compile(
                    "task", [], [], False
                )
                self.assertFalse(artifact.valid)
                self.assertTrue(artifact.placeholder)
                self.assertTrue(artifact.failure.startswith("invalid_skill_"))

        self.assertIsNone(
            validate_skill_text(
                "---\nname: valid-name\ndescription: Precise routing text.\n---\nBody.\n"
            )
        )

    def test_explicit_frozen_system_prompt_is_used_verbatim(self):
        client = FakeClient(
            {"content": ("---\nname: stable-skill\ndescription: Stable.\n---\nBody.\n")}
        )
        SkillCompiler(client, system_prompt="frozen compiler prompt").compile("task", [], [], True)
        self.assertEqual(client.calls[0][0][0]["content"], "frozen compiler prompt")


if __name__ == "__main__":
    unittest.main()
