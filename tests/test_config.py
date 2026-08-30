import copy
import unittest
from pathlib import Path

import yaml

from r2sp.config import ConfigValidationError, ExperimentConfig, load_config, validate_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment_plan.yaml"


class ConfigTests(unittest.TestCase):
    def test_checked_in_v03_is_design_valid_but_not_research_ready(self) -> None:
        config = load_config(CONFIG_PATH)

        self.assertTrue(config.design_valid)
        self.assertFalse(config.research_ready)
        self.assertEqual(config.protocol.version, "0.3")
        self.assertEqual(config.resource_pool.clean_resources, 457)
        self.assertEqual(config.retriever.top_k, 10)
        self.assertEqual(config.retriever.model_select_k, 5)
        self.assertEqual(config.retriever.selection_scope, "acquisition_only")
        self.assertTrue(config.retriever.selection_requires_exact_count)
        self.assertEqual(
            config.retriever.selection_candidates,
            "previously_retrieved_headers_union",
        )
        self.assertIn("select_docs", config.agent.tools)
        self.assertEqual(
            config.pilot.task_provenance.research_source,
            "frozen_appworld_train_case_ids",
        )
        self.assertEqual(
            config.pilot.task_provenance.research_instruction_binding,
            "exact_world.task.instruction",
        )
        self.assertEqual(
            config.pilot.task_provenance.synthetic_source,
            "src/r2sp/fixtures.py",
        )
        self.assertFalse(config.pilot.task_provenance.model_generated_tasks)
        self.assertEqual(
            config.validation.readiness_gaps,
            (
                "protocol.runner_ready is false",
                "appworld.data_bundle_sha256 is not a frozen SHA-256 digest",
            ),
        )

    def test_ready_flag_and_real_bundle_hash_make_valid_design_ready(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        ready = copy.deepcopy(raw)
        ready["protocol"]["runner_ready"] = True
        ready["appworld"]["data_bundle_sha256"] = "a" * 64

        report = validate_config(ready)

        self.assertTrue(report.design_valid)
        self.assertTrue(report.research_ready)

    def test_cross_field_episode_mismatch_is_design_invalid(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["pilot"]["deployment_episodes"] = 63

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(any("deployment_episodes" in error for error in report.errors))
        with self.assertRaises(ConfigValidationError):
            ExperimentConfig.from_dict(invalid)

    def test_unsafe_retrieval_output_is_design_invalid(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["retriever"]["search_returns_body"] = True
        self.assertFalse(validate_config(invalid).design_valid)

    def test_model_selection_must_fit_inside_bm25_candidates(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["retriever"]["model_select_k"] = 11

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(
            any("model_select_k must be <= retriever.top_k" in error for error in report.errors)
        )

    def test_model_selection_count_must_be_positive(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["retriever"]["model_select_k"] = 0

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(
            any("retriever.model_select_k must be positive" in error for error in report.errors)
        )

    def test_read_budget_must_cover_exact_model_selection(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["retriever"]["max_unique_docs_read"] = 4

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(
            any(
                "max_unique_docs_read must be >= retriever.model_select_k" in error
                for error in report.errors
            )
        )

    def test_exact_selection_requires_select_docs_tool(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["agent"]["tools"] = [
            tool for tool in invalid["agent"]["tools"] if tool != "select_docs"
        ]

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(
            any("agent.tools must include select_docs" in error for error in report.errors)
        )


if __name__ == "__main__":
    unittest.main()
