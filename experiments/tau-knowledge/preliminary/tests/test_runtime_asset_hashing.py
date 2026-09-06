from __future__ import annotations

import hashlib
import importlib
import json
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture
def assets(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    for name in ("SLURM_JOB_ID", "SLURM_JOBID", "SLURM_CPUS_PER_TASK"):
        monkeypatch.delenv(name, raising=False)
    return importlib.import_module("validate_runtime_assets")


@pytest.fixture
def tiny_model(
    assets: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, list[str]]:
    root = tmp_path / "model"
    metadata = root / ".cache/huggingface/download"
    metadata.mkdir(parents=True)
    (metadata / "config.json.metadata").write_text(assets.MODEL_REVISION + "\n")
    names = [f"model-{number:05d}-of-00131.safetensors" for number in range(1, 4)]
    total_size = 0
    for number, name in enumerate(names):
        content = f"tiny weight shard {number}".encode()
        (root / name).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        (metadata / f"{name}.metadata").write_text(f"{assets.MODEL_REVISION}\n{digest}\n")
        total_size += len(content)
    index = {
        "metadata": {"total_size": 42},
        "weight_map": {f"tensor-{number}": name for number, name in enumerate(reversed(names))},
    }
    index_bytes = json.dumps(index).encode()
    (root / "model.safetensors.index.json").write_bytes(index_bytes)
    monkeypatch.setattr(assets, "MODEL_SHARDS", len(names))
    monkeypatch.setattr(assets, "MODEL_TENSOR_BYTES", 42)
    monkeypatch.setattr(assets, "MODEL_SHARD_BYTES", total_size)
    monkeypatch.setattr(
        assets,
        "MODEL_ARTIFACTS",
        {"model.safetensors.index.json": hashlib.sha256(index_bytes).hexdigest()},
    )
    return root, names


@pytest.mark.parametrize(
    ("job_variable", "allocation", "expected"),
    [
        (None, None, 1),
        (None, "8", 1),
        ("SLURM_JOB_ID", None, 1),
        ("SLURM_JOB_ID", "", 1),
        ("SLURM_JOB_ID", "invalid", 1),
        ("SLURM_JOB_ID", "0", 1),
        ("SLURM_JOB_ID", "-2", 1),
        ("SLURM_JOB_ID", "1", 1),
        ("SLURM_JOB_ID", "2", 2),
        ("SLURM_JOB_ID", "8", 8),
        ("SLURM_JOB_ID", "64", 8),
        ("SLURM_JOBID", "4", 4),
    ],
)
def test_hash_workers_stay_within_slurm_allocation(
    assets: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    job_variable: str | None,
    allocation: str | None,
    expected: int,
) -> None:
    if job_variable is not None:
        monkeypatch.setenv(job_variable, "12345")
    if allocation is not None:
        monkeypatch.setenv("SLURM_CPUS_PER_TASK", allocation)
    assert assets._shard_hash_workers() == expected


def test_parallel_hashes_preserve_serial_commitment_and_report_order(
    assets: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tiny_model: tuple[Path, list[str]],
) -> None:
    root, names = tiny_model
    serial_report = assets._validate_main_model(root)
    original_digest = assets._sha256_file
    original_commitment = assets._canonical_sha256
    second_finished = threading.Event()
    completed: list[str] = []
    commitments: list[dict[str, Any]] = []

    def out_of_order_digest(path: Path) -> str:
        if path.name == names[0]:
            assert second_finished.wait(timeout=5), "second shard did not hash concurrently"
        result = original_digest(path)
        if path.name in names:
            completed.append(path.name)
        if path.name == names[1]:
            second_finished.set()
        return result

    def record_commitment(value: dict[str, Any]) -> str:
        commitments.append(value)
        return original_commitment(value)

    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "2")
    monkeypatch.setattr(assets, "_sha256_file", out_of_order_digest)
    monkeypatch.setattr(assets, "_canonical_sha256", record_commitment)
    assert assets._validate_main_model(root) == serial_report
    assert completed.index(names[1]) < completed.index(names[0])
    assert sorted(completed) == names
    assert [row["path"] for row in commitments[0]["shards"]] == names


@pytest.mark.parametrize("workers", [1, 2, 8])
def test_parallel_content_hash_rejects_same_size_corruption(
    assets: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tiny_model: tuple[Path, list[str]],
    workers: int,
) -> None:
    root, names = tiny_model
    path = root / names[1]
    path.write_bytes(b"x" * path.stat().st_size)
    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", str(workers))
    with pytest.raises(assets.AssetError, match="shard content SHA-256 mismatch"):
        assets._validate_main_model(root)


@pytest.mark.parametrize("failure", ["revision", "lfs_metadata", "size", "artifact"])
def test_parallel_hashing_keeps_other_asset_commitment_checks(
    assets: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tiny_model: tuple[Path, list[str]],
    failure: str,
) -> None:
    root, names = tiny_model
    metadata = root / ".cache/huggingface/download"
    if failure == "revision":
        (metadata / "config.json.metadata").write_text("wrong-revision\n")
        expected = "main model revision mismatch"
    elif failure == "lfs_metadata":
        (metadata / f"{names[0]}.metadata").write_text(f"{assets.MODEL_REVISION}\ninvalid\n")
        expected = "shard metadata mismatch"
    elif failure == "size":
        monkeypatch.setattr(assets, "MODEL_SHARD_BYTES", assets.MODEL_SHARD_BYTES + 1)
        expected = "serialized shard size mismatch"
    else:
        index = root / "model.safetensors.index.json"
        index.write_bytes(index.read_bytes() + b" ")
        expected = "artifact SHA-256 mismatch"
    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "8")
    with pytest.raises(assets.AssetError, match=expected):
        assets._validate_main_model(root)


def test_non_slurm_validation_does_not_create_thread_pool(
    assets: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tiny_model: tuple[Path, list[str]],
) -> None:
    def forbidden_pool(**_kwargs: Any) -> None:
        raise AssertionError("outside Slurm, shard hashing must stay in the calling thread")

    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "8")
    monkeypatch.setattr(assets, "ThreadPoolExecutor", forbidden_pool)
    assert assets._validate_main_model(tiny_model[0])["weight_content_hashes_verified"] is True
