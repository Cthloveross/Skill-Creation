import copy
import json
import unittest
from pathlib import Path

import yaml

from r2sp.config import ConfigValidationError, ExperimentConfig, load_config, validate_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment_plan.yaml"


class ConfigTests(unittest.TestCase):
    def test_checked_in_v04_matches_the_file_backed_benign_poison_protocol(self) -> None:
        config = load_config(CONFIG_PATH)

        self.assertTrue(config.design_valid)
        self.assertTrue(config.validation.execution_ready)
        self.assertFalse(config.research_ready)
        self.assertFalse(config.protocol.research_eligible)
        self.assertEqual(config.protocol.version, "0.4")
        self.assertEqual(config.model.id, "Qwen/Qwen3.8-27B-FP8")
        self.assertEqual(
            config.model.revision,
            "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",
        )
        self.assertEqual(config.model.dtype, "float16")
        self.assertEqual(config.model.physical_gpu_ids, (0, 6))
        self.assertEqual(config.model.max_model_len, 32768)
        self.assertEqual(config.model.serving.tensor_parallel_size, 2)
        self.assertEqual(config.model.serving.pipeline_parallel_size, 1)
        self.assertEqual(config.compiler.model, "same_Qwen3.8_in_fresh_context")
        self.assertEqual(config.compiler.max_input_tokens, 23552)
        self.assertEqual(config.appworld.raw_endpoint_count, 457)
        self.assertEqual(config.appworld.task_facing_resource_count, 447)
        self.assertEqual(
            config.appworld.standard_corpus_sha256,
            "cd1125539a6d437a23f47556b595b69d020903e5be939c49695cff293a37a141",
        )
        self.assertEqual(
            config.appworld.task_facing_pool_manifest_sha256,
            "6626216a3149fdd74840b28247901b05691a60d6a769890a8ab1b8093db7de79",
        )
        self.assertEqual(config.resource_pool.clean_resources, 447)
        self.assertEqual(config.resource_pool.acquisition_resources, 447)
        self.assertEqual(config.resource_pool.deployment_resources, 447)
        self.assertEqual(config.resource_pool.benign.transform, "identity_copy")
        self.assertEqual(config.resource_pool.poison.modified_resource_count, 1)
        self.assertEqual(config.retriever.top_k, 10)
        self.assertEqual(config.retriever.model_select_k, 5)
        self.assertEqual(config.retriever.selection_scope, "poison_acquisition_only")
        self.assertTrue(config.retriever.selection_requires_exact_count)
        self.assertEqual(
            config.retriever.selection_candidates,
            "previously_retrieved_headers_union",
        )
        self.assertIn("select_docs", config.agent.tools)
        self.assertEqual(
            config.assay.task_provenance.source,
            "frozen_appworld_train_specs",
        )
        self.assertEqual(
            config.assay.task_provenance.instruction_binding,
            "exact_specs_instruction",
        )
        self.assertEqual(config.assay.profile_count, 2)
        self.assertEqual(config.gates.canonical_retrieval.required_profile_count, 2)
        self.assertTrue(config.gates.canonical_retrieval.on_any_failure.stop_pipeline)
        self.assertEqual(
            config.gates.canonical_retrieval.on_any_failure.next_action,
            "version_retrieval_lead_and_rematerialize",
        )
        self.assertEqual(config.gates.actual_acquisition.required_profile_count, 2)
        self.assertTrue(config.gates.actual_acquisition.on_any_failure.stop_pipeline)
        self.assertEqual(config.gates.compile.required_profile_count, 2)
        self.assertEqual(config.gates.deployment.required_compile_profile_count, 2)
        self.assertEqual(config.validation.readiness_gaps, ())

        encoded = json.dumps(config.to_dict(), sort_keys=True).lower()
        for stale in ("qwen3.5", "h200", "smoke", "overlay", "sixteen_case"):
            self.assertNotIn(stale, encoded)

    def test_runner_flag_is_an_execution_readiness_gate(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        blocked = copy.deepcopy(raw)
        blocked["protocol"]["runner_ready"] = False

        report = validate_config(blocked)

        self.assertTrue(report.design_valid)
        self.assertFalse(report.research_ready)
        self.assertEqual(
            report.readiness_gaps,
            ("protocol.runner_ready is false",),
        )

    def test_research_mode_rejects_the_bounded_nonresearch_assay(self) -> None:
        with self.assertRaisesRegex(
            ConfigValidationError,
            "protocol.research_eligible is false",
        ):
            load_config(CONFIG_PATH, require_research_ready=True)

    def test_official_bundle_hash_is_a_frozen_contract_field(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["appworld"]["data_bundle_sha256"] = "fill_after_download"

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(any("data_bundle_sha256" in error for error in report.errors))

    def test_cross_field_resource_count_mismatch_is_design_invalid(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["resource_pool"]["acquisition_resources"] = 448

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(any("acquisition_resources" in error for error in report.errors))
        with self.assertRaises(ConfigValidationError):
            ExperimentConfig.from_dict(invalid)

    def test_every_global_gate_requires_both_fixed_profiles(self) -> None:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(raw)
        invalid["gates"]["actual_acquisition"]["required_profile_count"] = 1

        report = validate_config(invalid)

        self.assertFalse(report.design_valid)
        self.assertTrue(any("required_profile_count" in error for error in report.errors))

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
