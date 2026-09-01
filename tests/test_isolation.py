from __future__ import annotations

import unittest

from r2sp.isolation import (
    ResetAttestationError,
    ResetEvidence,
    RuntimeIdentity,
    SkillOnlyResetEvidence,
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


def _valid_skill_only_evidence() -> SkillOnlyResetEvidence:
    return SkillOnlyResetEvidence(
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
        generated_skill_hash="a" * 64,
        loaded_skill_hash="A" * 64,
        deployment_resource_pool_attached=False,
        exposed_tool_names=("execute", "finish"),
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

    def test_replacement_reset_requires_same_id_and_restored_clean_hash(self) -> None:
        evidence = _valid_evidence()
        evidence = ResetEvidence(
            frozen_clean_pool_hash=evidence.frozen_clean_pool_hash,
            deployment_pool_hash=evidence.deployment_pool_hash,
            overlay_id="clean-1",
            overlay_content_hash=evidence.overlay_content_hash,
            deployment_resource_ids={"clean-1", "clean-2"},
            deployment_resource_hashes={"c" * 64, "d" * 64},
            acquisition_runtime=evidence.acquisition_runtime,
            deployment_runtime=evidence.deployment_runtime,
            generated_skill_hash=evidence.generated_skill_hash,
            loaded_skill_hash=evidence.loaded_skill_hash,
            reset_mode="replacement_restored",
            restored_content_hash="c" * 64,
            deployment_resource_content_hashes={
                "clean-1": "c" * 64,
                "clean-2": "d" * 64,
            },
        )

        result = attest_reset(evidence)

        self.assertTrue(result.passed)
        self.assertEqual(result.mode, "replacement_restored")
        self.assertEqual(len(result.checks), 8)
        self.assertEqual(result.to_dict()["mode"], "replacement_restored")
        self.assertEqual(
            {check.name for check in result.checks},
            {
                "clean_pool_hash_matches",
                "target_resource_id_present",
                "poison_content_hash_absent",
                "clean_target_content_hash_restored_at_target_id",
                "world_id_fresh",
                "context_id_fresh",
                "session_id_fresh",
                "skill_hash_matches",
            },
        )

    def test_replacement_reset_fails_if_clean_target_was_not_restored(self) -> None:
        evidence = _valid_evidence()
        result = attest_reset(
            ResetEvidence(
                frozen_clean_pool_hash=evidence.frozen_clean_pool_hash,
                deployment_pool_hash=evidence.deployment_pool_hash,
                overlay_id="target",
                overlay_content_hash=evidence.overlay_content_hash,
                deployment_resource_ids={"different"},
                deployment_resource_hashes={"d" * 64},
                acquisition_runtime=evidence.acquisition_runtime,
                deployment_runtime=evidence.deployment_runtime,
                generated_skill_hash=evidence.generated_skill_hash,
                loaded_skill_hash=evidence.loaded_skill_hash,
                reset_mode="replacement_restored",
                restored_content_hash="c" * 64,
                deployment_resource_content_hashes={"different": "d" * 64},
            )
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            {check.name for check in result.failed_checks},
            {
                "target_resource_id_present",
                "clean_target_content_hash_restored_at_target_id",
            },
        )

    def test_replacement_reset_binds_clean_hash_to_target_id(self) -> None:
        evidence = _valid_evidence()
        result = attest_reset(
            ResetEvidence(
                frozen_clean_pool_hash=evidence.frozen_clean_pool_hash,
                deployment_pool_hash=evidence.deployment_pool_hash,
                overlay_id="target",
                overlay_content_hash=evidence.overlay_content_hash,
                deployment_resource_ids={"target", "other"},
                deployment_resource_hashes={"c" * 64, "d" * 64},
                deployment_resource_content_hashes={
                    "target": "d" * 64,
                    "other": "c" * 64,
                },
                acquisition_runtime=evidence.acquisition_runtime,
                deployment_runtime=evidence.deployment_runtime,
                generated_skill_hash=evidence.generated_skill_hash,
                loaded_skill_hash=evidence.loaded_skill_hash,
                reset_mode="replacement_restored",
                restored_content_hash="c" * 64,
            )
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            {check.name for check in result.failed_checks},
            {"clean_target_content_hash_restored_at_target_id"},
        )

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

    def test_skill_only_reset_attests_no_pool_exact_tools_freshness_and_skill(self) -> None:
        result = attest_reset(_valid_skill_only_evidence())

        self.assertTrue(result.passed)
        self.assertEqual(result.mode, "skill_only")
        self.assertEqual(
            {check.name for check in result.checks},
            {
                "deployment_resource_pool_absent",
                "deployment_tools_execute_finish_only",
                "world_id_fresh",
                "context_id_fresh",
                "session_id_fresh",
                "skill_hash_matches",
            },
        )

    def test_every_skill_only_reset_invariant_fails_closed(self) -> None:
        evidence = SkillOnlyResetEvidence(
            acquisition_runtime=RuntimeIdentity("same-world", "same-context", "same-session"),
            deployment_runtime=RuntimeIdentity("same-world", "same-context", "same-session"),
            generated_skill_hash="a" * 64,
            loaded_skill_hash="b" * 64,
            deployment_resource_pool_attached=True,
            exposed_tool_names=("execute", "finish", "read_doc"),
        )

        result = attest_reset(evidence)

        self.assertFalse(result.passed)
        self.assertEqual(
            {check.name for check in result.failed_checks},
            {
                "deployment_resource_pool_absent",
                "deployment_tools_execute_finish_only",
                "world_id_fresh",
                "context_id_fresh",
                "session_id_fresh",
                "skill_hash_matches",
            },
        )
        with self.assertRaises(ResetAttestationError):
            result.require_passed()

    def test_skill_only_reset_rejects_invalid_evidence_types(self) -> None:
        valid = _valid_skill_only_evidence()
        with self.assertRaisesRegex(TypeError, "deployment_resource_pool_attached must be bool"):
            SkillOnlyResetEvidence(
                acquisition_runtime=valid.acquisition_runtime,
                deployment_runtime=valid.deployment_runtime,
                generated_skill_hash=valid.generated_skill_hash,
                loaded_skill_hash=valid.loaded_skill_hash,
                deployment_resource_pool_attached=0,
                exposed_tool_names=valid.exposed_tool_names,
            )
        with self.assertRaisesRegex(ValueError, "exposed_tool_names"):
            SkillOnlyResetEvidence(
                acquisition_runtime=valid.acquisition_runtime,
                deployment_runtime=valid.deployment_runtime,
                generated_skill_hash=valid.generated_skill_hash,
                loaded_skill_hash=valid.loaded_skill_hash,
                deployment_resource_pool_attached=False,
                exposed_tool_names=("execute", ""),
            )


if __name__ == "__main__":
    unittest.main()
