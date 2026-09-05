from __future__ import annotations

import os
import unittest
from pathlib import Path

from r2sp.integrity import ContentDigest, hash_tree

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
DATASETS = ("appworld", "tau-knowledge")
PRELIMINARY_CHILDREN = {
    "configs",
    "data",
    "injections",
    "plans",
    "prompts",
    "runs",
    "schemas",
    "scripts",
    "tests",
}
ENTRYPOINTS = {"bootstrap.sh", "materialize.py", "replay.py", "run_preliminary.py"}
APPWORLD_DATA_COMMITMENTS = {
    "appworld-0.1.0": ContentDigest(
        sha256="8c9ae087e4d62855c96f00d25fc72655dce5243c6f30541e6c25b0d0063d9d2d",
        file_count=15_058,
        size_bytes=204_803_395,
    ),
    "file-injection-appworld-20260901-v3": ContentDigest(
        sha256="94ff480f14a78cd3fc2b1945bc680294df3641c41e610af06ecd07179fcf6cf5",
        file_count=48,
        size_bytes=3_113_845,
    ),
}


class ExperimentTopologyTests(unittest.TestCase):
    def test_only_two_dataset_roots_exist_without_pilot_alias(self) -> None:
        roots = {path.name for path in EXPERIMENTS.iterdir() if path.is_dir()}
        self.assertEqual(roots, set(DATASETS))
        self.assertFalse(os.path.lexists(EXPERIMENTS / "pilot"))

    def test_each_dataset_has_complete_preliminary_tree(self) -> None:
        for dataset in DATASETS:
            with self.subTest(dataset=dataset):
                root = EXPERIMENTS / dataset / "preliminary"
                children = {path.name for path in root.iterdir() if path.is_dir()}
                self.assertEqual(children, PRELIMINARY_CHILDREN)
                self.assertTrue((root / "data" / ".gitkeep").is_file())
                self.assertTrue((root / "runs" / ".gitkeep").is_file())

    def test_dataset_entrypoints_are_distinct_and_executable(self) -> None:
        script_roots = {
            dataset: EXPERIMENTS / dataset / "preliminary" / "scripts" for dataset in DATASETS
        }
        for dataset, root in script_roots.items():
            with self.subTest(dataset=dataset):
                scripts = {path.name for path in root.iterdir() if path.is_file()}
                self.assertEqual(scripts, ENTRYPOINTS)
                for name in ENTRYPOINTS:
                    self.assertTrue(os.access(root / name, os.X_OK), name)

        appworld_text = "\n".join(
            (script_roots["appworld"] / name).read_text(encoding="utf-8")
            for name in sorted(ENTRYPOINTS)
        )
        tau_text = "\n".join(
            (script_roots["tau-knowledge"] / name).read_text(encoding="utf-8")
            for name in sorted(ENTRYPOINTS)
        )
        self.assertNotIn("r2sp_tau_knowledge", appworld_text)
        self.assertNotIn("from r2sp.", tau_text)
        self.assertNotIn("import r2sp.", tau_text)

    def test_migrated_appworld_data_bytes_match_pre_move_commitments(self) -> None:
        data_root = EXPERIMENTS / "appworld" / "preliminary" / "data"
        if any(not (data_root / name).is_dir() for name in APPWORLD_DATA_COMMITMENTS):
            self.skipTest("requires the ignored AppWorld data trees")
        for name, expected in APPWORLD_DATA_COMMITMENTS.items():
            with self.subTest(tree=name):
                self.assertEqual(hash_tree(data_root / name), expected)


if __name__ == "__main__":
    unittest.main()
