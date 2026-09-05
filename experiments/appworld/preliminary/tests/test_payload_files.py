from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from r2sp.appworld_payloads import (
    APPWORLD_INJECTION_FILES,
    AppWorldPayloadError,
    load_appworld_injection_payloads,
)

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
INJECTION_ROOT = EXPERIMENT_ROOT / "injections"
EXPECTED_PAYLOADS = {
    "mock-api-call": (
        1346,
        "5d075bdd23ec1a278346e098ebc4d3b6e53b3ece6de393723353923ff25b8bf5",
    ),
    "delete-sentinel": (
        1395,
        "dc3724eb9d045466e3a4c0659fbf85e00c4744792a7e83fa083bb862b5e72fdd",
    ),
}


def _write_valid_shape(root: Path, *, mock: bytes = b"mock", delete: bytes = b"delete") -> None:
    root.mkdir()
    (root / APPWORLD_INJECTION_FILES["mock-api-call"]).write_bytes(mock)
    (root / APPWORLD_INJECTION_FILES["delete-sentinel"]).write_bytes(delete)


class AppWorldPayloadFileTests(unittest.TestCase):
    def test_repository_payloads_have_frozen_exact_bytes(self) -> None:
        payloads = load_appworld_injection_payloads(INJECTION_ROOT)
        self.assertEqual(set(payloads), set(EXPECTED_PAYLOADS))
        for profile_name, (size, expected_sha256) in EXPECTED_PAYLOADS.items():
            with self.subTest(profile=profile_name):
                path = INJECTION_ROOT / APPWORLD_INJECTION_FILES[profile_name]
                raw = path.read_bytes()
                self.assertEqual(len(raw), size)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha256)
                self.assertFalse(raw.endswith(b"\n"))
                self.assertEqual(payloads[profile_name].encode("utf-8"), raw)

    def test_loader_preserves_all_whitespace_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "payloads"
            raw = b"  first\r\nsecond\n"
            _write_valid_shape(root, mock=raw)
            payloads = load_appworld_injection_payloads(root)
            self.assertEqual(payloads["mock-api-call"].encode("utf-8"), raw)

    def test_loader_rejects_missing_or_extra_txt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "missing"
            root.mkdir()
            (root / APPWORLD_INJECTION_FILES["mock-api-call"]).write_bytes(b"mock")
            with self.assertRaisesRegex(AppWorldPayloadError, "exactly the two"):
                load_appworld_injection_payloads(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "extra"
            _write_valid_shape(root)
            (root / "extra.txt").write_bytes(b"extra")
            with self.assertRaisesRegex(AppWorldPayloadError, "exactly the two"):
                load_appworld_injection_payloads(root)

    def test_loader_rejects_empty_nul_and_invalid_utf8(self) -> None:
        cases = {
            "empty": b"",
            "nul": b"before\x00after",
            "invalid-utf8": b"\xff",
        }
        for name, raw in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "payloads"
                _write_valid_shape(root, mock=raw)
                with self.assertRaises(AppWorldPayloadError):
                    load_appworld_injection_payloads(root)

    def test_loader_rejects_payload_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "payloads"
            root.mkdir()
            target = temporary / "payload.bin"
            target.write_bytes(b"mock")
            (root / APPWORLD_INJECTION_FILES["mock-api-call"]).symlink_to(target)
            (root / APPWORLD_INJECTION_FILES["delete-sentinel"]).write_bytes(b"delete")
            with self.assertRaisesRegex(AppWorldPayloadError, "unsafe"):
                load_appworld_injection_payloads(root)


if __name__ == "__main__":
    unittest.main()
