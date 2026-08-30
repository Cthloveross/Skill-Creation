from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from r2sp.artifacts import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactStore,
    sha256_bytes,
    sha256_file,
    verify_artifact_manifest,
    write_artifact_manifest,
)


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "artifacts"
        self.store = ArtifactStore(self.root)

    def test_atomic_write_and_identical_resume(self) -> None:
        payload = b"generated skill\n"

        created = self.store.write_bytes("run-1/SKILL.md", payload)
        original_stat = created.path.stat()
        resumed = self.store.write_bytes("run-1/SKILL.md", payload)

        self.assertTrue(created.created)
        self.assertFalse(created.resumed)
        self.assertTrue(resumed.resumed)
        self.assertEqual(created.sha256, sha256_bytes(payload))
        self.assertEqual(sha256_file(created.path), created.sha256)
        self.assertEqual(created.path.read_bytes(), payload)
        self.assertEqual(resumed.path.stat().st_ino, original_stat.st_ino)
        self.assertEqual(os.stat(created.path).st_mode & 0o077, 0)
        self.assertEqual(list(created.path.parent.glob(".*.tmp")), [])

    def test_different_content_is_a_collision_and_never_overwrites(self) -> None:
        path = "run-1/result.json"
        self.store.write_bytes(path, b"first")

        with self.assertRaises(ArtifactCollisionError):
            self.store.write_bytes(path, b"second")

        self.assertEqual((self.root / path).read_bytes(), b"first")

    def test_expected_hash_is_checked_before_publication(self) -> None:
        with self.assertRaises(ArtifactIntegrityError):
            self.store.write_text("run-1/SKILL.md", "content", expected_sha256="0" * 64)

        self.assertFalse((self.root / "run-1" / "SKILL.md").exists())

    def test_canonical_json_resumes_across_mapping_order(self) -> None:
        first = self.store.write_json("run-1/reset.json", {"b": 2, "a": 1})
        second = self.store.write_json("run-1/reset.json", {"a": 1, "b": 2})

        self.assertFalse(first.resumed)
        self.assertTrue(second.resumed)
        self.assertEqual(first.path.read_bytes(), b'{"a":1,"b":2}\n')

    def test_unsafe_paths_are_rejected(self) -> None:
        for path in ("../escape", "/absolute", ".", "run/../escape"):
            with self.subTest(path=path), self.assertRaises(ArtifactPathError):
                self.store.write_bytes(path, b"x")

    def test_concurrent_identical_writers_create_once_then_resume(self) -> None:
        def write() -> bool:
            return self.store.write_bytes("run-1/trace.bin", b"trace").resumed

        with ThreadPoolExecutor(max_workers=2) as executor:
            resumed_flags = list(executor.map(lambda _: write(), range(2)))

        self.assertEqual(sorted(resumed_flags), [False, True])
        self.assertEqual((self.root / "run-1" / "trace.bin").read_bytes(), b"trace")

    def test_full_manifest_round_trip_is_deterministic(self) -> None:
        first = self.store.write_text("cases/case-01/SKILL.md", "generated skill\n")
        second = self.store.write_json("reports/summary.json", {"decision": "eligible"})
        self.store.write_json("complete.json", {"status": "not-yet-complete"})
        self.store.write_text(".active.lock", "owner\n")

        manifest = write_artifact_manifest(self.root, self.store)
        verify_artifact_manifest(self.root, manifest.path)
        payload = json.loads(manifest.path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["artifact_count"], 2)
        self.assertEqual(
            payload["artifacts"],
            [
                {
                    "path": first.relative_path,
                    "sha256": first.sha256,
                    "size_bytes": first.size_bytes,
                },
                {
                    "path": second.relative_path,
                    "sha256": second.sha256,
                    "size_bytes": second.size_bytes,
                },
            ],
        )

    def test_manifest_verification_rejects_tampered_artifact(self) -> None:
        artifact = self.store.write_text("reports/summary.md", "original\n")
        manifest = write_artifact_manifest(self.root, self.store)
        artifact.path.write_text("tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(ArtifactIntegrityError, "verification failed"):
            verify_artifact_manifest(self.root, manifest.path)

    def test_manifest_verification_rejects_missing_artifact(self) -> None:
        artifact = self.store.write_text("reports/summary.md", "original\n")
        manifest = write_artifact_manifest(self.root, self.store)
        artifact.path.unlink()

        with self.assertRaisesRegex(ArtifactIntegrityError, "verification failed"):
            verify_artifact_manifest(self.root, manifest.path)

    def test_manifest_verification_rejects_extra_artifact(self) -> None:
        self.store.write_text("reports/summary.md", "original\n")
        manifest = write_artifact_manifest(self.root, self.store)
        (self.root / "untracked.txt").write_text("extra\n", encoding="utf-8")

        with self.assertRaisesRegex(ArtifactIntegrityError, "verification failed"):
            verify_artifact_manifest(self.root, manifest.path)

    def test_manifest_write_and_verification_reject_symlinks(self) -> None:
        self.store.write_text("reports/summary.md", "original\n")
        target = Path(self.temporary_directory.name) / "outside.txt"
        target.write_text("outside\n", encoding="utf-8")
        symlink = self.root / "linked.txt"
        symlink.symlink_to(target)

        with self.assertRaisesRegex(ArtifactIntegrityError, "symlink"):
            write_artifact_manifest(self.root, self.store)

        symlink.unlink()
        manifest = write_artifact_manifest(self.root, self.store)
        symlink.symlink_to(target)
        with self.assertRaisesRegex(ArtifactIntegrityError, "verification failed"):
            verify_artifact_manifest(self.root, manifest.path)


if __name__ == "__main__":
    unittest.main()
