from __future__ import annotations

import csv
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from r2sp.artifacts import ArtifactCollisionError
from r2sp.evaluation import Eligibility, summarize
from r2sp.reporting import funnel_csv, summary_json, summary_markdown, write_reports
from tests.test_evaluation import matched


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = summarize(
            [matched(0, poison_selected5=True)],
            eligibility=Eligibility(
                "synthetic_smoke",
                "0.4",
                False,
                False,
                False,
                False,
                1,
                expected_case_count=1,
                provenance={"run_id": "test-run", "config_hash": "a" * 64},
            ),
        )

    def test_funnel_has_one_row_per_case(self) -> None:
        content = funnel_csv(self.summary)
        lines = content.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("poison_full_chain_success", lines[0])
        self.assertIn("poison_overlay_top10", lines[0])
        self.assertIn("poison_overlay_selected5", lines[0])
        self.assertLess(
            lines[0].index("poison_overlay_top10"),
            lines[0].index("poison_overlay_selected5"),
        )
        self.assertLess(
            lines[0].index("poison_overlay_selected5"),
            lines[0].index("poison_natural_read"),
        )
        self.assertIn("deployment_task_denominator_per_arm", lines[0])
        self.assertIn("synthetic_smoke", lines[1])
        row = next(csv.DictReader(StringIO(content)))
        self.assertEqual(row["benign_overlay_selected5"], "False")
        self.assertEqual(row["poison_overlay_selected5"], "True")

    def test_markdown_states_non_independence_boundary(self) -> None:
        markdown = summary_markdown(self.summary)
        self.assertIn("not independent samples", markdown)
        self.assertIn("NOT_ELIGIBLE", markdown)
        self.assertIn("Mode: `synthetic_smoke`", markdown)
        self.assertIn("Deployment tasks (Benign / Poison / total): `2 / 2 / 4`", markdown)
        self.assertIn("Overlay in acquisition top-10", markdown)
        self.assertIn("Overlay selected in model top-5", markdown)
        self.assertIn(
            "Overlay selected in model top-5 (Benign / Poison; denominator 1 each): `0 / 1`",
            markdown,
        )
        self.assertIn('"run_id":"test-run"', markdown)

    def test_write_reports_outputs_parseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports(self.summary, directory)
            payload = json.loads(Path(paths["summary.json"]).read_text(encoding="utf-8"))
        self.assertFalse(payload["research_eligible"])
        self.assertEqual(payload["decision"], "NOT_ELIGIBLE")
        self.assertEqual(payload["mode"], "synthetic_smoke")
        self.assertEqual(payload["denominators"]["deployment_tasks_per_arm"], 2)
        self.assertEqual(payload["benign_overlay_top10"], 1)
        self.assertEqual(payload["poison_overlay_top10"], 1)
        self.assertEqual(payload["benign_overlay_selected5"], 0)
        self.assertEqual(payload["poison_overlay_selected5"], 1)
        self.assertEqual(payload["provenance"]["declared"]["run_id"], "test-run")

    def test_write_reports_resumes_identical_content_but_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = write_reports(self.summary, directory)
            second = write_reports(self.summary, directory)
            self.assertEqual(first, second)
            Path(first["summary.json"]).write_text("different\n", encoding="utf-8")
            with self.assertRaises(ArtifactCollisionError):
                write_reports(self.summary, directory)

    def test_json_exposes_denominators_mode_and_provenance(self) -> None:
        payload = json.loads(summary_json(self.summary))
        self.assertEqual(payload["denominators"]["matched_cases"], 1)
        self.assertEqual(payload["mode"], "synthetic_smoke")
        self.assertEqual(payload["provenance"]["declared"]["config_hash"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
