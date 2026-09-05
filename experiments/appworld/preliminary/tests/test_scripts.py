from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from r2sp.cli import main as r2sp_main
from r2sp.file_injection_fixture import materialize_appworld_file_bundles
from tests.test_file_injection_fixture import _make_appworld_tree

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = EXPERIMENT_ROOT.parents[2]
SCRIPT_ROOT = EXPERIMENT_ROOT / "scripts"
EXPECTED_SCRIPTS = {
    "bootstrap.sh",
    "materialize.py",
    "replay.py",
    "run_preliminary.py",
}


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class AppWorldScriptTests(unittest.TestCase):
    def test_script_set_is_executable_and_does_not_import_tau(self) -> None:
        observed = {path.name for path in SCRIPT_ROOT.iterdir() if path.is_file()}
        self.assertEqual(observed, EXPECTED_SCRIPTS)
        for name in sorted(EXPECTED_SCRIPTS):
            with self.subTest(script=name):
                path = SCRIPT_ROOT / name
                self.assertTrue(os.access(path, os.X_OK))
                self.assertNotIn("r2sp_tau_knowledge", path.read_text(encoding="utf-8"))

    def test_every_entrypoint_has_standalone_help(self) -> None:
        commands = {
            "bootstrap.sh": [str(SCRIPT_ROOT / "bootstrap.sh"), "--help"],
            "materialize.py": [sys.executable, str(SCRIPT_ROOT / "materialize.py"), "--help"],
            "replay.py": [sys.executable, str(SCRIPT_ROOT / "replay.py"), "--help"],
            "run_preliminary.py": [
                sys.executable,
                str(SCRIPT_ROOT / "run_preliminary.py"),
                "--help",
            ],
        }
        for name, command in commands.items():
            with self.subTest(script=name):
                completed = _run(*command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage:", completed.stdout.lower())

    def test_bootstrap_validates_the_current_environment_without_writes(self) -> None:
        completed = _run(
            str(SCRIPT_ROOT / "bootstrap.sh"),
            "--python",
            sys.executable,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["appworld_preliminary_environment"], "valid")
        self.assertGreaterEqual(tuple(map(int, result["python_version"].split(".")))[:2], (3, 10))
        self.assertEqual(Path(result["project_root"]), PROJECT_ROOT)

    def test_materialize_entrypoint_writes_replayable_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld_root = _make_appworld_tree(temporary / "appworld")
            output = temporary / "bundles"
            completed = _run(
                sys.executable,
                str(SCRIPT_ROOT / "materialize.py"),
                "--appworld-root",
                str(appworld_root),
                "--payload-directory",
                str(EXPERIMENT_ROOT / "injections"),
                "--output-root",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertRegex(result["payload_set_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                Path(result["output_directory"]).parent,
                output,
            )
            self.assertEqual(set(result["manifests"]), {"delete-sentinel", "mock-api-call"})
            for arms in result["manifests"].values():
                self.assertEqual(set(arms), {"benign", "poison"})
                for manifest in arms.values():
                    self.assertTrue(Path(manifest).is_file())

    def test_run_preliminary_executes_only_the_offline_boundary_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            appworld_root = _make_appworld_tree(temporary / "appworld")
            bundle_root = temporary / "bundles"
            materialize_appworld_file_bundles(
                appworld_root,
                bundle_root,
                payload_directory=EXPERIMENT_ROOT / "injections",
            )
            output = temporary / "offline-regression"

            completed = _run(
                sys.executable,
                str(SCRIPT_ROOT / "run_preliminary.py"),
                "--appworld-root",
                str(appworld_root),
                "--bundle-directory",
                str(bundle_root),
                "--output",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(Path(completed.stdout.strip()), output / "report.json")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "appworld_preliminary_offline_regression")
            self.assertEqual(len(report["records"]), 4)
            for record in report["records"]:
                self.assertTrue(record["body_only"])
                self.assertFalse(record["select_docs_exposed"])
                self.assertLessEqual(len(record["agent_visible"]["results"]), 5)
                self.assertLessEqual(len(record["evaluator_search"]["top10"]), 10)

    def test_replay_entrypoint_uses_the_completed_artifact_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "offline-regression"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = r2sp_main(
                    [
                        "smoke",
                        "--output",
                        str(output),
                        "--config",
                        str(EXPERIMENT_ROOT / "configs" / "experiment_plan.yaml"),
                        "--project-root",
                        str(PROJECT_ROOT),
                    ]
                )
            self.assertEqual(status, 0)
            complete_sha256 = json.loads(stdout.getvalue())["complete_hash"]

            completed = _run(
                sys.executable,
                str(SCRIPT_ROOT / "replay.py"),
                "--run-directory",
                str(output),
                "--expected-complete-sha256",
                complete_sha256,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["decision"], "NOT_ELIGIBLE")


if __name__ == "__main__":
    unittest.main()
