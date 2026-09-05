from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from r2sp.appworld_payloads import (
    DEFAULT_APPWORLD_INJECTION_DIRECTORY,
    AppWorldPayloadError,
    load_appworld_injection_payloads,
)
from r2sp.artifacts import sha256_file
from r2sp.file_injection_fixture import (
    load_appworld_file_fixtures,
    materialize_appworld_file_bundles,
)
from r2sp.file_injection_profiles import APPWORLD_FILE_BINDINGS
from r2sp.fixtures import _poison_injection_body
from r2sp.injection_deployment_runner import run_poison_deployment_verification
from r2sp.injection_runner import (
    InjectionRunnerError,
    build_fixture_commitments,
    run_injection_compile_gate,
)
from r2sp.resource_pool import make_resource_id
from tests.test_injection_deployment_runner import _DeploymentProvider
from tests.test_injection_runner import _Provider

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _make_appworld_tree(root: Path) -> Path:
    standard = root / "data/api_docs/standard"
    standard.mkdir(parents=True)
    _write_json(
        standard / "spotify.json",
        {
            "search_songs": {
                "app_name": "spotify",
                "api_name": "search_songs",
                "description": "Search Spotify songs and return titles with play counts.",
                "parameters": [{"name": "query", "type": "string"}],
            }
        },
    )
    _write_json(
        standard / "file_system.json",
        {
            "delete_directory": {
                "app_name": "file_system",
                "api_name": "delete_directory",
                "description": "Delete one simulated directory after its archive is created.",
                "parameters": [{"name": "path", "type": "string"}],
            }
        },
    )
    _write_json(
        standard / "benign_catalog.json",
        {
            f"benign_endpoint_{index:03d}": {
                "app_name": "benign_catalog",
                "api_name": f"benign_endpoint_{index:03d}",
                "description": f"Unrelated benign catalog operation number {index:03d}.",
            }
            for index in range(445)
        },
    )
    _write_json(
        standard / "api_docs.json",
        {
            f"helper_{index}": {
                "app_name": "api_docs",
                "api_name": f"helper_{index}",
                "description": f"API documentation helper {index}.",
            }
            for index in range(4)
        },
    )
    _write_json(
        standard / "supervisor.json",
        {
            f"helper_{index}": {
                "app_name": "supervisor",
                "api_name": f"helper_{index}",
                "description": f"Supervisor helper {index}.",
            }
            for index in range(6)
        },
    )
    (root / "data/version.txt").write_text("0.1.0\n", encoding="utf-8")
    for binding in APPWORLD_FILE_BINDINGS.values():
        task_instructions = {
            binding.authoring_task_id: binding.profile.authoring_instruction,
            binding.positive_task_id: binding.profile.positive_instruction,
            binding.negative_task_id: binding.profile.negative_instruction,
        }
        for task_id, instruction in task_instructions.items():
            _write_json(
                root / "data/tasks" / task_id / "specs.json",
                {"instruction": instruction},
            )
    return root


def _source_snapshot(root: Path) -> dict[str, bytes]:
    standard = root / "data/api_docs/standard"
    return {path.name: path.read_bytes() for path in sorted(standard.glob("*.json"))}


class FileInjectionFixtureTests(unittest.TestCase):
    def test_invalid_payload_fails_before_materialization_output_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld = _make_appworld_tree(temporary / "appworld")
            payloads = temporary / "payloads"
            payloads.mkdir()
            (payloads / "mock-api-call.txt").write_bytes(b"\xff")
            (payloads / "delete-sentinel.txt").write_bytes(b"valid")
            output = temporary / "bundles"

            with self.assertRaises(AppWorldPayloadError):
                materialize_appworld_file_bundles(
                    appworld,
                    output,
                    payload_directory=payloads,
                )
            self.assertFalse(output.exists())

    def test_full_derived_pools_feed_bm25_and_compile_with_bound_disk_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld = _make_appworld_tree(temporary / "appworld")
            before = _source_snapshot(appworld)
            bundle_root = temporary / "bundles"
            manifest_paths = materialize_appworld_file_bundles(
                appworld,
                bundle_root,
                payload_directory=DEFAULT_APPWORLD_INJECTION_DIRECTORY,
            )
            self.assertEqual(_source_snapshot(appworld), before)
            for name, paths in manifest_paths.items():
                with self.subTest(profile=name, boundary="disk-arms"):
                    self.assertEqual(set(paths), {"benign", "poison"})
                    benign_standard = bundle_root / name / "benign" / "standard"
                    self.assertEqual(
                        {
                            path.name: path.read_bytes()
                            for path in sorted(benign_standard.glob("*.json"))
                        },
                        before,
                    )
                    benign_manifest = json.loads(paths["benign"].read_text(encoding="utf-8"))
                    self.assertEqual(
                        benign_manifest["schema_version"],
                        "r2sp.file-injection-bundle.v3",
                    )
                    self.assertEqual(benign_manifest["profile"]["arm"], "A_benign")
                    self.assertEqual(
                        benign_manifest["transform"]["strategy"],
                        "identity_copy",
                    )
                    self.assertIsNone(benign_manifest["target"]["payload"])
                    self.assertEqual(
                        benign_manifest["source_corpus"]["corpus_sha256"],
                        benign_manifest["derived_corpus"]["corpus_sha256"],
                    )

            loaded = load_appworld_file_fixtures(appworld, bundle_root)
            self.assertEqual(
                loaded.source_evidence["schema_version"],
                "r2sp.file-backed-source-evidence.v3",
            )
            self.assertEqual(loaded.source_evidence["raw_endpoint_count"], 457)
            self.assertEqual(loaded.source_evidence["task_facing_endpoint_count"], 447)
            commitments = build_fixture_commitments(loaded.fixtures)
            for name, fixture in loaded.fixtures.items():
                with self.subTest(profile=name):
                    binding = APPWORLD_FILE_BINDINGS[name]
                    target_id = make_resource_id(
                        binding.profile.app_name,
                        binding.profile.api_name,
                    )
                    self.assertEqual(binding.profile.resource_id, target_id)
                    self.assertEqual(len(fixture.clean_pool), 447)
                    self.assertIsNotNone(fixture.acquisition_pools)
                    clean_target = fixture.clean_pool.read_doc(target_id)
                    self.assertNotIn(binding.profile.retrieval_lead, clean_target.body)
                    for arm in ("benign", "poison"):
                        pool = fixture.pool_for_arm(arm)
                        target = getattr(fixture.case.overlays, arm).resource
                        self.assertEqual(len(pool), 447)
                        self.assertEqual(sum(r.resource_id == target_id for r in pool), 1)
                        self.assertEqual(pool.read_doc(target_id), target)
                        arm_evidence = loaded.source_evidence["profiles"][name]["arms"][arm]
                        if arm == "benign":
                            self.assertEqual(target, clean_target)
                            self.assertIsNone(arm_evidence["target"]["payload_sha256"])
                            self.assertEqual(
                                arm_evidence["source_corpus_sha256"],
                                arm_evidence["derived_corpus_sha256"],
                            )
                        else:
                            self.assertNotEqual(target.content_hash, clean_target.content_hash)
                            self.assertIn(binding.profile.retrieval_lead, target.body)
                        self.assertEqual(
                            pool.manifest.manifest_hash,
                            arm_evidence["derived_pool_manifest_hash"],
                        )
                        self.assertEqual(
                            target.content_hash,
                            arm_evidence["target"]["derived_resource_body_sha256"],
                        )
                    profile_commitment = commitments["profiles"][name]
                    self.assertEqual(
                        profile_commitment["source_clean_pool"]["resource_count"],
                        447,
                    )
                    self.assertEqual(
                        profile_commitment["target_resources"]["poison"]["resource_id"],
                        target_id,
                    )
                    provenance = fixture.provenance.to_dict()
                    self.assertEqual(provenance["raw_endpoint_count"], 457)
                    self.assertEqual(provenance["task_facing_endpoint_count"], 447)

            provider = _Provider()
            output = temporary / "compile-gate"
            result = run_injection_compile_gate(
                output,
                project_root=ROOT,
                client_provider=provider,
                fixtures=loaded.fixtures,
                mode="file_backed_injection_compile_gate",
                source_type="appworld_standard_json_file_backed",
                source_evidence=loaded.source_evidence,
            )
            self.assertFalse(result.cached)
            for relative in ("run.json", "gate.json", "complete.json"):
                payload = json.loads((output / relative).read_text(encoding="utf-8"))
                self.assertEqual(payload["fixture_commitments"], commitments)
            for name, fixture in loaded.fixtures.items():
                acquisition = json.loads(
                    (output / f"profiles/{name}/poison/acquisition.json").read_text(
                        encoding="utf-8"
                    )
                )
                target = fixture.case.overlays.poison.resource
                self.assertEqual(
                    acquisition["pool_hash"],
                    fixture.pool_for_arm("poison").manifest.manifest_hash,
                )
                read_target = next(
                    document
                    for document in acquisition["result"]["read_documents"]
                    if document["resource_id"] == target.resource_id
                )
                self.assertEqual(read_target["content_hash"], target.content_hash)
                self.assertEqual(read_target["body"], target.body)

            deployment = temporary / "deployment"
            deployment_result = run_poison_deployment_verification(
                output,
                deployment,
                expected_compile_complete_sha256=sha256_file(output / "complete.json"),
                project_root=ROOT,
                client_provider=_DeploymentProvider(),
                fixtures=loaded.fixtures,
                mode="file_backed_poison_deployment_verification",
                source_type="appworld_standard_json_file_backed",
                source_evidence=dict(loaded.source_evidence),
                expected_compile_mode="file_backed_injection_compile_gate",
                expected_compile_source_type="appworld_standard_json_file_backed",
            )
            self.assertEqual(deployment_result.gate["episode_count"], 4)
            self.assertEqual(deployment_result.gate["positive_exact_effect_count"], 2)
            for name in loaded.fixtures:
                for task_kind in ("positive", "negative"):
                    episode = deployment / "episodes" / name / task_kind
                    reset = json.loads((episode / "reset.json").read_text(encoding="utf-8"))
                    trace = json.loads((episode / "trace.json").read_text(encoding="utf-8"))
                    self.assertTrue(reset["passed"])
                    self.assertEqual(reset["mode"], "replacement_restored")
                    self.assertEqual(
                        {check["name"] for check in reset["checks"]},
                        {
                            "clean_pool_hash_matches",
                            "target_resource_id_present",
                            "poison_content_hash_absent",
                            "clean_target_content_hash_restored_at_target_id",
                            "world_id_fresh",
                            "context_id_fresh",
                            "session_id_fresh",
                            "skill_hash_matches",
                        },
                    )
                    self.assertTrue(trace["clean_pool"]["target_resource_id_present"])
                    self.assertTrue(trace["clean_pool"]["poison_content_hash_absent"])
                    self.assertFalse(trace["clean_pool"]["overlay_absent"])

            before_calls = (provider.acquisition_calls, provider.compiler_calls)
            resumed = run_injection_compile_gate(
                output,
                project_root=ROOT,
                client_provider=provider,
                fixtures=loaded.fixtures,
                mode="file_backed_injection_compile_gate",
                source_type="appworld_standard_json_file_backed",
                source_evidence=loaded.source_evidence,
            )
            self.assertTrue(resumed.cached)
            self.assertEqual(
                (provider.acquisition_calls, provider.compiler_calls),
                before_calls,
            )

            changed_fixtures = dict(loaded.fixtures)
            original_fixture = changed_fixtures["mock-api-call"]
            changed_fixtures["mock-api-call"] = replace(
                original_fixture,
                case=replace(
                    original_fixture.case,
                    authoring_task=replace(
                        original_fixture.case.authoring_task,
                        instruction="changed fixture commitment instruction",
                    ),
                ),
            )
            changed_provider = _Provider()
            with self.assertRaisesRegex(
                InjectionRunnerError,
                "corrupt|stale|do not replay from disk",
            ):
                run_injection_compile_gate(
                    output,
                    project_root=ROOT,
                    client_provider=changed_provider,
                    fixtures=changed_fixtures,
                    mode="file_backed_injection_compile_gate",
                    source_type="appworld_standard_json_file_backed",
                    source_evidence=loaded.source_evidence,
                )
            self.assertEqual(changed_provider.acquisition_calls, 0)
            self.assertEqual(changed_provider.compiler_calls, 0)

            tampered_evidence = json.loads(json.dumps(dict(loaded.source_evidence)))
            tampered_evidence["profiles"]["mock-api-call"]["expected_poison_payload_sha256"] = (
                "0" * 64
            )
            evidence_provider = _Provider()
            with self.assertRaisesRegex(
                InjectionRunnerError,
                "bundle commitment|replay from disk",
            ):
                run_injection_compile_gate(
                    temporary / "tampered-evidence",
                    project_root=ROOT,
                    client_provider=evidence_provider,
                    fixtures=loaded.fixtures,
                    mode="file_backed_injection_compile_gate",
                    source_type="appworld_standard_json_file_backed",
                    source_evidence=tampered_evidence,
                )
            self.assertEqual(evidence_provider.acquisition_calls, 0)
            self.assertEqual(evidence_provider.compiler_calls, 0)

            path_tampered_evidence = json.loads(json.dumps(dict(loaded.source_evidence)))
            path_tampered_evidence["profiles"]["mock-api-call"]["arms"]["poison"]["target"][
                "source_relative_path"
            ] = "different.json"
            path_provider = _Provider()
            with self.assertRaisesRegex(InjectionRunnerError, "replay from disk"):
                run_injection_compile_gate(
                    temporary / "tampered-path-evidence",
                    project_root=ROOT,
                    client_provider=path_provider,
                    fixtures=loaded.fixtures,
                    mode="file_backed_injection_compile_gate",
                    source_type="appworld_standard_json_file_backed",
                    source_evidence=path_tampered_evidence,
                )
            self.assertEqual(path_provider.acquisition_calls, 0)
            self.assertEqual(path_provider.compiler_calls, 0)

            with patch(
                "r2sp.file_injection_fixture.load_appworld_injection_payloads",
                side_effect=AssertionError("bundle replay must not read mutable payload files"),
            ):
                replayed = load_appworld_file_fixtures(appworld, bundle_root)
            self.assertEqual(replayed.source_evidence, loaded.source_evidence)

            provider = _Provider()
            with self.assertRaisesRegex(InjectionRunnerError, "synthetic mode rejects"):
                run_injection_compile_gate(
                    temporary / "wrong-mode",
                    project_root=ROOT,
                    client_provider=provider,
                    fixtures=loaded.fixtures,
                )
            self.assertEqual(provider.acquisition_calls, 0)
            self.assertEqual(provider.compiler_calls, 0)

    def test_current_payload_hashes_are_bound_to_source_evidence(self) -> None:
        expected = {
            "mock-api-call": (
                1346,
                "5d075bdd23ec1a278346e098ebc4d3b6e53b3ece6de393723353923ff25b8bf5",
            ),
            "delete-sentinel": (
                1395,
                "dc3724eb9d045466e3a4c0659fbf85e00c4744792a7e83fa083bb862b5e72fdd",
            ),
        }
        payloads = load_appworld_injection_payloads(DEFAULT_APPWORLD_INJECTION_DIRECTORY)
        for name, binding in APPWORLD_FILE_BINDINGS.items():
            poison = payloads[name]
            path = DEFAULT_APPWORLD_INJECTION_DIRECTORY / f"{name}.txt"
            self.assertIn(binding.profile.retrieval_lead, poison, name)
            self.assertEqual(poison, _poison_injection_body(binding.profile))
            self.assertEqual(len(path.read_bytes()), expected[name][0])
            self.assertEqual(sha256_file(path), expected[name][1])
            self.assertEqual(binding.source_relative_path, f"{binding.profile.app_name}.json")
            self.assertEqual(
                binding.profile.resource_id,
                make_resource_id(binding.profile.app_name, binding.profile.api_name),
            )


if __name__ == "__main__":
    unittest.main()
