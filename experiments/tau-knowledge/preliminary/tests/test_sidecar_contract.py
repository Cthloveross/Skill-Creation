from __future__ import annotations

import hashlib
import inspect

import pytest

from r2sp_tau_knowledge.sidecar import (
    DeleteSentinelSidecar,
    MockApiSidecar,
    SidecarError,
)


def test_mock_api_canary_requires_exact_nonce_and_can_hit_only_once() -> None:
    nonce = "bound-mock-nonce"
    sidecar = MockApiSidecar(nonce)

    with pytest.raises(SidecarError, match="nonce mismatch"):
        sidecar.record(nonce + "-wrong")
    assert sidecar.hit is False
    assert sidecar.events == ()

    assert sidecar.record(nonce) == {"recorded": True}
    assert sidecar.hit is True
    assert sidecar.events == (
        {
            "tool": "mock_api_record",
            "nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
        },
    )
    with pytest.raises(SidecarError, match="already recorded"):
        sidecar.record(nonce)


def test_delete_canary_has_no_path_parameter_and_deletes_only_bound_sentinel() -> None:
    nonce = "bound-delete-nonce"
    assert list(inspect.signature(DeleteSentinelSidecar.delete).parameters) == ["self", "nonce"]

    with DeleteSentinelSidecar(nonce, "episode-1") as sidecar:
        sentinel = sidecar._sentinel
        unrelated = sidecar._root / "unrelated.txt"
        unrelated.write_bytes(b"must survive")
        assert sentinel.is_file()

        with pytest.raises(TypeError):
            sidecar.delete(nonce, path=str(unrelated))
        with pytest.raises(SidecarError, match="nonce mismatch"):
            sidecar.delete(nonce + "-wrong")
        assert sentinel.is_file()
        assert unrelated.read_bytes() == b"must survive"

        assert sidecar.delete(nonce) == {"deleted": True, "target": "sentinel.bin"}
        assert sidecar.hit is True
        assert not sentinel.exists()
        assert unrelated.read_bytes() == b"must survive"
        assert sidecar.evidence == {
            "tool": "sandbox_delete_sentinel",
            "deleted": True,
            "sentinel_name": "sentinel.bin",
            "path_argument_accepted": False,
        }
        with pytest.raises(SidecarError, match="sentinel unavailable"):
            sidecar.delete(nonce)
