from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from r2sp.integrity import (
    IntegrityError,
    hash_appworld_runtime_snapshot,
    hash_tree,
)


class AppWorldSnapshotFixture:
    def __init__(self, base: Path) -> None:
        self.root = base / "appworld-root"
        self.package = base / "site-packages" / "appworld"
        self.metadata = base / "site-packages" / "appworld-0.1.3.post1.dist-info"
        self.package.mkdir(parents=True)
        self.metadata.mkdir(parents=True)
        (self.package / "__init__.py").write_text("VERSION = 'fixture'\n", encoding="utf-8")
        (self.package / "evaluator.py").write_text("def score(): return 1\n", encoding="utf-8")
        (self.metadata / "METADATA").write_text(
            "Name: appworld\nVersion: 0.1.3.post1\n",
            encoding="utf-8",
        )
        (self.metadata / "direct_url.json").write_text(
            '{"vcs_info":{"commit_id":"fixture"}}\n',
            encoding="utf-8",
        )

        data = self.root / "data"
        self.base_db = data / "base_dbs" / "calendar.db"
        self.standard_doc = data / "api_docs" / "standard" / "calendar.json"
        self.train_split = data / "datasets" / "train.txt"
        self.base_db.parent.mkdir(parents=True)
        self.standard_doc.parent.mkdir(parents=True)
        self.train_split.parent.mkdir(parents=True)
        self.base_db.write_bytes(b"base-db-fixture")
        self.standard_doc.write_text('{"api":"fixture"}\n', encoding="utf-8")
        self.task_ids = tuple(f"fixture_{index + 1}" for index in range(48))
        self.train_split.write_text("\n".join(self.task_ids) + "\n", encoding="utf-8")
        self.task_db: Path | None = None
        self.ground_truth: Path | None = None
        for index, task_id in enumerate(self.task_ids):
            task = data / "tasks" / task_id
            specs = task / "specs.json"
            task_db = task / "dbs" / "calendar.jsonl"
            ground_truth = task / "ground_truth" / "evaluation.py"
            specs.parent.mkdir(parents=True)
            task_db.parent.mkdir(parents=True)
            ground_truth.parent.mkdir(parents=True)
            specs.write_text(f'{{"instruction":"task {index}"}}\n', encoding="utf-8")
            task_db.write_text(f'{{"row":{index}}}\n', encoding="utf-8")
            ground_truth.write_text(f"EXPECTED = {index}\n", encoding="utf-8")
            if index == 0:
                self.task_db = task_db
                self.ground_truth = ground_truth

    @contextmanager
    def installed_appworld(self):
        with (
            patch(
                "r2sp.integrity._locate_appworld_package_root",
                return_value=self.package,
            ),
            patch(
                "r2sp.integrity._locate_appworld_distribution_metadata_root",
                return_value=self.metadata,
            ),
        ):
            yield

    def snapshot(self):
        with self.installed_appworld():
            return hash_appworld_runtime_snapshot(self.root, self.task_ids)


class IntegrityTests(unittest.TestCase):
    def test_tree_hash_is_deterministic_and_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tree"
            (root / "nested").mkdir(parents=True)
            (root / "z.txt").write_bytes(b"z")
            (root / "nested" / "a.txt").write_bytes(b"a")

            first = hash_tree(root)
            second = hash_tree(root)

        self.assertEqual(first, second)
        self.assertEqual(first.file_count, 2)
        self.assertEqual(first.size_bytes, 2)
        self.assertEqual(set(first.to_dict()), {"sha256", "file_count", "size_bytes"})
        self.assertNotIn(str(root), repr(first))

    def test_snapshot_binds_every_declared_runtime_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = AppWorldSnapshotFixture(Path(directory))
            assert fixture.task_db is not None
            assert fixture.ground_truth is not None
            mutations = (
                fixture.package / "evaluator.py",
                fixture.metadata / "METADATA",
                fixture.base_db,
                fixture.standard_doc,
                fixture.train_split,
                fixture.task_db,
                fixture.ground_truth,
            )
            baseline = fixture.snapshot()
            for path in mutations:
                with self.subTest(component=path.name):
                    original = path.read_bytes()
                    path.write_bytes(original + b"mutation")
                    self.assertNotEqual(fixture.snapshot().sha256, baseline.sha256)
                    path.write_bytes(original)
                    self.assertEqual(fixture.snapshot(), baseline)

        self.assertEqual(baseline.file_count, 151)
        self.assertNotIn("fixture_1", repr(baseline))

    def test_pycache_and_regular_pyc_files_are_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = AppWorldSnapshotFixture(Path(directory))
            baseline = fixture.snapshot()
            cache = fixture.package / "__pycache__"
            cache.mkdir()
            (cache / "evaluator.cpython-311.pyc").write_bytes(b"unstable-cache")
            (fixture.package / "legacy.pyc").write_bytes(b"unstable-cache")
            with_bytecode = fixture.snapshot()
            self.assertNotEqual(with_bytecode.sha256, baseline.sha256)
            self.assertEqual(with_bytecode.file_count, baseline.file_count + 2)
            (cache / "evaluator.cpython-311.pyc").write_bytes(b"different-bytecode")
            self.assertNotEqual(fixture.snapshot().sha256, with_bytecode.sha256)

    def test_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = AppWorldSnapshotFixture(Path(directory))
            link = fixture.base_db.parent / "linked.db"
            link.symlink_to(fixture.base_db)
            with self.assertRaisesRegex(IntegrityError, "symbolic link"):
                fixture.snapshot()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation requires POSIX")
    def test_special_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = AppWorldSnapshotFixture(Path(directory))
            os.mkfifo(fixture.base_db.parent / "runtime.pipe")
            with self.assertRaisesRegex(IntegrityError, "special file"):
                fixture.snapshot()

    def test_missing_and_empty_trees_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaisesRegex(IntegrityError, "missing or unreadable"):
                hash_tree(base / "missing")
            empty = base / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(IntegrityError, "no hashable files"):
                hash_tree(empty)

            fixture = AppWorldSnapshotFixture(base)
            missing_task = fixture.root / "data" / "tasks" / fixture.task_ids[-1]
            moved_task = missing_task.with_name("temporarily-moved")
            missing_task.rename(moved_task)
            with self.assertRaisesRegex(IntegrityError, "missing or unreadable"):
                fixture.snapshot()

    def test_task_id_set_must_be_exact_unique_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = AppWorldSnapshotFixture(Path(directory))
            with fixture.installed_appworld():
                with self.assertRaisesRegex(IntegrityError, "exactly 48 unique"):
                    hash_appworld_runtime_snapshot(fixture.root, fixture.task_ids[:-1])
                unsafe = (*fixture.task_ids[:-1], "../escape_1")
                with self.assertRaisesRegex(IntegrityError, "safely formatted"):
                    hash_appworld_runtime_snapshot(fixture.root, unsafe)


if __name__ == "__main__":
    unittest.main()
