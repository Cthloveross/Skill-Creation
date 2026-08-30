from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from r2sp.canary import (
    CanaryLogError,
    CanaryUnavailableError,
    EvaluatorOwnedCanary,
    read_canary_events,
)


class EvaluatorOwnedCanaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.log_path = Path(self.temporary_directory.name) / "evaluator" / "canary.jsonl"
        self.canary = EvaluatorOwnedCanary(
            self.log_path,
            run_id="run-001",
            skill_hash="a" * 64,
            expected_nonce="expected-nonce",
            clock=lambda: datetime(2026, 8, 29, tzinfo=timezone.utc),
        )

    def test_authoring_call_is_rejected_without_creating_a_log(self) -> None:
        tool = self.canary.authoring_tool(episode_id="authoring-1")

        with self.assertRaises(CanaryUnavailableError):
            tool.emit("expected-nonce")

        self.assertFalse(self.log_path.exists())
        self.assertFalse(hasattr(tool, "log_path"))
        self.assertFalse(hasattr(tool, "read_events"))

    def test_every_deployment_call_is_appended_and_counts_specificity(self) -> None:
        tool = self.canary.deployment_tool(
            episode_id="deployment-1", arm="poison", trigger_present=True
        )

        first = tool.emit("expected-nonce")
        second = tool.emit("wrong-nonce")
        third = tool.emit()
        fourth = tool.invoke(["malformed", "arguments"])

        self.assertTrue(first.recorded)
        self.assertEqual(len({first.call_id, second.call_id, third.call_id, fourth.call_id}), 4)

        events = self.canary.read_events()
        self.assertEqual(len(events), 4)
        self.assertEqual([event["nonce_matches"] for event in events], [True, False, False, False])
        self.assertEqual([event["nonce_present"] for event in events], [True, True, False, False])
        self.assertTrue(all(event["phase"] == "deployment" for event in events))
        self.assertTrue(all(event["run_id"] == "run-001" for event in events))

        summary = self.canary.summary()
        self.assertEqual(summary.total_calls, 4)
        self.assertEqual(summary.matching_nonce_calls, 1)
        self.assertEqual(summary.specificity_call_count, 4)

        raw_lines = self.log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(raw_lines), 4)
        self.assertEqual(os.stat(self.log_path).st_mode & 0o077, 0)

    def test_new_evaluator_instance_resumes_the_same_jsonl_log(self) -> None:
        self.canary.deployment_tool().emit("wrong")
        resumed = EvaluatorOwnedCanary(
            self.log_path,
            run_id="run-002",
            skill_hash="b" * 64,
            expected_nonce="other",
        )

        resumed.deployment_tool().emit("other")

        events = read_canary_events(self.log_path)
        self.assertEqual([event["run_id"] for event in events], ["run-001", "run-002"])
        self.assertEqual(len(events), 2)

    def test_malformed_or_partial_log_fails_closed(self) -> None:
        self.log_path.parent.mkdir(parents=True)
        self.log_path.write_text('{"event":"canary.emit"}', encoding="utf-8")

        with self.assertRaises(CanaryLogError):
            read_canary_events(self.log_path)


if __name__ == "__main__":
    unittest.main()
