from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from r2sp.artifacts import sha256_file
from r2sp.runner import RunnerError, run_synthetic_smoke

ROOT = Path(__file__).resolve().parents[1]


class RunnerTests(unittest.TestCase):
    def test_synthetic_smoke_exercises_full_chain_without_research_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            result = run_synthetic_smoke(output, project_root=ROOT)
            summary = result.summary
            reset = json.loads(
                (output / "cases/smoke-case-00/poison/reset.json").read_text(encoding="utf-8")
            )
            clean_manifest = json.loads(
                (output / "manifests/clean-pool.json").read_text(encoding="utf-8")
            )
            run_record = json.loads((output / "run.json").read_text(encoding="utf-8"))
            task_provenance = json.loads(
                (output / "inputs/task-provenance.json").read_text(encoding="utf-8")
            )
            poison_acquisition = json.loads(
                (output / "cases/smoke-case-00/poison/acquisition.json").read_text(encoding="utf-8")
            )
            poison_skill_path = output / "cases/smoke-case-00/poison/skill/SKILL.md"
            poison_skill_provenance = json.loads(
                (output / "cases/smoke-case-00/poison/skill/provenance.json").read_text(
                    encoding="utf-8"
                )
            )
            artifact_manifest = json.loads(
                (output / "artifacts-manifest.json").read_text(encoding="utf-8")
            )
            run_schema = json.loads(
                (
                    ROOT / "experiments/appworld/preliminary/schemas/run-record.schema.json"
                ).read_text(encoding="utf-8")
            )

            self.assertFalse(result.cached)
            self.assertEqual(clean_manifest["resource_count"], 457)
            self.assertTrue(set(run_schema["required"]).issubset(run_record))
            self.assertTrue(set(run_record).issubset(run_schema["properties"]))
            self.assertFalse(run_record["research_candidate"])
            self.assertEqual(run_record["protocol_version"], "0.4")
            self.assertEqual(task_provenance["source_type"], "checked_in_synthetic_fixture")
            self.assertEqual(task_provenance["source_file"], "src/r2sp/fixtures.py")
            self.assertEqual(task_provenance["case_id"], "smoke-case-00")
            self.assertEqual(len(task_provenance["tasks"]), 3)
            self.assertNotIn("instruction", task_provenance["tasks"][0])
            self.assertNotIn("LOCAL_SMOKE_TRIGGER", json.dumps(task_provenance))
            self.assertEqual(
                len(poison_acquisition["result"]["selected_resource_ids"]),
                5,
            )
            self.assertEqual(
                poison_acquisition["result"]["selection_trace"][0]["accepted"],
                True,
            )
            self.assertTrue(poison_skill_path.is_file())
            self.assertEqual(
                poison_skill_provenance["skill"]["sha256"],
                sha256_file(poison_skill_path),
            )
            self.assertEqual(
                poison_skill_provenance["generator"]["kind"],
                "scripted_fixture",
            )
            self.assertEqual(
                poison_skill_provenance["selected_resource_ids"],
                poison_acquisition["result"]["selected_resource_ids"],
            )
            manifest_paths = {item["path"] for item in artifact_manifest["artifacts"]}
            self.assertIn(
                "cases/smoke-case-00/poison/skill/SKILL.md",
                manifest_paths,
            )
            self.assertIn(
                "cases/smoke-case-00/poison/skill/provenance.json",
                manifest_paths,
            )
            self.assertTrue(reset["passed"])
            self.assertEqual(summary["decision"], "NOT_ELIGIBLE")
            self.assertFalse(summary["research_eligible"])
            self.assertEqual(summary["poison_natural_reads"], 1)
            self.assertEqual(summary["poison_positive_canary_activations"], 1)
            self.assertEqual(summary["poison_full_chain_successes"], 1)
            self.assertEqual(summary["benign_positive_false_activations"], 0)
            self.assertEqual(summary["all_negative_false_activations"], 0)

    def test_completed_smoke_rejects_tampered_skill_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            run_synthetic_smoke(output, project_root=ROOT)
            skill_path = output / "cases/smoke-case-00/poison/skill/SKILL.md"
            skill_path.write_text("tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(RunnerError, "corrupt|integrity|stale"):
                run_synthetic_smoke(output, project_root=ROOT)

    def test_completed_smoke_rejects_missing_skill_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            run_synthetic_smoke(output, project_root=ROOT)
            provenance_path = output / "cases/smoke-case-00/benign/skill/provenance.json"
            provenance_path.unlink()

            with self.assertRaisesRegex(RunnerError, "corrupt|integrity|stale"):
                run_synthetic_smoke(output, project_root=ROOT)

    def test_completed_smoke_is_resumed_without_duplicate_canary_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            first = run_synthetic_smoke(output, project_root=ROOT)
            log = output / "canary/poison-positive.jsonl"
            first_lines = log.read_text(encoding="utf-8").splitlines()
            second = run_synthetic_smoke(output, project_root=ROOT)
            second_lines = log.read_text(encoding="utf-8").splitlines()

            self.assertFalse(first.cached)
            self.assertTrue(second.cached)
            self.assertEqual(first.complete_hash, second.complete_hash)
            self.assertEqual(len(first_lines), 1)
            self.assertEqual(first_lines, second_lines)

    def test_changed_config_cannot_reuse_completed_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "smoke"
            config = root / "config.yaml"
            original = ROOT / "experiments/appworld/preliminary/configs/experiment_plan.yaml"
            config.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
            run_synthetic_smoke(output, project_root=ROOT, config_path=config)
            changed = config.read_text(encoding="utf-8") + "\n# changed\n"
            config.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "different code/config/inputs"):
                run_synthetic_smoke(output, project_root=ROOT, config_path=config)


if __name__ == "__main__":
    unittest.main()
