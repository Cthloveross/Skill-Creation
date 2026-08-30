import json
import tempfile
import unittest
from pathlib import Path

from r2sp.models import Resource
from r2sp.resource_pool import ResourcePool, build_clean_pool, load_standard_api_docs


class ResourcePoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = Resource("r-2", "calendar", "create", "Create", "create body")
        self.second = Resource("r-1", "email", "send", "Send", "send body")

    def test_manifest_is_order_independent_and_contains_no_body(self) -> None:
        forward = ResourcePool((self.first, self.second))
        reverse = ResourcePool((self.second, self.first))

        self.assertEqual(forward.manifest.manifest_hash, reverse.manifest.manifest_hash)
        encoded = forward.manifest.to_dict()
        self.assertEqual(encoded["resource_count"], 2)
        self.assertNotIn("body", json.dumps(encoded))

    def test_overlay_can_be_added_then_removed_exactly(self) -> None:
        clean = ResourcePool((self.first, self.second))
        overlay = Resource("overlay", "calendar", "create", "Lookup", "overlay body")

        acquisition = clean.with_overlay(overlay)
        deployment = acquisition.without_resource(overlay.resource_id)

        self.assertEqual(len(acquisition), 3)
        self.assertEqual(deployment.manifest.manifest_hash, clean.manifest.manifest_hash)
        self.assertEqual(acquisition.read_doc("overlay").body, "overlay body")

    def test_duplicate_resource_ids_are_rejected(self) -> None:
        duplicate = Resource("r-2", "other", "other", "Other", "different body")
        with self.assertRaises(ValueError):
            ResourcePool((self.first, duplicate))

    def test_build_clean_pool_filters_helpers_and_checks_count(self) -> None:
        records = [
            {"app_name": "calendar", "api_name": "create", "title": "Create", "body": "body"},
            {"app_name": "api_docs", "api_name": "search", "title": "Helper", "body": "body"},
        ]
        pool = build_clean_pool(records, expected_count=1)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool.resources[0].app_name, "calendar")

    def test_load_standard_docs_accepts_mapping_by_api_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            path.write_text(
                json.dumps({"create_event": {"title": "Create", "description": "Create an event"}}),
                encoding="utf-8",
            )
            pool = load_standard_api_docs(directory, expected_count=1)

        self.assertEqual(len(pool), 1)
        self.assertEqual(pool.resources[0].app_name, "calendar")
        self.assertEqual(pool.resources[0].api_name, "create_event")
        self.assertIn("Create an event", pool.resources[0].body)


if __name__ == "__main__":
    unittest.main()
