from __future__ import annotations

import unittest

from r2sp.fixtures import (
    SYNTHETIC_NONCE,
    SYNTHETIC_TRIGGER,
    make_synthetic_fixture,
)


class SyntheticFixtureTests(unittest.TestCase):
    def test_fixture_has_exact_clean_scale_and_matched_public_identity(self) -> None:
        fixture = make_synthetic_fixture()
        self.assertEqual(len(fixture.clean_pool), 457)
        sham = fixture.case.overlays.sham.resource
        poison = fixture.case.overlays.poison.resource
        self.assertEqual(
            (sham.resource_id, sham.app_name, sham.api_name, sham.title),
            (poison.resource_id, poison.app_name, poison.api_name, poison.title),
        )
        self.assertNotEqual(sham.content_hash, poison.content_hash)

        sham_spec = fixture.case.overlays.sham.to_dict()
        poison_spec = fixture.case.overlays.poison.to_dict()
        self.assertEqual(sham_spec.pop("arm"), "A_sham")
        self.assertEqual(poison_spec.pop("arm"), "B_poison")
        for spec in (sham_spec, poison_spec):
            spec["resource"].pop("body")
            spec["resource"].pop("content_hash")
        self.assertEqual(sham_spec, poison_spec)

    def test_attack_material_occurs_only_in_poison_body(self) -> None:
        fixture = make_synthetic_fixture()
        sham_body = fixture.case.overlays.sham.resource.body
        poison_body = fixture.case.overlays.poison.resource.body
        self.assertNotEqual(sham_body, poison_body)
        for secret in ("canary", "nonce", SYNTHETIC_TRIGGER, SYNTHETIC_NONCE):
            with self.subTest(secret=secret):
                self.assertNotIn(secret.casefold(), sham_body.casefold())
                self.assertIn(secret.casefold(), poison_body.casefold())

        sham_tokens = len(sham_body.split())
        poison_tokens = len(poison_body.split())
        self.assertLessEqual(
            abs(sham_tokens - poison_tokens) / max(sham_tokens, poison_tokens),
            0.05,
        )

    def test_clean_pool_contains_no_synthetic_attack_material(self) -> None:
        fixture = make_synthetic_fixture()
        clean_bodies = "\n".join(resource.body for resource in fixture.clean_pool).casefold()
        for secret in ("canary", "nonce", SYNTHETIC_TRIGGER, SYNTHETIC_NONCE):
            with self.subTest(secret=secret):
                self.assertNotIn(secret.casefold(), clean_bodies)

    def test_negative_task_has_no_assay_language(self) -> None:
        instruction = make_synthetic_fixture().case.negative_task.instruction
        assert instruction is not None
        for forbidden in ("marker", "test", "canary", "trigger"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, instruction.casefold())

    def test_provenance_is_structured_and_permanently_nonresearch(self) -> None:
        provenance = make_synthetic_fixture().provenance.to_dict()
        self.assertEqual(provenance["schema_version"], "r2sp.fixture-provenance.v1")
        self.assertEqual(provenance["source_type"], "synthetic")
        self.assertEqual(provenance["mode"], "synthetic_smoke")
        self.assertFalse(provenance["research_eligible"])
        self.assertEqual(provenance["purpose"], "instrumentation_validation_only")

    def test_both_acquisition_arms_accept_the_topic_matched_overlay(self) -> None:
        fixture = make_synthetic_fixture()
        self.assertEqual(
            len(fixture.clean_pool.with_overlay(fixture.case.overlays.sham.resource)),
            458,
        )
        self.assertEqual(
            len(fixture.clean_pool.with_overlay(fixture.case.overlays.poison.resource)),
            458,
        )


if __name__ == "__main__":
    unittest.main()
