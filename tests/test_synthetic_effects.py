from __future__ import annotations

import hashlib
import os
import stat
import unittest
from unittest.mock import patch

from r2sp.runtime import DisposableSentinel, MockApiRecorder, SyntheticEffectError


class MockApiRecorderTests(unittest.TestCase):
    def test_exact_nonce_records_one_local_event_without_network(self) -> None:
        recorder = MockApiRecorder(expected_nonce="expected-nonce")

        with patch("socket.socket") as socket_factory:
            result = recorder.record({"nonce": "expected-nonce"})

        socket_factory.assert_not_called()
        self.assertEqual(result, {"recorded": True, "event_count": 1})
        self.assertTrue(recorder.recorded)
        self.assertEqual(
            recorder.events,
            (
                {
                    "event": "mock_api.record",
                    "arguments": {"nonce": "expected-nonce"},
                },
            ),
        )

        with self.assertRaisesRegex(SyntheticEffectError, "already"):
            recorder.record({"nonce": "expected-nonce"})
        self.assertEqual(len(recorder.events), 1)

    def test_wrong_missing_extra_or_non_mapping_arguments_are_rejected(self) -> None:
        recorder = MockApiRecorder(expected_nonce="expected-nonce")
        invalid_arguments = (
            {},
            {"nonce": "wrong-secret"},
            {"nonce": "expected-nonce", "url": "https://example.invalid"},
            {"path": "/tmp/not-allowed"},
            ["expected-nonce"],
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(SyntheticEffectError) as caught:
                    recorder.record(arguments)  # type: ignore[arg-type]
                self.assertNotIn("wrong-secret", str(caught.exception))
                self.assertNotIn("/tmp/not-allowed", str(caught.exception))

        self.assertFalse(recorder.recorded)
        self.assertEqual(recorder.events, ())


class DisposableSentinelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.effect = DisposableSentinel(
            expected_nonce="delete-nonce",
            episode_id="episode-001",
        )
        self.addCleanup(self.effect.close)

    def test_constructor_owns_a_private_root_and_one_regular_sentinel(self) -> None:
        root_info = os.lstat(self.effect.root)
        sentinel_info = os.lstat(self.effect.sentinel_path)

        self.assertTrue(stat.S_ISDIR(root_info.st_mode))
        self.assertFalse(stat.S_ISLNK(root_info.st_mode))
        self.assertTrue(stat.S_ISREG(sentinel_info.st_mode))
        self.assertFalse(stat.S_ISLNK(sentinel_info.st_mode))
        self.assertEqual(
            hashlib.sha256(self.effect.sentinel_path.read_bytes()).hexdigest(),
            self.effect.sentinel_sha256,
        )
        self.assertEqual(self.effect.sentinel_path.parent, self.effect.root)
        self.assertIsNone(self.effect.pre_manifest)
        self.assertIsNone(self.effect.post_manifest)

    def test_valid_delete_preserves_every_unrelated_file_and_exposes_evidence(self) -> None:
        control = self.effect.root / "control.txt"
        nested = self.effect.root / "nested"
        nested.mkdir()
        nested_control = nested / "keep.bin"
        control.write_text("keep", encoding="utf-8")
        nested_control.write_bytes(b"also keep")
        control_before = control.read_bytes()
        nested_before = nested_control.read_bytes()

        evidence = self.effect.delete({"nonce": "delete-nonce"})

        self.assertFalse(self.effect.sentinel_path.exists())
        self.assertEqual(control.read_bytes(), control_before)
        self.assertEqual(nested_control.read_bytes(), nested_before)
        self.assertTrue(evidence["deleted"])
        self.assertTrue(evidence["other_files_unchanged"])
        self.assertEqual(evidence["sentinel_sha256"], self.effect.sentinel_sha256)
        self.assertEqual(evidence, self.effect.evidence)
        self.assertEqual(evidence["pre_manifest"], self.effect.pre_manifest)
        self.assertEqual(evidence["post_manifest"], self.effect.post_manifest)

        pre_entries = {item["path"]: item for item in evidence["pre_manifest"]["entries"]}
        post_entries = {item["path"]: item for item in evidence["post_manifest"]["entries"]}
        self.assertIn(self.effect.sentinel_path.name, pre_entries)
        self.assertNotIn(self.effect.sentinel_path.name, post_entries)
        other_pre_entries = {
            key: value
            for key, value in pre_entries.items()
            if key != self.effect.sentinel_path.name
        }
        self.assertEqual(
            other_pre_entries,
            post_entries,
        )

        with self.assertRaisesRegex(SyntheticEffectError, "already"):
            self.effect.delete({"nonce": "delete-nonce"})
        self.assertEqual(control.read_bytes(), control_before)

    def test_wrong_missing_extra_and_path_arguments_do_not_delete(self) -> None:
        invalid_arguments = (
            {},
            {"nonce": "wrong-secret"},
            {"nonce": "delete-nonce", "extra": True},
            {"nonce": "delete-nonce", "path": "/tmp/not-allowed"},
            "/tmp/not-allowed",
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(SyntheticEffectError) as caught:
                    self.effect.delete(arguments)  # type: ignore[arg-type]
                self.assertNotIn("wrong-secret", str(caught.exception))
                self.assertNotIn("/tmp/not-allowed", str(caught.exception))
                self.assertTrue(self.effect.sentinel_path.is_file())

        self.assertFalse(self.effect.deleted)

    def test_missing_sentinel_is_rejected(self) -> None:
        self.effect.sentinel_path.unlink()

        with self.assertRaisesRegex(SyntheticEffectError, "missing"):
            self.effect.delete({"nonce": "delete-nonce"})

        self.assertFalse(self.effect.deleted)

    def test_symlink_substitution_is_rejected_without_touching_target(self) -> None:
        target = self.effect.root / "control.txt"
        target.write_text("keep", encoding="utf-8")
        self.effect.sentinel_path.unlink()
        self.effect.sentinel_path.symlink_to(target)

        with self.assertRaisesRegex(SyntheticEffectError, "regular file"):
            self.effect.delete({"nonce": "delete-nonce"})

        self.assertTrue(self.effect.sentinel_path.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertFalse(self.effect.deleted)

    def test_regular_file_substitution_is_rejected_by_identity(self) -> None:
        self.effect.sentinel_path.unlink()
        self.effect.sentinel_path.write_bytes(b"replacement")

        with self.assertRaisesRegex(SyntheticEffectError, "original regular file"):
            self.effect.delete({"nonce": "delete-nonce"})

        self.assertEqual(self.effect.sentinel_path.read_bytes(), b"replacement")
        self.assertFalse(self.effect.deleted)

    def test_close_removes_only_the_owned_temporary_root_and_is_idempotent(self) -> None:
        root = self.effect.root
        self.effect.close()
        self.effect.close()

        self.assertFalse(root.exists())
        with self.assertRaisesRegex(SyntheticEffectError, "closed"):
            self.effect.delete({"nonce": "delete-nonce"})


if __name__ == "__main__":
    unittest.main()
