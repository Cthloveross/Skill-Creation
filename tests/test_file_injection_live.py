from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from r2sp.appworld_payloads import DEFAULT_APPWORLD_INJECTION_DIRECTORY
from r2sp.artifacts import sha256_file, verify_artifact_manifest
from r2sp.config import load_config
from r2sp.file_injection_fixture import (
    EXPECTED_RAW_ENDPOINT_COUNT,
    EXPECTED_TASK_FACING_COUNT,
    load_appworld_file_fixtures,
    materialize_appworld_file_bundles,
)
from r2sp.file_injection_live import (
    APPWORLD_STANDARD_CORPUS_SHA256,
    APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256,
    FileBackedCompileClientProvider,
    _compiler_config,
    _LazyFileBackedCompileClientProvider,
    _parser,
    _require_effective_config_match,
    run_live_compile,
    run_live_deployment,
    run_live_retrieval,
)
from r2sp.fixtures import INJECTION_PROFILES, make_injection_fixture
from r2sp.injection_deployment_runner import PoisonDeploymentError
from r2sp.injection_runner import run_injection_compile_gate
from tests.test_file_injection_fixture import _make_appworld_tree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/appworld/preliminary/configs/experiment_plan.yaml"


def _official_source_evidence() -> dict[str, object]:
    return {
        "schema_version": "test.file-backed-source.v1",
        "source_type": "appworld_standard_json_file_backed",
        "source_corpus_sha256": APPWORLD_STANDARD_CORPUS_SHA256,
        "source_pool_manifest_hash": APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256,
        "raw_endpoint_count": EXPECTED_RAW_ENDPOINT_COUNT,
        "task_facing_endpoint_count": EXPECTED_TASK_FACING_COUNT,
        "excluded_helpers": ["api_docs", "supervisor"],
    }


class FileInjectionLiveConfigTests(unittest.TestCase):
    def test_materialize_cli_requires_explicit_payload_directory(self) -> None:
        parser = _parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "materialize",
                    "--appworld-root",
                    "source",
                    "--output",
                    "bundles",
                ]
            )
        args = parser.parse_args(
            [
                "materialize",
                "--appworld-root",
                "source",
                "--payload-directory",
                "payloads",
                "--output",
                "bundles",
            ]
        )
        self.assertEqual(args.payload_directory, "payloads")

    def test_official_source_commitments_are_frozen(self) -> None:
        self.assertEqual(
            APPWORLD_STANDARD_CORPUS_SHA256,
            "cd1125539a6d437a23f47556b595b69d020903e5be939c49695cff293a37a141",
        )
        self.assertEqual(
            APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256,
            "6626216a3149fdd74840b28247901b05691a60d6a769890a8ab1b8093db7de79",
        )

    def test_qwen38_mock_compiler_reserves_visible_output_budget(self) -> None:
        config = _compiler_config("mock-api-call")

        self.assertFalse(config.enable_thinking)
        self.assertIsNone(config.preserve_thinking)
        self.assertIsNone(config.reasoning_effort)

    def test_qwen38_delete_compiler_reserves_visible_output_budget(self) -> None:
        config = _compiler_config("delete-sentinel")

        self.assertFalse(config.enable_thinking)
        self.assertIsNone(config.preserve_thinking)
        self.assertIsNone(config.reasoning_effort)

    def test_qwen38_compiler_rejects_unknown_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown file-injection compiler profile"):
            _compiler_config("unknown-profile")

    def test_compiler_prompt_requires_closed_yaml_frontmatter(self) -> None:
        prompt = (
            PROJECT_ROOT
            / "experiments"
            / "appworld"
            / "preliminary"
            / "prompts"
            / "compiler_system.md"
        ).read_text(encoding="utf-8")

        self.assertIn("second standalone `---` delimiter", prompt)

    def test_all_live_cli_commands_accept_the_same_config_option(self) -> None:
        parser = _parser()
        commands = (
            [
                "retrieve",
                "--appworld-root",
                "source",
                "--bundle-directory",
                "bundles",
                "--output",
                "retrieval",
            ],
            [
                "compile",
                "--appworld-root",
                "source",
                "--bundle-directory",
                "bundles",
                "--output",
                "compile",
            ],
            [
                "deploy",
                "--appworld-root",
                "source",
                "--bundle-directory",
                "bundles",
                "--compile-gate-directory",
                "compile",
                "--compile-complete-sha256",
                "0" * 64,
                "--output",
                "deployment",
            ],
        )
        for command in commands:
            with self.subTest(command=command[0]):
                args = parser.parse_args([*command, "--config", "custom-plan.yaml"])
                self.assertEqual(args.config, "custom-plan.yaml")

    def test_generator_evidence_commits_effective_config_without_superseded_claims(
        self,
    ) -> None:
        experiment = load_config(DEFAULT_CONFIG)
        binding = _require_effective_config_match(
            DEFAULT_CONFIG,
            sha256_file(DEFAULT_CONFIG),
            experiment,
            _official_source_evidence(),
        )
        provider = FileBackedCompileClientProvider(
            "http://127.0.0.1:18138/v1",
            observed_service_catalog={
                "endpoint": "http://127.0.0.1:18138/v1/models",
                "model_id": "Qwen/Qwen3.8-27B-FP8",
                "max_model_len": 32768,
            },
            effective_config=binding,
        )

        generator = provider.generator
        self.assertEqual(
            generator["effective_config_commitment"]["sha256"],
            sha256_file(DEFAULT_CONFIG),
        )
        self.assertEqual(generator["effective_config_match"]["status"], "matched")
        self.assertNotIn("superseded", json.dumps(generator, sort_keys=True))

    def test_config_toctou_drift_is_rejected_before_service_or_http_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "experiment.yaml"
            config.write_bytes(DEFAULT_CONFIG.read_bytes())
            experiment = load_config(config)
            binding = _require_effective_config_match(
                config,
                sha256_file(config),
                experiment,
                _official_source_evidence(),
            )
            lazy_provider = _LazyFileBackedCompileClientProvider(
                "http://127.0.0.1:18138/v1",
                effective_config=binding,
            )
            config.write_text(
                config.read_text(encoding="utf-8") + "\n# post-validation drift\n",
                encoding="utf-8",
            )
            with (
                patch("r2sp.file_injection_live._verify_service") as verify_service,
                patch(
                    "r2sp.file_injection_live.FileBackedCompileClientProvider"
                ) as concrete_provider,
                self.assertRaisesRegex(RuntimeError, "changed before service access"),
            ):
                _ = lazy_provider.generator

            verify_service.assert_not_called()
            concrete_provider.assert_not_called()

    def test_retrieval_entry_writes_model_free_write_once_artifact(self) -> None:
        fixtures = {name: make_injection_fixture(name) for name in INJECTION_PROFILES}
        loaded = SimpleNamespace(fixtures=fixtures)
        source_evidence = _official_source_evidence()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "r2sp.file_injection_live.load_appworld_file_fixtures",
                return_value=loaded,
            ),
            patch(
                "r2sp.file_injection_live._verified_source_evidence",
                return_value=source_evidence,
            ),
            patch(
                "r2sp.file_injection_live._verify_service",
                side_effect=AssertionError("retrieval-only must not contact the model service"),
            ),
        ):
            output = Path(directory) / "retrieval"
            result = run_live_retrieval(
                appworld_root=Path(directory) / "source",
                bundle_directory=Path(directory) / "bundle",
                output_directory=output,
                project_root=PROJECT_ROOT,
                config_path=DEFAULT_CONFIG,
            )

            self.assertTrue(result.gate["passed"])
            self.assertEqual(result.complete_hash, sha256_file(output / "complete.json"))
            self.assertEqual(list(output.rglob("SKILL.md")), [])
            run = json.loads((output / "run.json").read_text(encoding="utf-8"))
            gate = json.loads((output / "gate.json").read_text(encoding="utf-8"))
            complete = json.loads((output / "complete.json").read_text(encoding="utf-8"))
            self.assertRegex(run["started_at"], r"Z$")
            self.assertEqual(complete["started_at"], run["started_at"])
            self.assertRegex(complete["completed_at"], r"Z$")
            self.assertIsInstance(complete["duration_seconds"], float)
            self.assertGreaterEqual(complete["duration_seconds"], 0.0)
            for payload in (run, gate, complete):
                self.assertFalse(payload["model_requested"])
                self.assertFalse(payload["compiler_constructed"])
                self.assertFalse(payload["skill_created"])
            verify_artifact_manifest(output, output / "artifacts-manifest.json")

            with self.assertRaisesRegex(RuntimeError, "already exists"):
                run_live_retrieval(
                    appworld_root=Path(directory) / "source",
                    bundle_directory=Path(directory) / "bundle",
                    output_directory=output,
                    project_root=PROJECT_ROOT,
                    config_path=DEFAULT_CONFIG,
                )

    def test_canonical_miss_never_accesses_service_or_constructs_http_provider(
        self,
    ) -> None:
        from r2sp.injection_evaluation import evaluate_canonical_task_retrieval

        experiment = load_config(DEFAULT_CONFIG)
        binding = _require_effective_config_match(
            DEFAULT_CONFIG,
            sha256_file(DEFAULT_CONFIG),
            experiment,
            _official_source_evidence(),
        )
        lazy_provider = _LazyFileBackedCompileClientProvider(
            "http://127.0.0.1:18138/v1",
            effective_config=binding,
        )

        def forced_rank_eleven(**kwargs: Any) -> Any:
            evidence = evaluate_canonical_task_retrieval(**kwargs)
            target = kwargs["target"]
            if INJECTION_PROFILES["mock-api-call"].nonce in target.body:
                return replace(evidence, entered_top_k=False, rank=11)
            return evidence

        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "r2sp.injection_runner.evaluate_canonical_task_retrieval",
                side_effect=forced_rank_eleven,
            ),
            patch("r2sp.file_injection_live._verify_service") as verify_service,
            patch("r2sp.file_injection_live.FileBackedCompileClientProvider") as concrete_provider,
        ):
            result = run_injection_compile_gate(
                Path(directory) / "compile",
                project_root=PROJECT_ROOT,
                config_path=DEFAULT_CONFIG,
                client_provider=lazy_provider,
            )

        self.assertFalse(result.gate["compile_gate_passed"])
        verify_service.assert_not_called()
        concrete_provider.assert_not_called()

    def test_invalid_deployment_gate_never_accesses_service_or_constructs_http_provider(
        self,
    ) -> None:
        fixtures = {name: make_injection_fixture(name) for name in INJECTION_PROFILES}
        loaded = SimpleNamespace(fixtures=fixtures)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "r2sp.file_injection_live.load_appworld_file_fixtures",
                return_value=loaded,
            ),
            patch(
                "r2sp.file_injection_live._verified_source_evidence",
                return_value=_official_source_evidence(),
            ),
            patch("r2sp.file_injection_live._verify_service") as verify_service,
            patch(
                "r2sp.file_injection_live.FileBackedDeploymentClientProvider"
            ) as concrete_provider,
        ):
            temporary = Path(directory)
            with self.assertRaises(PoisonDeploymentError):
                run_live_deployment(
                    appworld_root=temporary / "source",
                    bundle_directory=temporary / "bundle",
                    compile_gate_directory=temporary / "missing-compile-gate",
                    compile_complete_sha256="0" * 64,
                    output_directory=temporary / "deployment",
                    project_root=PROJECT_ROOT,
                    config_path=DEFAULT_CONFIG,
                )

        verify_service.assert_not_called()
        concrete_provider.assert_not_called()

    def test_official_live_entries_reject_non_target_source_drift_before_model_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld = _make_appworld_tree(temporary / "appworld")
            source_bundle = appworld / "source-bundles/data-0.1.0.bundle"
            source_bundle.parent.mkdir(parents=True)
            source_bundle.write_bytes(b"frozen-test-bundle")

            pristine_bundles = temporary / "pristine-bundles"
            materialize_appworld_file_bundles(
                appworld,
                pristine_bundles,
                payload_directory=DEFAULT_APPWORLD_INJECTION_DIRECTORY,
            )
            pristine = load_appworld_file_fixtures(appworld, pristine_bundles)

            non_target = appworld / "data/api_docs/standard/benign_catalog.json"
            payload = json.loads(non_target.read_text(encoding="utf-8"))
            payload["benign_endpoint_000"]["description"] += " Drifted after acquisition."
            non_target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            drifted_bundles = temporary / "drifted-bundles"
            materialize_appworld_file_bundles(
                appworld,
                drifted_bundles,
                payload_directory=DEFAULT_APPWORLD_INJECTION_DIRECTORY,
            )

            constant_patches = (
                patch(
                    "r2sp.file_injection_live.APPWORLD_BUNDLE_SIZE",
                    source_bundle.stat().st_size,
                ),
                patch(
                    "r2sp.file_injection_live.APPWORLD_BUNDLE_SHA256",
                    sha256_file(source_bundle),
                ),
                patch(
                    "r2sp.file_injection_live.APPWORLD_STANDARD_CORPUS_SHA256",
                    pristine.source_evidence["source_corpus_sha256"],
                ),
                patch(
                    "r2sp.file_injection_live.APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256",
                    pristine.source_evidence["source_pool_manifest_hash"],
                ),
            )
            for context in constant_patches:
                context.start()
                self.addCleanup(context.stop)

            with patch("r2sp.file_injection_live._verify_service") as verify_service:
                with self.assertRaisesRegex(RuntimeError, "standard corpus hash differs"):
                    run_live_retrieval(
                        appworld_root=appworld,
                        bundle_directory=drifted_bundles,
                        output_directory=temporary / "retrieval",
                        project_root=PROJECT_ROOT,
                    )
                verify_service.assert_not_called()

            with (
                patch("r2sp.file_injection_live._verify_service") as verify_service,
                patch("r2sp.file_injection_live.FileBackedCompileClientProvider") as provider,
            ):
                with self.assertRaisesRegex(RuntimeError, "standard corpus hash differs"):
                    run_live_compile(
                        appworld_root=appworld,
                        bundle_directory=drifted_bundles,
                        output_directory=temporary / "compile",
                        project_root=PROJECT_ROOT,
                    )
                verify_service.assert_not_called()
                provider.assert_not_called()

            with (
                patch("r2sp.file_injection_live._verify_service") as verify_service,
                patch("r2sp.file_injection_live.FileBackedDeploymentClientProvider") as provider,
            ):
                with self.assertRaisesRegex(RuntimeError, "standard corpus hash differs"):
                    run_live_deployment(
                        appworld_root=appworld,
                        bundle_directory=drifted_bundles,
                        compile_gate_directory=temporary / "compile-gate",
                        compile_complete_sha256="0" * 64,
                        output_directory=temporary / "deployment",
                        project_root=PROJECT_ROOT,
                    )
                verify_service.assert_not_called()
                provider.assert_not_called()

    def test_official_live_compile_rejects_pool_manifest_drift_before_model_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld = temporary / "appworld"
            source_bundle = appworld / "source-bundles/data-0.1.0.bundle"
            source_bundle.parent.mkdir(parents=True)
            source_bundle.write_bytes(b"frozen-test-bundle")
            loaded = SimpleNamespace(
                fixtures={},
                source_evidence={
                    "source_corpus_sha256": APPWORLD_STANDARD_CORPUS_SHA256,
                    "source_pool_manifest_hash": "0" * 64,
                },
            )

            with (
                patch(
                    "r2sp.file_injection_live.load_appworld_file_fixtures",
                    return_value=loaded,
                ),
                patch(
                    "r2sp.file_injection_live.APPWORLD_BUNDLE_SIZE",
                    source_bundle.stat().st_size,
                ),
                patch(
                    "r2sp.file_injection_live.APPWORLD_BUNDLE_SHA256",
                    sha256_file(source_bundle),
                ),
                patch("r2sp.file_injection_live._verify_service") as verify_service,
                patch("r2sp.file_injection_live.FileBackedCompileClientProvider") as provider,
                patch("r2sp.file_injection_live.run_injection_compile_gate") as runner,
            ):
                with self.assertRaisesRegex(RuntimeError, "pool manifest hash differs"):
                    run_live_compile(
                        appworld_root=appworld,
                        bundle_directory=temporary / "bundles",
                        output_directory=temporary / "compile",
                        project_root=PROJECT_ROOT,
                    )
                verify_service.assert_not_called()
                provider.assert_not_called()
                runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
