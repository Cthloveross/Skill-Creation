from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from r2sp.artifacts import ArtifactStore, sha256_file
from r2sp.cli import main
from r2sp.model_probe import ModelProbeCheck, ModelProbeReport
from r2sp.preflight import PreflightReport
from tests.test_cases import bundle_payload

ROOT = Path(__file__).resolve().parents[1]


def runtime_payload(external_root: Path) -> dict:
    return {
        "runtime": {
            "mode": "research",
            "appworld_root": str(external_root / "appworld"),
            "clean_manifest": str(external_root / "frozen" / "clean-manifest.json"),
            "cases": str(external_root / "frozen" / "cases.json"),
            "overlays": str(external_root / "frozen" / "overlays.json"),
            "dependency_lockfiles": [
                str(external_root / "locks" / "appworld.lock"),
                str(external_root / "locks" / "model-service.lock"),
            ],
            "output_root": str(external_root / "runs"),
            "phase_timeout_seconds": 1800,
            "model_request_timeout_seconds": 300,
            "evaluate_every_completed_cases": 1,
            "resume": True,
        },
        "model_service": {
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key_env": "R2SP_MODEL_API_KEY",
        },
        "logging": {
            "level": "INFO",
            "jsonl": True,
            "include_protected_document_bodies": False,
            "include_model_reasoning": False,
        },
    }


class CliTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_validate_config_reports_v04_execution_ready(self) -> None:
        status, stdout, stderr = self.invoke(
            "validate-config",
            "--config",
            str(ROOT / "configs/experiment_plan.yaml"),
        )
        payload = json.loads(stdout)

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(payload["design_valid"])
        self.assertTrue(payload["execution_ready"])
        self.assertFalse(payload["research_eligible"])
        self.assertFalse(payload["research_ready"])

    def test_model_gateway_cli_builds_the_frozen_declaration_profile(self) -> None:
        with patch("r2sp.model_gateway.serve_model_gateway") as serve:
            status, _, stderr = self.invoke(
                "serve-model-gateway",
                "--config",
                str(ROOT / "configs/experiment_plan.yaml"),
                "--backend-url",
                "http://127.0.0.1:18001",
            )

        self.assertEqual(status, 0, stderr)
        arguments = serve.call_args.kwargs
        self.assertEqual(arguments["host"], "127.0.0.1")
        self.assertEqual(arguments["port"], 18000)
        self.assertEqual(arguments["timeout_seconds"], 300.0)
        self.assertEqual(arguments["metadata"]["dtype"], "float16")
        self.assertEqual(arguments["metadata"]["gpu"], "2x_NVIDIA_Quadro_RTX_6000_24GB")
        self.assertEqual(arguments["metadata"]["runtime"]["tensor_parallel_size"], 2)
        self.assertEqual(
            arguments["metadata"]["evidence_scope"],
            "caller_declared_not_weight_or_process_proof",
        )

    def test_model_probe_cli_preserves_nonresearch_evidence_grade(self) -> None:
        report = ModelProbeReport((ModelProbeCheck("probe", True, "ok"),))
        with patch(
            "r2sp.model_probe.run_model_service_probe",
            return_value=report,
        ) as run_probe:
            status, stdout, stderr = self.invoke("probe-model-service")

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ready"])
        self.assertFalse(payload["research_eligible"])
        arguments = run_probe.call_args.kwargs
        self.assertEqual(arguments["model_id"], "Qwen/Qwen3.8-27B-FP8")
        self.assertEqual(
            arguments["revision"],
            "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",
        )
        self.assertEqual(arguments["max_model_len"], 32768)

    def test_model_smoke_cli_forwards_explicit_loopback_profile(self) -> None:
        result = SimpleNamespace(
            cached=False,
            complete_hash="a" * 64,
            output_directory=Path("/tmp/model-smoke"),
            summary={
                "decision": "NOT_ELIGIBLE",
                "mode": "synthetic_model_smoke",
                "research_eligible": False,
            },
        )
        with (
            patch.dict("os.environ", {"R2SP_TEST_MODEL_KEY": "explicit-key"}),
            patch("r2sp.runner.run_model_backed_synthetic", return_value=result) as run,
        ):
            status, stdout, stderr = self.invoke(
                "run-model-smoke",
                "--output",
                "/tmp/model-smoke",
                "--base-url",
                "http://127.0.0.1:18000/v1",
                "--api-key-env",
                "R2SP_TEST_MODEL_KEY",
                "--max-model-len",
                "65536",
            )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["mode"], "synthetic_model_smoke")
        self.assertFalse(payload["research_eligible"])
        arguments = run.call_args.kwargs
        self.assertEqual(arguments["api_key"], "explicit-key")
        self.assertEqual(arguments["max_model_len"], 65536)
        self.assertEqual(arguments["max_agent_turns"], 16)
        self.assertEqual(arguments["base_url"], "http://127.0.0.1:18000/v1")

    def test_preflight_runtime_config_uses_full_contract_and_preserves_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory)
            runtime_path = external / "runtime.yaml"
            runtime_path.write_text(
                yaml.safe_dump(runtime_payload(external), sort_keys=False),
                encoding="utf-8",
            )
            override_cases = external / "alternate" / "cases.json"
            with patch(
                "r2sp.cli.run_preflight",
                return_value=PreflightReport((), mode="research"),
            ) as mocked:
                status, _, stderr = self.invoke(
                    "preflight",
                    "--config",
                    str(ROOT / "configs/experiment_plan.yaml"),
                    "--runtime-config",
                    str(runtime_path),
                    "--project-root",
                    str(ROOT),
                    "--cases",
                    str(override_cases),
                    "--json",
                )

            self.assertEqual(status, 0, stderr)
            arguments = mocked.call_args.kwargs
            self.assertEqual(arguments["cases_path"], override_cases)
            self.assertEqual(
                arguments["clean_manifest"],
                external / "frozen" / "clean-manifest.json",
            )
            self.assertEqual(
                arguments["dependency_lockfiles"],
                (
                    external / "locks" / "appworld.lock",
                    external / "locks" / "model-service.lock",
                ),
            )
            self.assertEqual(arguments["model_url"], "http://127.0.0.1:8000/v1")
            self.assertEqual(arguments["model_api_key_env"], "R2SP_MODEL_API_KEY")

    def test_preflight_rejects_invalid_runtime_contract_before_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory)
            runtime_path = external / "runtime.yaml"
            invalid_variants = (
                (("runtime", "resume"), False, "runtime.resume must be true"),
                (
                    ("logging", "include_model_reasoning"),
                    True,
                    "model reasoning cannot be persisted",
                ),
                (
                    ("runtime", "output_root"),
                    "runs",
                    "runtime.output_root must be an absolute path",
                ),
            )
            for (section, key), value, expected_error in invalid_variants:
                with self.subTest(section=section, key=key):
                    payload = runtime_payload(external)
                    payload[section][key] = value
                    runtime_path.write_text(
                        yaml.safe_dump(payload, sort_keys=False),
                        encoding="utf-8",
                    )
                    with patch("r2sp.cli.run_preflight") as mocked:
                        status, stdout, stderr = self.invoke(
                            "preflight",
                            "--config",
                            str(ROOT / "configs/experiment_plan.yaml"),
                            "--runtime-config",
                            str(runtime_path),
                            "--project-root",
                            str(ROOT),
                        )
                    self.assertEqual(status, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(expected_error, stderr)
                    mocked.assert_not_called()

    def test_build_manifest_and_freeze_instrumentation_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "notes.json").write_text(
                json.dumps(
                    {
                        "add": {
                            "title": "Add note",
                            "body": "Add one local note.",
                        }
                    }
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            status, stdout, _ = self.invoke(
                "build-manifest",
                "--source",
                str(docs),
                "--output",
                str(manifest),
                "--expected-count",
                "1",
            )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(stdout)["resource_count"], 1)
            self.assertNotIn("Add one local note", manifest.read_text(encoding="utf-8"))

            cases = root / "cases.json"
            cases.write_text(json.dumps(bundle_payload(2)), encoding="utf-8")
            schedule = root / "schedule.json"
            status, stdout, _ = self.invoke(
                "freeze-pilot",
                "--cases",
                str(cases),
                "--output",
                str(schedule),
                "--instrumentation",
            )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(stdout)["entry_count"], 4)
            serialized = schedule.read_text(encoding="utf-8")
            self.assertNotIn("nonce-", serialized)
            self.assertNotIn("Harmless matched body", serialized)

    def test_smoke_and_report_commands_verify_completed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            status, stdout, stderr = self.invoke(
                "smoke",
                "--output",
                str(output),
                "--config",
                str(ROOT / "configs/experiment_plan.yaml"),
                "--project-root",
                str(ROOT),
            )
            result = json.loads(stdout)
            self.assertEqual(status, 0, stderr)
            self.assertFalse(result["research_eligible"])
            self.assertEqual(result["decision"], "NOT_ELIGIBLE")

            status, report, stderr = self.invoke(
                "report",
                "--run-directory",
                str(output),
                "--format",
                "json",
                "--expected-complete-sha256",
                result["complete_hash"],
            )
            self.assertEqual(status, 0, stderr)
            self.assertEqual(json.loads(report)["decision"], "NOT_ELIGIBLE")

            for report_format, relative_path in (
                ("json", "reports/summary.json"),
                ("markdown", "reports/summary.md"),
                ("csv", "reports/funnel.csv"),
            ):
                report_path = output / relative_path
                original = report_path.read_text(encoding="utf-8")
                report_path.write_text("tampered\n", encoding="utf-8")
                status, _, stderr = self.invoke(
                    "report",
                    "--run-directory",
                    str(output),
                    "--format",
                    report_format,
                    "--expected-complete-sha256",
                    result["complete_hash"],
                )
                self.assertEqual(status, 2)
                self.assertRegex(stderr, "digest|manifest verification")
                report_path.write_text(original, encoding="utf-8")

    def test_report_verifies_research_artifact_manifest_for_every_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "research"
            store = ArtifactStore(output)
            reports = {
                "reports/summary.json": "{}\n",
                "reports/summary.md": "# Summary\n",
                "reports/funnel.csv": "metric,value\n",
            }
            run_record = store.write_json("run.json", {"mode": "research"})
            records = [
                run_record,
                *(store.write_text(path, body) for path, body in reports.items()),
            ]
            manifest = store.write_json(
                "artifacts-manifest.json",
                {
                    "schema_version": 1,
                    "artifact_count": len(records),
                    "artifacts": [
                        {
                            "path": record.relative_path,
                            "sha256": record.sha256,
                            "size_bytes": record.size_bytes,
                        }
                        for record in records
                    ],
                },
            )
            completion = store.write_json(
                "complete.json",
                {
                    "status": "completed",
                    "mode": "research",
                    "summary_hash": records[1].sha256,
                    "artifact_manifest_hash": manifest.sha256,
                },
            )

            for report_format in ("json", "markdown", "csv"):
                status, _, stderr = self.invoke(
                    "report",
                    "--run-directory",
                    str(output),
                    "--format",
                    report_format,
                    "--expected-complete-sha256",
                    completion.sha256,
                )
                self.assertEqual(status, 0, stderr)

            markdown = output / "reports/summary.md"
            markdown.write_text("tampered\n", encoding="utf-8")
            status, _, stderr = self.invoke(
                "report",
                "--run-directory",
                str(output),
                "--format",
                "csv",
                "--expected-complete-sha256",
                completion.sha256,
            )
            self.assertEqual(status, 2)
            self.assertIn("manifest verification failed", stderr)
            self.assertNotEqual(sha256_file(markdown), records[2].sha256)

    def test_research_report_cannot_downgrade_to_per_file_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "research"
            store = ArtifactStore(output)
            store.write_json("run.json", {"mode": "research"})
            summary = store.write_text("reports/summary.json", "{}\n")
            store.write_text("reports/summary.md", "# Summary\n")
            store.write_text("reports/funnel.csv", "metric,value\n")
            completion = store.write_json(
                "complete.json",
                {
                    "status": "completed",
                    "mode": "research",
                    "summary_hash": summary.sha256,
                },
            )

            status, _, stderr = self.invoke(
                "report",
                "--run-directory",
                str(output),
                "--format",
                "json",
                "--expected-complete-sha256",
                completion.sha256,
            )
            self.assertEqual(status, 2)
            self.assertIn("requires a complete artifact manifest", stderr)

            rewritten = json.loads((output / "complete.json").read_text(encoding="utf-8"))
            rewritten["mode"] = "synthetic_smoke"
            (output / "complete.json").write_text(
                json.dumps(rewritten, sort_keys=True) + "\n", encoding="utf-8"
            )
            status, _, stderr = self.invoke(
                "report",
                "--run-directory",
                str(output),
                "--format",
                "json",
                "--expected-complete-sha256",
                completion.sha256,
            )
            self.assertEqual(status, 2)
            self.assertIn("external expected digest", stderr)


if __name__ == "__main__":
    unittest.main()
