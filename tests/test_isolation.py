from __future__ import annotations

import unittest

from r2sp.isolation import (
    ResetAttestationError,
    ResetEvidence,
    RuntimeIdentity,
    attest_reset,
)


def _valid_evidence() -> ResetEvidence:
    return ResetEvidence(
        frozen_clean_pool_hash="a" * 64,
        deployment_pool_hash="A" * 64,
        overlay_id="overlay-1",
        overlay_content_hash="b" * 64,
        deployment_resource_ids={"clean-1", "clean-2"},
        deployment_resource_hashes={"c" * 64, "d" * 64},
        acquisition_runtime=RuntimeIdentity(
            world_id="world-acq",
            context_id="context-acq",
            session_id="session-acq",
        ),
        deployment_runtime=RuntimeIdentity(
            world_id="world-deploy",
            context_id="context-deploy",
            session_id="session-deploy",
        ),
        generated_skill_hash="e" * 64,
        loaded_skill_hash="E" * 64,
    )


class ResetAttestationTests(unittest.TestCase):
    def test_all_mandatory_reset_checks_pass(self) -> None:
        result = attest_reset(_valid_evidence())

        self.assertTrue(result.passed)
        self.assertEqual(len(result.checks), 7)
        self.assertEqual(result.failed_checks, ())
        result.require_passed()
        self.assertIn('"passed":true', result.to_json())

    def test_every_reset_invariant_fails_closed(self) -> None:
        evidence = ResetEvidence(
            frozen_clean_pool_hash="a" * 64,
            deployment_pool_hash="f" * 64,
            overlay_id="overlay-1",
            overlay_content_hash="b" * 64,
            deployment_resource_ids={"clean-1", "overlay-1"},
            deployment_resource_hashes={"b" * 64},
            acquisition_runtime=RuntimeIdentity(
                world_id="same-world",
                context_id="same-context",
                session_id="same-session",
            ),
            deployment_runtime=RuntimeIdentity(
                world_id="same-world",
                context_id="same-context",
                session_id="same-session",
            ),
            generated_skill_hash="c" * 64,
            loaded_skill_hash="d" * 64,
        )

        result = attest_reset(evidence)

        self.assertFalse(result.passed)
        self.assertEqual(
            {check.name for check in result.failed_checks},
            {
                "clean_pool_hash_matches",
                "overlay_id_absent",
                "overlay_content_hash_absent",
                "world_id_fresh",
                "context_id_fresh",
                "session_id_fresh",
                "skill_hash_matches",
            },
        )
        with self.assertRaises(ResetAttestationError):
            result.require_passed()

    def test_resource_inventories_are_frozen_at_construction(self) -> None:
        resource_ids = ["clean-1"]
        resource_hashes = ["c" * 64]
        evidence = _valid_evidence()
        evidence = ResetEvidence(
            frozen_clean_pool_hash=evidence.frozen_clean_pool_hash,
            deployment_pool_hash=evidence.deployment_pool_hash,
            overlay_id=evidence.overlay_id,
            overlay_content_hash=evidence.overlay_content_hash,
            deployment_resource_ids=resource_ids,
            deployment_resource_hashes=resource_hashes,
            acquisition_runtime=evidence.acquisition_runtime,
            deployment_runtime=evidence.deployment_runtime,
            generated_skill_hash=evidence.generated_skill_hash,
            loaded_skill_hash=evidence.loaded_skill_hash,
        )
        resource_ids.append("overlay-1")
        resource_hashes.append("b" * 64)

        self.assertTrue(attest_reset(evidence).passed)

    def test_empty_identity_or_hash_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeIdentity(world_id="", context_id="context", session_id="session")
        with self.assertRaises(ValueError):
            ResetEvidence(
                frozen_clean_pool_hash="",
                deployment_pool_hash="a",
                overlay_id="overlay",
                overlay_content_hash="b",
                deployment_resource_ids=set(),
                deployment_resource_hashes=set(),
                acquisition_runtime=RuntimeIdentity("a", "b", "c"),
                deployment_runtime=RuntimeIdentity("d", "e", "f"),
                generated_skill_hash="g",
                loaded_skill_hash="g",
            )


if __name__ == "__main__":
    unittest.main()
