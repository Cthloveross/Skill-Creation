from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from r2sp.artifacts import sha256_file
from r2sp.qualification_live import (
    QUALIFICATION_CONFIG_PATH,
    _load_qualification_contract,
    _parser,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "configs/experiment_plan.yaml"


class QualificationLiveTests(unittest.TestCase):
    def test_frozen_qualification_contract_binds_base_and_strict_counts(self) -> None:
        contract = _load_qualification_contract(
            ROOT,
            QUALIFICATION_CONFIG_PATH,
            base_config=BASE_CONFIG,
            base_config_sha256=sha256_file(BASE_CONFIG),
        )

        value = contract["value"]
        self.assertEqual(value["compile"]["compiler_calls"], 4)
        self.assertEqual(value["deployment"]["episode_count"], 8)
        self.assertFalse(value["deployment"]["resource_pool_attached"])
        self.assertEqual(value["deployment"]["tools"], ["execute", "finish"])
        self.assertEqual(value["contamination"]["arms"]["poison"]["rho"], 1 / 447)
        self.assertEqual(value["compile"]["acquisition_mode"], "retrieval_only")
        self.assertEqual(value["compile"]["acquisition_max_turns"], 20)
        self.assertEqual(
            value["compile"]["acquisition_tools"],
            ["search_docs", "select_docs", "read_doc", "finish"],
        )
        self.assertEqual(
            value["compile"]["acquisition_completion"]["accepted_finish_statuses"],
            ["fail"],
        )
        self.assertTrue(
            value["compile"]["acquisition_completion"]["stop_immediately_if_incomplete"]
        )
        self.assertTrue(value["compile"]["poison_exposure_gate"]["stop_immediately_on_failure"])

    def test_qualification_contract_rejects_base_hash_drift(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "differs from the frozen protocol"):
            _load_qualification_contract(
                ROOT,
                QUALIFICATION_CONFIG_PATH,
                base_config=BASE_CONFIG,
                base_config_sha256="0" * 64,
            )

    def test_qualification_contract_rejects_relaxed_resource_tools(self) -> None:
        source = ROOT / QUALIFICATION_CONFIG_PATH
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
        payload["deployment"]["tools"].append("read_doc")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "qualification.yaml"
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "differs from the frozen protocol"):
                _load_qualification_contract(
                    ROOT,
                    path,
                    base_config=BASE_CONFIG,
                    base_config_sha256=sha256_file(BASE_CONFIG),
                )

    def test_cli_has_separate_write_once_compile_and_deploy_commands(self) -> None:
        parser = _parser()
        compile_args = parser.parse_args(
            [
                "compile",
                "--appworld-root",
                "source",
                "--bundle-directory",
                "bundles",
                "--output",
                "run/compile",
            ]
        )
        deploy_args = parser.parse_args(
            [
                "deploy",
                "--appworld-root",
                "source",
                "--bundle-directory",
                "bundles",
                "--compile-directory",
                "run/compile",
                "--compile-complete-sha256",
                "0" * 64,
                "--output",
                "run/deploy",
            ]
        )

        self.assertEqual(compile_args.command, "compile")
        self.assertEqual(deploy_args.command, "deploy")
        self.assertEqual(deploy_args.compile_directory, "run/compile")
        self.assertEqual(compile_args.base_url, "http://127.0.0.1:18138/v1")
        self.assertEqual(deploy_args.base_url, "http://127.0.0.1:18138/v1")


if __name__ == "__main__":
    unittest.main()
