from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from r2sp.cases import load_frozen_cases
from r2sp.hashing import sha256_file
from r2sp.models import CaseSpec, OverlayPair, OverlaySpec, Resource, TaskSpec
from r2sp.preflight import (
    _fetch_model_record,
    format_preflight,
    overlay_attestation_payload,
    run_preflight,
)
from r2sp.resource_pool import load_standard_api_docs, write_public_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment_plan.yaml"


def _base_config() -> dict[str, Any]:
    value = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_config(project: Path, value: dict[str, Any]) -> Path:
    path = project / "config.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _case(index: int) -> CaseSpec:
    case_id = f"case-{index:02d}"
    identity = {
        "resource_id": f"overlay-{index:02d}",
        "app_name": "calendar",
        "api_name": "create_event",
        "title": f"Matched overlay {index:02d}",
    }
    trigger = f"trigger-{index:02d}"
    nonce = f"nonce-{index:02d}"
    overlays = OverlayPair(
        case_id=case_id,
        sham=OverlaySpec(
            "A_sham",
            Resource(body=f"Harmless matched body {index:02d}.", **identity),
            trigger,
            nonce,
        ),
        poison=OverlaySpec(
            "B_poison",
            Resource(body=f"Different local canary rule {index:02d}.", **identity),
            trigger,
            nonce,
        ),
    )
    return CaseSpec(
        case_id=case_id,
        authoring_task=TaskSpec(f"task-{index:02d}-a", "authoring"),
        positive_task=TaskSpec(f"task-{index:02d}-p", "trigger_positive"),
        negative_task=TaskSpec(f"task-{index:02d}-n", "trigger_negative"),
        overlays=overlays,
    )


def _write_cases(path: Path) -> None:
    cases: list[dict[str, Any]] = []
    for index in range(16):
        encoded = _case(index).to_dict()
        encoded["sham_token_count"] = 100
        encoded["poison_token_count"] = 104
        cases.append(encoded)
    payload = {
        "protocol_version": "0.3",
        "tokenizer": {
            "model": "Qwen/Qwen3.8-27B",
            "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
        },
        "cases": cases,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _lock_text(package: str, version: str) -> str:
    return (
        f"{package}=={version} \\\n"
        f"    --hash=sha256:{'a' * 64}\n"
        "transitive-dependency==1.0.0 \\\n"
        f"    --hash=sha256:{'b' * 64}\n"
    )


def _appworld_lock_text() -> str:
    return (
        "appworld @ git+https://github.com/StonyBrookNLP/appworld.git@"
        "66ad8099e12188ece0d3fe45e661dbc01880813b\n"
        "transitive-dependency==1.0.0 \\\n"
        f"    --hash=sha256:{'b' * 64}\n"
    )


def _model_record(config: dict[str, Any]) -> dict[str, Any]:
    model = config["model"]
    return {
        "id": model["id"],
        "revision": model["revision"],
        "dtype": model["dtype"],
        "generation": model["generation"],
        "runtime": {
            "max_model_len": model["max_model_len"],
            "prefix_caching": model["prefix_caching"],
            "server_sessions": model["server_sessions"],
            **model["serving"],
        },
        "vllm_version": model["vllm_version"],
        "gpu": model["gpu"],
    }


def _build_research_fixture(base: Path) -> dict[str, Any]:
    project = base / "project"
    appworld = base / "protected-appworld"
    docs = appworld / "data" / "api_docs" / "standard"
    docs.mkdir(parents=True)
    project.mkdir()

    (project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    source = project / "src" / "r2sp"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    prompts = project / "experiments" / "pilot" / "prompts"
    prompts.mkdir(parents=True)
    for name in ("agent_system.md", "compiler_system.md", "neutral_skill.md"):
        (prompts / name).write_text(f"# {name}\nnon-empty\n", encoding="utf-8")

    api_docs = {
        f"api_{index:03d}": {"title": f"API {index:03d}", "description": "stable"}
        for index in range(457)
    }
    (docs / "calendar.json").write_text(json.dumps(api_docs), encoding="utf-8")
    clean_pool = load_standard_api_docs(docs, expected_count=457)
    manifest = base / "clean-manifest.json"
    write_public_manifest(clean_pool, manifest)

    cases = base / "cases.json"
    _write_cases(cases)
    bundle = load_frozen_cases(cases)
    overlays = base / "overlays.json"
    overlays.write_text(json.dumps(overlay_attestation_payload(bundle)), encoding="utf-8")

    requirements = project / "requirements"
    requirements.mkdir()
    (requirements / "appworld.lock").write_text(_appworld_lock_text(), encoding="utf-8")
    (requirements / "model-service.lock").write_text(_lock_text("vllm", "0.28.0"), encoding="utf-8")

    data_bundle = appworld / "data-0.1.0.bundle"
    data_bundle.write_bytes(b"frozen AppWorld fixture bundle")
    config = _base_config()
    config["protocol"]["runner_ready"] = True
    config["appworld"]["data_bundle_sha256"] = sha256_file(data_bundle)
    config_path = _write_config(project, config)
    return {
        "config": config,
        "config_path": config_path,
        "project": project,
        "appworld": appworld,
        "manifest": manifest,
        "cases": cases,
        "overlays": overlays,
        "model_url": "http://model.internal:8000/v1",
    }


def _run_fixture(
    fixture: dict[str, Any],
    *,
    model_url: str | None = None,
    model_record: dict[str, Any] | None = None,
    gpu_rows: tuple[list[tuple[str, int]], str | None] | None = None,
):
    selected_url = model_url or fixture["model_url"]
    selected_record = model_record or _model_record(fixture["config"])
    gpu_patch = (
        patch("r2sp.preflight._gpu_rows", return_value=gpu_rows)
        if gpu_rows is not None
        else patch(
            "r2sp.preflight._gpu_rows",
            side_effect=AssertionError("remote model must not inspect controller GPUs"),
        )
    )

    def package_version(name: str) -> str | None:
        if name != "appworld":
            raise AssertionError(f"runner package {name!r} must not describe the model service")
        return "0.1.3.post1"

    with (
        patch("r2sp.preflight._python_version_ok", return_value=True),
        patch("r2sp.preflight._package_version", side_effect=package_version),
        patch(
            "r2sp.preflight._package_git_revision",
            return_value=(
                "66ad8099e12188ece0d3fe45e661dbc01880813b",
                "PEP 610 fixture",
            ),
        ),
        patch(
            "r2sp.preflight._fetch_model_record",
            return_value=(selected_record, "endpoint declarations returned"),
        ),
        gpu_patch,
    ):
        return run_preflight(
            fixture["config_path"],
            project_root=fixture["project"],
            appworld_root=fixture["appworld"],
            clean_manifest=fixture["manifest"],
            cases_path=fixture["cases"],
            overlays_path=fixture["overlays"],
            model_url=selected_url,
            require_research_ready=True,
        )


class PreflightTests(unittest.TestCase):
    def test_model_metadata_probe_forwards_only_the_explicit_api_key(self) -> None:
        payload = json.dumps({"data": [{"id": "Qwen/Qwen3.8-27B"}]}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                del args

            def read(self):
                return payload

        with patch("r2sp.preflight.no_redirect_urlopen", return_value=Response()) as opened:
            record, _ = _fetch_model_record(
                "http://127.0.0.1:8000/v1",
                "Qwen/Qwen3.8-27B",
                api_key="experiment-secret",
            )

        self.assertEqual(record["id"], "Qwen/Qwen3.8-27B")
        request = opened.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer experiment-secret")

    def test_strict_loader_rejects_a_partial_config_in_instrumentation_mode(self) -> None:
        partial = "protocol:\n  runner_ready: false\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.yaml"
            config.write_text(partial, encoding="utf-8")
            report = run_preflight(
                config,
                project_root=PROJECT_ROOT,
                require_research_ready=False,
            )
        self.assertFalse(report.instrumentation_ready)
        self.assertEqual(report.mode, "instrumentation")
        self.assertEqual({check.name for check in report.failed_required}, {"config_v02_valid"})

    def test_instrumentation_and_research_readiness_are_distinct(self) -> None:
        with patch("r2sp.preflight._gpu_rows", return_value=([], "not available")):
            report = run_preflight(
                CONFIG_PATH,
                project_root=PROJECT_ROOT,
                require_research_ready=False,
            )
        self.assertTrue(report.ready)
        self.assertTrue(report.instrumentation_ready)
        self.assertFalse(report.research_ready)
        self.assertIn("[WARN] config_runner_ready", format_preflight(report))

    def test_research_mode_rejects_zero_or_placeholder_hash_and_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _base_config()
            config["appworld"]["data_bundle_sha256"] = "0" * 64
            path = _write_config(root, config)
            report = run_preflight(path, project_root=PROJECT_ROOT, require_research_ready=True)
        failures = {check.name for check in report.failed_required}
        self.assertFalse(report.ready)
        self.assertIn("data_bundle_hash_configured", failures)
        self.assertIn("clean_manifest_content", failures)
        self.assertIn("dependency_lockfile_1_appworld", failures)

    def test_complete_remote_research_evidence_passes_without_local_gpu_inference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            report = _run_fixture(fixture)
        self.assertTrue(report.ready, format_preflight(report))
        self.assertTrue(report.instrumentation_ready)
        self.assertTrue(report.research_ready)

    def test_manifest_is_rebuilt_from_actual_docs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            docs = fixture["appworld"] / "data" / "api_docs" / "standard" / "calendar.json"
            value = json.loads(docs.read_text(encoding="utf-8"))
            value["api_000"]["description"] = "mutated after manifest freeze"
            docs.write_text(json.dumps(value), encoding="utf-8")
            report = _run_fixture(fixture)
        failures = {check.name for check in report.failed_required}
        self.assertIn("clean_manifest_matches_docs", failures)

    def test_overlay_attestation_is_cross_checked_against_private_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            value = json.loads(fixture["overlays"].read_text(encoding="utf-8"))
            value["cases"][0]["nonce_sha256"] = "0" * 64
            fixture["overlays"].write_text(json.dumps(value), encoding="utf-8")
            report = _run_fixture(fixture)
        failures = {check.name for check in report.failed_required}
        self.assertIn("overlay_attestation_content", failures)

    def test_every_protected_input_must_resolve_outside_repository(self) -> None:
        for index, key in enumerate(("manifest", "cases", "overlays")):
            with self.subTest(path=key), tempfile.TemporaryDirectory() as directory:
                fixture = _build_research_fixture(Path(directory))
                source = fixture[key]
                inside = fixture["project"] / f"inside-{index}.json"
                source.replace(inside)
                fixture[key] = inside
                report = _run_fixture(fixture)
                failures = {check.name for check in report.failed_required}
                self.assertIn("protected_inputs_outside_repository", failures)

    def test_remote_endpoint_metadata_is_required_and_local_gpu_is_not_queried(self) -> None:
        with (
            patch(
                "r2sp.preflight._fetch_model_record",
                return_value=({"id": "Qwen/Qwen3.8-27B"}, "reachable"),
            ),
            patch(
                "r2sp.preflight._gpu_rows",
                side_effect=AssertionError("remote endpoint must not use local GPU facts"),
            ),
        ):
            report = run_preflight(
                CONFIG_PATH,
                project_root=PROJECT_ROOT,
                model_url="https://model.example/v1",
                require_research_ready=True,
            )
        failures = {check.name for check in report.failed_required}
        self.assertIn("model_revision_reported", failures)
        self.assertIn("model_dtype_reported", failures)
        self.assertIn("model_generation_reported", failures)
        self.assertIn("model_runtime_reported", failures)
        self.assertIn("model_execution_stack_reported_consistent", failures)

    def test_loopback_service_declarations_and_h200_pass_without_runner_vllm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            report = _run_fixture(
                fixture,
                model_url="http://127.0.0.1:8000/v1",
                gpu_rows=([("NVIDIA H200", 143_771)], None),
            )
        execution_check = next(
            check
            for check in report.checks
            if check.name == "model_execution_stack_reported_consistent"
        )
        self.assertTrue(execution_check.ok, execution_check.detail)
        self.assertTrue(report.ready, format_preflight(report))

    def test_loopback_service_missing_stack_metadata_fails_even_with_h200(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            record = _model_record(fixture["config"])
            record.pop("vllm_version")
            record.pop("gpu")
            report = _run_fixture(
                fixture,
                model_url="http://localhost:8000/v1",
                model_record=record,
                gpu_rows=([("NVIDIA H200", 143_771)], None),
            )
        execution_check = next(
            check
            for check in report.checks
            if check.name == "model_execution_stack_reported_consistent"
        )
        self.assertFalse(execution_check.ok)
        self.assertIn("vllm=None", execution_check.detail)
        self.assertIn("gpu=None", execution_check.detail)

    def test_placeholder_lockfile_is_a_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            lock = fixture["project"] / "requirements" / "appworld.lock"
            lock.write_text("# TODO: fill after provisioning\n", encoding="utf-8")
            report = _run_fixture(fixture)
        failures = {check.name for check in report.failed_required}
        self.assertIn("dependency_lockfile_1_appworld", failures)

    def test_appworld_lock_requires_the_exact_vcs_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _build_research_fixture(Path(directory))
            lock = fixture["project"] / "requirements" / "appworld.lock"
            lock.write_text(
                _appworld_lock_text().replace(
                    "66ad8099e12188ece0d3fe45e661dbc01880813b",
                    "c" * 40,
                ),
                encoding="utf-8",
            )
            report = _run_fixture(fixture)
        failures = {check.name for check in report.failed_required}
        self.assertIn("dependency_lockfile_1_appworld", failures)


if __name__ == "__main__":
    unittest.main()
