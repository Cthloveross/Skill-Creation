from __future__ import annotations

import subprocess

import pytest
from tau_skill_evolution.core.attack_payload import ATTACK_COMMANDS
from tau_skill_evolution.sidecar import DeleteSentinelSidecar, DualCommandSidecar, SidecarError


def test_canary_requires_actual_exact_dispatch_and_fresh_episode(monkeypatch):
    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: pytest.fail("canary cannot use a shell")
    )
    for episode in ("one", "two"):
        with DualCommandSidecar(episode) as sidecar:
            text = ATTACK_COMMANDS["mock-api-call"]
            assert text and sidecar.hits == {"mock-api-call": False, "delete-sentinel": False}
            with pytest.raises(SidecarError, match="allowlist"):
                sidecar.run_command(text + "; extra-command")
            assert not sidecar.hit
            assert sidecar.run_command(text) == {"recorded": True}
            with pytest.raises(SidecarError, match="already"):
                sidecar.run_command(text)
            assert sidecar.run_command(ATTACK_COMMANDS["delete-sentinel"])["deleted"]
            assert all(sidecar.hits.values())
            assert len(sidecar.events) == 2


def test_delete_canary_rejects_wrong_nonce_and_replaced_inode_without_touching_external_file(
    tmp_path,
):
    outside = tmp_path / "outside"
    outside.write_text("keep me")
    with DeleteSentinelSidecar("nonce", "episode") as sidecar:
        with pytest.raises(SidecarError, match="nonce"):
            sidecar.delete("wrong")
        sidecar._sentinel.unlink()
        sidecar._sentinel.symlink_to(outside)
        with pytest.raises(SidecarError, match="identity"):
            sidecar.delete("nonce")
        assert not sidecar.hit and outside.read_text() == "keep me"
        assert sidecar.evidence["path_argument_accepted"] is False
