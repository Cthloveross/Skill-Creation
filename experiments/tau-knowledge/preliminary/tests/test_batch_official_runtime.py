"""Offline checks using the real, pinned official banking runtime."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_EXPECTED_PREFIX = (
    Path(__file__).resolve().parents[1] / "data" / "upstream" / "tau2-bench" / ".venv"
).resolve()
if sys.version_info[:3] != (3, 12, 14) or Path(sys.prefix).resolve() != _EXPECTED_PREFIX:
    raise unittest.SkipTest("requires the pinned tau2 Python 3.12.14 environment")

from tau2.data_model.message import (  # noqa: E402
    AssistantMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.data_model.simulation import SimulationRun, TerminationReason  # noqa: E402

from r2sp_common import RetrieverClosedError  # noqa: E402
from r2sp_tau_knowledge import batch_official_runtime, batch_official_worker  # noqa: E402
from r2sp_tau_knowledge.batch_constants import MODEL_ID, MODEL_REVISION, SELECTION_K  # noqa: E402
from r2sp_tau_knowledge.data import load_documents  # noqa: E402
from r2sp_tau_knowledge.hybrid_retrieval import (  # noqa: E402
    QWEN3_EMBEDDING_ARTIFACT_SHA256,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_REVISION,
)


class OfflineDenseEmbedder:
    model_id = QWEN3_EMBEDDING_MODEL_ID
    revision = QWEN3_EMBEDDING_REVISION
    artifact_sha256 = QWEN3_EMBEDDING_ARTIFACT_SHA256

    def embed_documents(self, texts):
        return [[1.0, 0.0] if "gold" in text.casefold() else [0.0, 1.0] for text in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "gold" in text.casefold() else [0.0, 1.0]


class BatchOfficialRuntimeTest(unittest.TestCase):
    def bundle(self, *, acquisition=False, task_id="task_002"):
        bundle = batch_official_runtime.build_benign_batch_runtime(
            mode="acquisition" if acquisition else "deployment",
            task_id=task_id,
            model=MODEL_ID,
            endpoint="http://127.0.0.1:18138/v1",
            seed=7,
            skill_text=None if acquisition else "Use the supplied banking reference facts.",
            dense_embedder=OfflineDenseEmbedder() if acquisition else None,
        )
        self.addCleanup(bundle.close)
        return bundle

    def test_acquisition_uses_official_documents_for_any_registered_task(self):
        bundle = self.bundle(acquisition=True, task_id="task_003")
        self.assertEqual(bundle.task.id, "task_003")
        self.assertIn("search_web", bundle.exposed_tool_names)
        self.assertIn("select_docs", bundle.exposed_tool_names)
        self.assertNotIn("open_page", bundle.exposed_tool_names)
        tool = next(tool for tool in bundle.environment.get_tools() if tool.name == "select_docs")
        schema = tool.openai_schema["function"]["parameters"]["properties"]["page_ids"]
        self.assertEqual(schema["minItems"], SELECTION_K)
        self.assertEqual(schema["maxItems"], SELECTION_K)
        self.assertTrue(schema["uniqueItems"])
        search = bundle.environment.get_response(
            ToolCall(id="search-1", name="search_web", arguments={"query": "gold rewards card"})
        )
        self.assertFalse(search.error)
        candidates = json.loads(search.content)["results"]
        self.assertGreaterEqual(len(candidates), SELECTION_K)
        original = {document.page_id: document for document in load_documents()}
        for page in candidates:
            self.assertEqual(set(page), {"page_id", "title", "body"})
            self.assertEqual(page["body"], original[page["page_id"]].body)
        selected_ids = [page["page_id"] for page in candidates[:SELECTION_K]]
        selected = bundle.environment.get_response(
            ToolCall(id="select-1", name="select_docs", arguments={"page_ids": selected_ids})
        )
        self.assertFalse(selected.error)
        self.assertTrue(bundle.selection_complete)
        self.assertEqual([page.page_id for page in bundle.opened_pages], selected_ids)
        with self.assertRaises(RetrieverClosedError):
            bundle.retriever.search_web("another query")

    def test_utility_has_fresh_identity_and_only_normal_banking_tools(self):
        first, second = self.bundle(), self.bundle(task_id="task_003")
        forbidden = {
            "search_web",
            "select_docs",
            "open_page",
            "mock_api_record",
            "sandbox_delete_sentinel",
        }
        for bundle in (first, second):
            self.assertIsNone(bundle.retriever)
            self.assertFalse(hasattr(bundle, "sidecar"))
            self.assertFalse(hasattr(bundle, "profile"))
            self.assertFalse(set(bundle.exposed_tool_names) & forbidden)
            self.assertIn("transfer_to_human_agents", bundle.exposed_tool_names)
            self.assertNotIn(str(bundle.task.user_scenario), bundle.agent.domain_policy)
            bundle.orchestrator.initialize()
            self.assertEqual(len(bundle.orchestrator.trajectory), 1)
        self.assertIsNot(first.toolkit.db, second.toolkit.db)
        self.assertNotEqual(
            first.runtime_identity.execution_id, second.runtime_identity.execution_id
        )
        self.assertTrue(
            set(first.runtime_identity.instances.values()).isdisjoint(
                second.runtime_identity.instances.values()
            )
        )

    def test_model_arguments_keep_agent_and_user_roles_distinct(self):
        agent = batch_official_runtime._agent_llm_args("http://localhost:18138/v1", 7)
        user = batch_official_runtime._user_llm_args("http://localhost:18138/v1", 7)
        self.assertEqual(agent["seed"], 7)
        self.assertEqual(user["seed"], 7)
        self.assertEqual(agent["max_tokens"], 16384)
        self.assertEqual(user["max_tokens"], 8192)
        self.assertTrue(agent["extra_body"]["chat_template_kwargs"]["enable_thinking"])
        self.assertFalse(user["extra_body"]["chat_template_kwargs"]["enable_thinking"])

    def test_evaluator_filters_retrieval_and_provider_envelopes(self):
        messages = [
            UserMessage(role="user", content="Please explain this reference."),
            AssistantMessage(
                role="assistant",
                content="I will read the reference.",
                tool_calls=[
                    ToolCall(id="select-1", name="select_docs", arguments={"page_ids": []})
                ],
                raw_data={"provider_copy": "select_docs"},
            ),
            ToolMessage(role="tool", id="select-1", content="Reference text"),
            AssistantMessage(
                role="assistant", content="Here is the answer.", raw_data={"unused": 1}
            ),
        ]
        filtered = batch_official_runtime.filter_official_evaluator_trajectory(messages)
        self.assertEqual(len(filtered), 3)
        self.assertTrue(all(not getattr(message, "tool_calls", None) for message in filtered))
        self.assertTrue(all(getattr(message, "raw_data", None) is None for message in filtered))
        self.assertIsNotNone(messages[1].raw_data)

    def test_snapshot_failure_prevents_building_a_runtime(self):
        with (
            patch(
                "r2sp_tau_knowledge.data.verify_tracked_snapshot",
                side_effect=ValueError("snapshot"),
            ),
            self.assertRaisesRegex(ValueError, "snapshot"),
        ):
            self.bundle(acquisition=True)

    def test_worker_rejects_extra_fields_and_nonbenign_modes_before_runtime(self):
        base = {
            "mode": "batch-benign-acquisition",
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "endpoint": "http://127.0.0.1:18138/v1",
                "max_context_tokens": 65536,
            },
            "task_id": "task_003",
            "seed": 7,
            "simulation_id": "test",
            "corpus": "benign",
        }
        mutations = [
            {"mode": "acquisition"},
            {"corpus": "poison"},
            {"seed": -1},
            {"provider": "codex"},
            {"profile": "extra"},
            {"corpus_directory": "/external"},
        ]
        with patch.object(batch_official_runtime, "build_benign_batch_runtime") as build:
            for mutation in mutations:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    batch_official_worker.run_request(base | mutation)
            build.assert_not_called()

    def test_worker_returns_bound_official_record_and_metrics(self):
        skill = "Use the supplied banking reference facts."
        bundle = self.bundle()
        simulation = SimulationRun(
            id="fixture",
            task_id="task_002",
            start_time="2026-09-01T00:00:00",
            end_time="2026-09-01T00:00:01",
            duration=1.0,
            seed=7,
            termination_reason=TerminationReason.USER_STOP,
            messages=[UserMessage(role="user", content="Please explain this reference.")],
        )
        result = SimpleNamespace(
            task_success=True,
            reward=1.0,
            first_user_utterance="Please explain this reference.",
            public_trace=batch_official_runtime.normalize_public_trace(simulation.messages),
            evaluation=SimpleNamespace(filtered_simulation=simulation, excluded_tool_calls=()),
        )
        with (
            patch.object(batch_official_runtime, "build_benign_batch_runtime", return_value=bundle),
            patch.object(batch_official_runtime, "run_official", return_value=result),
        ):
            response = batch_official_worker.run_request(
                {
                    "mode": "batch-utility-deployment",
                    "model": {
                        "id": MODEL_ID,
                        "revision": MODEL_REVISION,
                        "endpoint": "http://127.0.0.1:18138/v1",
                        "max_context_tokens": 65536,
                    },
                    "task_id": "task_002",
                    "seed": 7,
                    "simulation_id": "fixture",
                    "skill_text": skill,
                    "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
                }
            )
        self.assertEqual(response["official_trajectory"]["task_id"], "task_002")
        self.assertEqual(response["runtime_identity"], bundle.runtime_identity.to_dict())
        self.assertEqual(response["opened_pages"], [])
        self.assertEqual(response["search_events"], [])
        self.assertGreaterEqual(response["duration_seconds"], 0)
        self.assertNotIn("canary_hit", response)


if __name__ == "__main__":
    unittest.main()
