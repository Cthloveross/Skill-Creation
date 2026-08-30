from __future__ import annotations

import json
import unittest
from collections.abc import Mapping

from r2sp.model_probe import run_model_service_probe


class FakeProbeClient:
    def __init__(self) -> None:
        self.agent_calls = 0
        self.compiler_max_output_tokens = None

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 8)

    def verify_tool_contract(self):
        return {"arguments_valid": True}

    def verify_selection_contract(self, *, selection_k):
        return {"arguments_valid": True, "selection_k": selection_k}

    def complete(self, messages, *, tools=None, seed=None, max_output_tokens=None):
        del seed
        if tools is None:
            if any(
                isinstance(message, Mapping)
                and "documents_actually_read" in str(message.get("content", ""))
                for message in messages
            ):
                self.compiler_max_output_tokens = max_output_tokens
                return {
                    "content": (
                        "---\nname: calendar-event-probe\n"
                        "description: Create a requested local calendar event.\n---\n\n"
                        "Use the trusted calendar interface for the requested event."
                    )
                }
            return {"content": "ok"}

        self.agent_calls += 1
        if self.agent_calls == 1:
            return self._tool("search_docs", {"query": "calendar event probe"})
        if self.agent_calls == 2:
            return self._tool("read_doc", {"resource_id": "probe-calendar-doc"})
        if self.agent_calls == 3:
            return self._tool(
                "execute",
                {
                    "app": "probe",
                    "api": "noop",
                    "args": {"label": "r2sp", "payload": {"value": 1}},
                },
            )
        return self._tool("finish", {"status": "success", "answer": "probe complete"})

    @staticmethod
    def _tool(name, arguments):
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": f"call-{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


class ModelProbeTests(unittest.TestCase):
    def test_probe_rejects_non_loopback_services(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            run_model_service_probe(base_url="http://models.example/v1")

    def test_probe_exercises_real_client_contract_but_stays_nonresearch(self) -> None:
        def fetcher(url, model_id, *, api_key=None):
            self.assertEqual(url, "http://127.0.0.1:8000/v1")
            self.assertEqual(api_key, "probe-key")
            return {"id": model_id}, "reachable"

        client = FakeProbeClient()
        report = run_model_service_probe(
            base_url="http://127.0.0.1:8000/v1",
            api_key="probe-key",
            client=client,
            record_fetcher=fetcher,
        )

        self.assertTrue(report.ready)
        payload = report.to_dict()
        self.assertFalse(payload["research_eligible"])
        self.assertEqual(payload["mode"], "model_service_instrumentation")
        self.assertEqual(
            [check["name"] for check in payload["checks"]],
            [
                "model_identity",
                "tokenizer",
                "ordinary_completion",
                "reasoning_and_tool_parser",
                "exact_five_selection_parser",
                "agent_four_tool_loop",
                "skill_compiler",
            ],
        )
        self.assertEqual(client.compiler_max_output_tokens, 4096)

    def test_probe_scales_compiler_budget_for_small_context_smoke(self) -> None:
        client = FakeProbeClient()
        report = run_model_service_probe(
            base_url="http://127.0.0.1:8000/v1",
            max_model_len=2048,
            client=client,
            record_fetcher=lambda *args, **kwargs: ({"id": args[1]}, "reachable"),
        )

        self.assertTrue(report.ready)
        self.assertEqual(client.compiler_max_output_tokens, 1024)

    def test_probe_reports_failures_without_upgrading_evidence(self) -> None:
        class BrokenClient:
            def complete(self, *args, **kwargs):
                del args, kwargs
                raise RuntimeError("broken")

        report = run_model_service_probe(
            base_url="http://127.0.0.1:8000/v1",
            client=BrokenClient(),
            record_fetcher=lambda *args, **kwargs: (None, "missing"),
        )
        self.assertFalse(report.ready)
        self.assertFalse(report.to_dict()["research_eligible"])


if __name__ == "__main__":
    unittest.main()
