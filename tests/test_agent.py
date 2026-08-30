import json
import unittest

from r2sp.agent import (
    AGENT_TOOLS,
    TRUSTED_APPWORLD_CONTROL_PLANE,
    AgentBudgets,
    AgentRunner,
)
from r2sp.model_client import ModelClientError
from r2sp.runtime import SyntheticRuntime


def tool_call(name, arguments, index):
    return {
        "id": f"call-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append((json.loads(json.dumps(messages)), kwargs))
        return self.responses.pop(0)


class FakeRetriever:
    def __init__(self):
        self.read_count = 0

    def search(self, query, *, top_k):
        return [
            {
                "resource_id": "doc-1",
                "app_name": "notes",
                "api_name": "add",
                "title": "Add note",
                "body": "must never appear in search",
                "score": 99.0,
            }
        ]

    def read(self, resource_id):
        self.read_count += 1
        return {
            "resource_id": resource_id,
            "app_name": "notes",
            "api_name": "add",
            "title": "Add note",
            "body": "Use notes.add with text.",
            "content_hash": "abc",
        }


class CandidateRetriever:
    def __init__(self):
        self.search_count = 0
        self.read_ids = []

    def search(self, query, *, top_k):
        self.search_count += 1
        start = 1 if query == "first" else 6 if query == "second" else 1
        return [
            {
                "resource_id": f"doc-{index}",
                "app_name": "notes",
                "api_name": "add",
                "title": f"Document {index}",
                "body": "must not be returned by search",
                "score": 100.0 - index,
            }
            for index in range(start, start + min(top_k, 5))
        ]

    def read(self, resource_id):
        self.read_ids.append(resource_id)
        return {
            "resource_id": resource_id,
            "app_name": "notes",
            "api_name": "add",
            "title": resource_id,
            "body": f"Full documentation for {resource_id}.",
            "content_hash": f"hash-{resource_id}",
        }


class AgentTests(unittest.TestCase):
    def test_only_normalized_model_failures_become_episode_failures(self):
        class FailingClient:
            def __init__(self, exception):
                self.exception = exception

            def complete(self, messages, **kwargs):
                del messages, kwargs
                raise self.exception

        normalized = AgentRunner(FailingClient(ModelClientError("timeout", "timed out"))).run(
            "task", {}, SyntheticRuntime(), FakeRetriever()
        )
        self.assertEqual(normalized.failure, "model_timeout")

        runtime = SyntheticRuntime()
        with self.assertRaisesRegex(RuntimeError, "programmer fault"):
            AgentRunner(FailingClient(RuntimeError("programmer fault"))).run(
                "task", {}, runtime, FakeRetriever()
            )
        with self.assertRaisesRegex(RuntimeError, "not been started"):
            runtime.execute("notes", "add", {})

    def test_unexpected_runtime_and_retriever_faults_propagate(self):
        class FaultyRetriever(FakeRetriever):
            def __init__(self, phase):
                super().__init__()
                self.phase = phase

            def search(self, query, *, top_k):
                del query, top_k
                raise RuntimeError("search programmer fault")

            def read(self, resource_id):
                del resource_id
                raise RuntimeError("read programmer fault")

        class FaultyRuntime(SyntheticRuntime):
            def __init__(self, phase):
                super().__init__()
                self.phase = phase

            def start(self):
                if self.phase == "start":
                    raise RuntimeError("start programmer fault")
                return super().start()

            def execute(self, app, api, args):
                if self.phase == "execute":
                    raise RuntimeError("execute programmer fault")
                return super().execute(app, api, args)

            def finish(self, status, answer):
                if self.phase == "finish":
                    raise RuntimeError("finish programmer fault")
                return super().finish(status, answer)

            def close(self):
                super().close()
                if self.phase == "close":
                    raise RuntimeError("close programmer fault")

        scenarios = (
            (
                "search",
                [tool_call("search_docs", {"query": "q"}, 1)],
                SyntheticRuntime(),
                FaultyRetriever("search"),
            ),
            (
                "read",
                [tool_call("read_doc", {"resource_id": "doc"}, 1)],
                SyntheticRuntime(),
                FaultyRetriever("read"),
            ),
            (
                "execute",
                [tool_call("execute", {"app": "notes", "api": "add", "args": {}}, 1)],
                FaultyRuntime("execute"),
                FakeRetriever(),
            ),
            (
                "finish",
                [tool_call("finish", {"status": "success", "answer": ""}, 1)],
                FaultyRuntime("finish"),
                FakeRetriever(),
            ),
        )
        for phase, calls, runtime, retriever in scenarios:
            with (
                self.subTest(phase=phase),
                self.assertRaisesRegex(RuntimeError, f"{phase} programmer fault"),
            ):
                AgentRunner(FakeClient([{"tool_calls": calls}])).run("task", {}, runtime, retriever)

        with self.assertRaisesRegex(RuntimeError, "start programmer fault"):
            AgentRunner(FakeClient([])).run("task", {}, FaultyRuntime("start"), FakeRetriever())
        with self.assertRaisesRegex(RuntimeError, "close programmer fault"):
            AgentRunner(
                FakeClient(
                    [
                        {
                            "tool_calls": [
                                tool_call(
                                    "finish",
                                    {"status": "success", "answer": ""},
                                    1,
                                )
                            ]
                        }
                    ]
                )
            ).run("task", {}, FaultyRuntime("close"), FakeRetriever())

    def test_unknown_document_id_is_a_normal_agent_visible_read_failure(self):
        class UnknownRetriever(FakeRetriever):
            def read(self, resource_id):
                raise KeyError(resource_id)

        client = FakeClient(
            [
                {"tool_calls": [tool_call("read_doc", {"resource_id": "missing"}, 1)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": ""}, 2)]},
            ]
        )
        result = AgentRunner(client).run("task", {}, SyntheticRuntime(), UnknownRetriever())
        self.assertTrue(result.task_success)
        self.assertEqual(result.read_trace[0]["error"], "unknown_resource_id")

    def test_full_four_tool_episode_and_trace(self):
        client = FakeClient(
            [
                {
                    "content": None,
                    "reasoning_content": "must not persist",
                    "tool_calls": [tool_call("search_docs", {"query": "add note"}, 1)],
                },
                {
                    "content": None,
                    "tool_calls": [tool_call("read_doc", {"resource_id": "doc-1"}, 2)],
                },
                {
                    "content": None,
                    "tool_calls": [
                        tool_call(
                            "execute",
                            {"app": "notes", "api": "add", "args": {"text": "x"}},
                            3,
                        )
                    ],
                },
                {
                    "content": None,
                    "tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 4)],
                },
            ]
        )
        retriever = FakeRetriever()
        runtime = SyntheticRuntime({("notes", "add"): lambda args: {"saved": args["text"]}})
        result = AgentRunner(client).run(
            "Add a note", {"notes": "Create and manage notes"}, runtime, retriever, seed=100
        )

        self.assertTrue(result.task_success)
        self.assertEqual(result.resource_ids, ("doc-1",))
        self.assertEqual(result.api_calls, 1)
        self.assertEqual(result.search_calls, 1)
        self.assertEqual(result.api_trace[0]["app"], "notes")
        self.assertIsNone(result.failure)
        self.assertEqual([call[1]["seed"] for call in client.calls], [100, 101, 102, 103])
        self.assertEqual(
            {tool["function"]["name"] for tool in client.calls[0][1]["tools"]},
            {"search_docs", "read_doc", "execute", "finish"},
        )
        second_prompt = json.dumps(client.calls[1][0])
        self.assertNotIn("must never appear in search", second_prompt)
        self.assertNotIn("99.0", second_prompt)
        self.assertNotIn("must not persist", second_prompt)

    def test_unique_read_budget_prevents_second_read(self):
        client = FakeClient(
            [
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-1"}, 1)]},
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-2"}, 2)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": ""}, 3)]},
            ]
        )
        retriever = FakeRetriever()
        runtime = SyntheticRuntime()
        runner = AgentRunner(
            client,
            budgets=AgentBudgets(
                max_turns=4,
                max_api_calls=2,
                max_search_calls=2,
                max_unique_docs_read=1,
            ),
        )
        result = runner.run("task", {"notes": "notes"}, runtime, retriever)
        self.assertEqual(retriever.read_count, 1)
        self.assertEqual(result.resource_ids, ("doc-1",))
        self.assertTrue(result.task_success)

    def test_simulated_credentials_are_visible_in_episode_but_redacted_from_trace(self):
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        tool_call(
                            "execute",
                            {
                                "app": "spotify",
                                "api": "login",
                                "args": {"username": "u", "password": "fixture-pass"},
                            },
                            1,
                        )
                    ]
                },
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": ""}, 2)]},
            ]
        )
        runtime = SyntheticRuntime(
            {("spotify", "login"): lambda args: {"access_token": "fixture-token"}}
        )

        result = AgentRunner(client).run("login", {"spotify": "Music"}, runtime, FakeRetriever())

        visible_next_turn = json.dumps(client.calls[1][0])
        durable_trace = json.dumps(result.api_trace)
        self.assertIn("fixture-token", visible_next_turn)
        self.assertNotIn("fixture-pass", durable_trace)
        self.assertNotIn("fixture-token", durable_trace)
        self.assertEqual(result.api_trace[0]["args"]["password"], "<redacted>")
        self.assertEqual(result.api_trace[0]["result"]["access_token"], "<redacted>")

    def test_prompt_has_fixed_supervisor_control_plane(self):
        client = FakeClient(
            [{"tool_calls": [tool_call("finish", {"status": "success", "answer": ""}, 1)]}]
        )
        AgentRunner(client).run("task", {"notes": "Notes"}, SyntheticRuntime(), FakeRetriever())

        payload = json.loads(client.calls[0][0][1]["content"])
        self.assertEqual(tuple(payload["trusted_control_plane"]), TRUSTED_APPWORLD_CONTROL_PLANE)
        self.assertEqual(
            {item["api"] for item in payload["trusted_control_plane"]},
            {
                "show_profile",
                "show_addresses",
                "show_payment_cards",
                "show_account_passwords",
            },
        )

    def test_context_budget_drops_oldest_complete_turn(self):
        class CountingClient(FakeClient):
            def count_tokens(self, text):
                return text.count('"role"') * 100

        client = CountingClient(
            [
                {"content": "first turn without a tool"},
                {"content": "second turn without a tool"},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": ""}, 3)]},
            ]
        )
        runner = AgentRunner(
            client,
            max_context_tokens=700,
            max_output_tokens=100,
            context_reserve_tokens=50,
        )

        result = runner.run("task", {"notes": "Notes"}, SyntheticRuntime(), FakeRetriever())

        self.assertTrue(result.task_success)
        self.assertEqual(result.context_truncations, 1)
        third_request = json.dumps(client.calls[2][0])
        self.assertNotIn("first turn without a tool", third_request)
        self.assertIn("second turn without a tool", third_request)

    def test_selection_mode_exposes_dynamic_exact_count_tool(self):
        client = FakeClient(
            [{"tool_calls": [tool_call("finish", {"status": "fail", "answer": ""}, 1)]}]
        )
        AgentRunner(client, selection_k=5).run(
            "task", {"notes": "Notes"}, SyntheticRuntime(), CandidateRetriever()
        )

        tools = client.calls[0][1]["tools"]
        self.assertEqual(
            [tool["function"]["name"] for tool in tools],
            ["search_docs", "select_docs", "read_doc", "execute", "finish"],
        )
        schema = tools[1]["function"]["parameters"]["properties"]["resource_ids"]
        self.assertEqual(schema["minItems"], 5)
        self.assertEqual(schema["maxItems"], 5)
        self.assertTrue(schema["uniqueItems"])

    def test_complete_selection_episode_records_candidate_and_selection_traces(self):
        selected = ["doc-7", "doc-2", "doc-9", "doc-4", "doc-6"]
        client = FakeClient(
            [
                {"tool_calls": [tool_call("search_docs", {"query": "first"}, 1)]},
                {"tool_calls": [tool_call("search_docs", {"query": "second"}, 2)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": selected}, 3)]},
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-7"}, 4)]},
                {
                    "tool_calls": [
                        tool_call(
                            "execute",
                            {"app": "notes", "api": "add", "args": {"text": "x"}},
                            5,
                        )
                    ]
                },
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 6)]},
            ]
        )
        retriever = CandidateRetriever()
        runtime = SyntheticRuntime({("notes", "add"): lambda args: {"saved": args["text"]}})

        result = AgentRunner(client, selection_k=5).run("task", {}, runtime, retriever)

        self.assertTrue(result.task_success)
        self.assertEqual(result.candidate_resource_ids, tuple(f"doc-{i}" for i in range(1, 11)))
        self.assertEqual(result.selected_resource_ids, tuple(selected))
        self.assertEqual(result.resource_ids, ("doc-7",))
        self.assertEqual(result.selection_trace[-1]["accepted"], True)
        self.assertEqual(result.selection_trace[-1]["resource_ids"], selected)
        self.assertEqual(retriever.read_ids, ["doc-7"])

    def test_invalid_selection_attempts_can_be_retried_without_mutating_selection(self):
        valid = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
        client = FakeClient(
            [
                {"tool_calls": [tool_call("search_docs", {"query": "first"}, 1)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": valid[:-1]}, 2)]},
                {
                    "tool_calls": [
                        tool_call(
                            "select_docs",
                            {"resource_ids": ["doc-1", "doc-2", "doc-3", "doc-4", "doc-4"]},
                            3,
                        )
                    ]
                },
                {
                    "tool_calls": [
                        tool_call(
                            "select_docs",
                            {"resource_ids": ["doc-1", "doc-2", "doc-3", "doc-4", "unseen"]},
                            4,
                        )
                    ]
                },
                {"tool_calls": [tool_call("select_docs", {"resource_ids": valid}, 5)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 6)]},
            ]
        )

        result = AgentRunner(client, selection_k=5).run(
            "task", {}, SyntheticRuntime(), CandidateRetriever()
        )

        self.assertEqual(result.selected_resource_ids, tuple(valid))
        self.assertEqual(
            [attempt.get("error") for attempt in result.selection_trace],
            [
                "selection_count_mismatch",
                "duplicate_resource_ids",
                "unseen_resource_ids",
                None,
            ],
        )

    def test_selection_is_immutable_and_search_after_selection_is_rejected(self):
        selected = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
        replacement = list(reversed(selected))
        client = FakeClient(
            [
                {"tool_calls": [tool_call("search_docs", {"query": "first"}, 1)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": selected}, 2)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": replacement}, 3)]},
                {"tool_calls": [tool_call("search_docs", {"query": "second"}, 4)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 5)]},
            ]
        )
        retriever = CandidateRetriever()

        result = AgentRunner(client, selection_k=5).run("task", {}, SyntheticRuntime(), retriever)

        self.assertEqual(result.selected_resource_ids, tuple(selected))
        self.assertEqual(result.selection_trace[-1]["error"], "selection_already_finalized")
        self.assertEqual(retriever.search_count, 1)
        last_prompt = json.dumps(client.calls[-1][0])
        self.assertIn("search_after_selection", last_prompt)

    def test_reads_before_or_outside_selection_do_not_call_retriever(self):
        selected = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
        client = FakeClient(
            [
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-1"}, 1)]},
                {"tool_calls": [tool_call("search_docs", {"query": "first"}, 2)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": selected}, 3)]},
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-9"}, 4)]},
                {"tool_calls": [tool_call("read_doc", {"resource_id": "doc-3"}, 5)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 6)]},
            ]
        )
        retriever = CandidateRetriever()

        result = AgentRunner(client, selection_k=5).run("task", {}, SyntheticRuntime(), retriever)

        self.assertEqual(retriever.read_ids, ["doc-3"])
        self.assertEqual(
            [item.get("error") for item in result.read_trace],
            ["selection_required", "resource_not_selected", None],
        )

    def test_execute_and_successful_finish_require_selection_but_fail_finish_does_not(self):
        executions = []
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        tool_call(
                            "execute",
                            {"app": "notes", "api": "add", "args": {"text": "x"}},
                            1,
                        )
                    ]
                },
                {
                    "tool_calls": [
                        tool_call("finish", {"status": "success", "answer": "premature"}, 2)
                    ]
                },
                {"tool_calls": [tool_call("finish", {"status": "fail", "answer": "stop"}, 3)]},
            ]
        )
        runtime = SyntheticRuntime({("notes", "add"): lambda args: executions.append(dict(args))})

        result = AgentRunner(client, selection_k=5).run("task", {}, runtime, CandidateRetriever())

        self.assertEqual(executions, [])
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(result.finish_status, "fail")
        next_prompt = json.dumps(client.calls[1][0])
        final_prompt = json.dumps(client.calls[2][0])
        self.assertIn("selection_required", next_prompt)
        self.assertIn("selection_required", final_prompt)

    def test_multi_tool_turn_is_rejected_atomically(self):
        selected = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        tool_call("search_docs", {"query": "first"}, 1),
                        tool_call("select_docs", {"resource_ids": selected}, 2),
                    ]
                },
                {"tool_calls": [tool_call("search_docs", {"query": "first"}, 3)]},
                {"tool_calls": [tool_call("select_docs", {"resource_ids": selected}, 4)]},
                {"tool_calls": [tool_call("finish", {"status": "success", "answer": "done"}, 5)]},
            ]
        )
        retriever = CandidateRetriever()

        result = AgentRunner(client, selection_k=5).run("task", {}, SyntheticRuntime(), retriever)

        self.assertEqual(retriever.search_count, 1)
        self.assertEqual(result.search_calls, 1)
        self.assertEqual(len(result.selection_trace), 1)
        rejected_prompt = json.dumps(client.calls[1][0])
        self.assertEqual(rejected_prompt.count("multiple_tool_calls_not_allowed"), 2)

    def test_selection_k_validation(self):
        for value in (True, 0, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AgentRunner(FakeClient([]), selection_k=value)

    def test_tool_catalog_contains_exactly_four_interfaces(self):
        self.assertEqual(
            [tool["function"]["name"] for tool in AGENT_TOOLS],
            ["search_docs", "read_doc", "execute", "finish"],
        )


if __name__ == "__main__":
    unittest.main()
