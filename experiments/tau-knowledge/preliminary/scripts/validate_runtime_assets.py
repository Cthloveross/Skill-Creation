#!/usr/bin/env python3
"""Validate the frozen Flash-Next, dense-retriever, and SIF assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

MODEL_REVISION = "236dfdf285828023ca3bcd3f37366c58a3469b13"
MODEL_TENSOR_BYTES = 185_502_232_570
MODEL_SHARD_BYTES = 185_523_317_458
MODEL_SHARDS = 131
MODEL_ARTIFACTS = {
    "LICENSE": "a0dc422560841fd68e06d974907f8b4c709bca44a67daad2b528437bdf676c08",
    "chat_template.jinja": ("c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041"),
    "config.json": "c22eb0a053eed62e18f0184d3ca62d3798f208c3e00b9feee939fc3dbacdc8ca",
    "generation_config.json": ("e70c136c1b78ddc1fb0905bac8e733a4dc448d4f852a5dd75143fffc70be550e"),
    "model.safetensors.index.json": (
        "0419e2c2dfbb925257d7409405433a793cf7ff7d96f3eba882a815ec6d9fe7a6"
    ),
    "tokenizer.json": ("0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"),
    "tokenizer_config.json": ("b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27"),
}

DENSE_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
DENSE_WEIGHT_BYTES = 1_191_586_416
DENSE_ARTIFACTS = {
    "config.json": "b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9",
    "model.safetensors": ("0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"),
    "tokenizer.json": ("def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a"),
    "tokenizer_config.json": ("253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0"),
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHARD_RE = re.compile(r"^model-[0-9]{5}-of-00131\.safetensors$")


class AssetError(RuntimeError):
    """A required runtime asset is missing or does not match its commitment."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shard_hash_workers() -> int:
    """Use only explicitly allocated Slurm CPUs, with a bounded I/O footprint."""
    if not (os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_JOBID")):
        return 1
    try:
        allocated_cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
    except ValueError:
        return 1
    return max(1, min(8, allocated_cpus))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _regular_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise AssetError(f"required regular file is missing: {path}")
    return path


def _revision(root: Path) -> str:
    metadata = _regular_file(
        root,
        ".cache/huggingface/download/config.json.metadata",
    )
    try:
        revision = metadata.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError) as exc:
        raise AssetError(f"revision metadata is unreadable: {metadata}") from exc
    return revision


def _validate_artifacts(root: Path, expected: dict[str, str]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected_sha256 in sorted(expected.items()):
        path = _regular_file(root, relative)
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise AssetError(f"artifact SHA-256 mismatch: {path}")
        observed[relative] = actual_sha256
    return observed


def _validate_main_model(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise AssetError(f"main model snapshot is missing: {root}")
    if _revision(root) != MODEL_REVISION:
        raise AssetError("main model revision mismatch")
    artifacts = _validate_artifacts(root, MODEL_ARTIFACTS)
    index = json.loads((root / "model.safetensors.index.json").read_bytes())
    if index.get("metadata", {}).get("total_size") != MODEL_TENSOR_BYTES:
        raise AssetError("main model index total_size mismatch")
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise AssetError("main model index has no weight_map")
    shard_names = sorted(set(weight_map.values()))
    if len(shard_names) != MODEL_SHARDS or any(
        not isinstance(name, str) or _SHARD_RE.fullmatch(name) is None for name in shard_names
    ):
        raise AssetError("main model shard inventory mismatch")

    shard_inputs: list[tuple[Path, str]] = []
    for name in shard_names:
        path = _regular_file(root, name)
        metadata = _regular_file(root, f".cache/huggingface/download/{name}.metadata")
        try:
            lines = metadata.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise AssetError(f"main model shard metadata is unreadable: {metadata}") from exc
        if len(lines) < 2 or lines[0] != MODEL_REVISION or _SHA256_RE.fullmatch(lines[1]) is None:
            raise AssetError(f"main model shard metadata mismatch: {metadata}")
        shard_inputs.append((path, lines[1]))

    workers = _shard_hash_workers()
    paths = [path for path, _expected_sha256 in shard_inputs]
    if workers == 1:
        digests = [_sha256_file(path) for path in paths]
    else:
        # Only digest computation runs concurrently. map preserves the sorted
        # inventory order, so commitments and validation reports stay identical.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            digests = list(executor.map(_sha256_file, paths))

    shard_records: list[dict[str, Any]] = []
    serialized_size = 0
    for (path, expected_sha256), actual_sha256 in zip(shard_inputs, digests, strict=True):
        if actual_sha256 != expected_sha256:
            raise AssetError(f"main model shard content SHA-256 mismatch: {path}")
        size = path.stat().st_size
        shard_records.append(
            {
                "path": path.name,
                "lfs_sha256": expected_sha256,
                "serialized_size_bytes": size,
            }
        )
        serialized_size += size
    if serialized_size != MODEL_SHARD_BYTES:
        raise AssetError("main model serialized shard size mismatch")

    commitment = {
        "revision": MODEL_REVISION,
        "weight_tensor_bytes": MODEL_TENSOR_BYTES,
        "serialized_shard_bytes": MODEL_SHARD_BYTES,
        "artifacts": artifacts,
        "shards": shard_records,
    }
    return {
        "root": str(root),
        "revision": MODEL_REVISION,
        "snapshot_sha256": _canonical_sha256(commitment),
        "weight_shards": MODEL_SHARDS,
        "weight_tensor_bytes": MODEL_TENSOR_BYTES,
        "serialized_shard_bytes": MODEL_SHARD_BYTES,
        "weight_content_hashes_verified": True,
    }


def _validate_dense_model(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise AssetError(f"dense model snapshot is missing: {root}")
    if _revision(root) != DENSE_REVISION:
        raise AssetError("dense model revision mismatch")
    artifacts = _validate_artifacts(root, DENSE_ARTIFACTS)
    if (root / "model.safetensors").stat().st_size != DENSE_WEIGHT_BYTES:
        raise AssetError("dense model weight size mismatch")
    commitment = {
        "revision": DENSE_REVISION,
        "weight_bytes": DENSE_WEIGHT_BYTES,
        "artifacts": artifacts,
    }
    return {
        "root": str(root),
        "revision": DENSE_REVISION,
        "snapshot_sha256": _canonical_sha256(commitment),
        "weight_bytes": DENSE_WEIGHT_BYTES,
    }


def validate(
    *,
    model_root: Path,
    dense_model_root: Path,
    sif_path: Path,
    expected_sif_sha256: str | None,
) -> dict[str, Any]:
    model_root = model_root.expanduser()
    dense_model_root = dense_model_root.expanduser()
    sif_path = sif_path.expanduser()
    if model_root.is_symlink() or dense_model_root.is_symlink() or sif_path.is_symlink():
        raise AssetError("runtime asset roots must not be symbolic links")
    model_root = model_root.resolve(strict=True)
    dense_model_root = dense_model_root.resolve(strict=True)
    sif_path = sif_path.resolve(strict=True)
    if not sif_path.is_file():
        raise AssetError(f"SIF is missing or is not a regular file: {sif_path}")
    if expected_sif_sha256 is not None and _SHA256_RE.fullmatch(expected_sif_sha256) is None:
        raise AssetError("expected SIF SHA-256 must be lowercase hexadecimal")
    sif_sha256 = _sha256_file(sif_path)
    if expected_sif_sha256 is not None and sif_sha256 != expected_sif_sha256:
        raise AssetError("SIF SHA-256 mismatch")
    return {
        "schema_version": "r2sp.tau-runtime-assets.v1",
        "model": _validate_main_model(model_root),
        "dense_model": _validate_dense_model(dense_model_root),
        "sif": {"path": str(sif_path), "sha256": sif_sha256},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--dense-model-root", type=Path, required=True)
    parser.add_argument("--sif-path", type=Path, required=True)
    parser.add_argument("--expected-sif-sha256")
    arguments = parser.parse_args()
    try:
        result = validate(
            model_root=arguments.model_root,
            dense_model_root=arguments.dense_model_root,
            sif_path=arguments.sif_path,
            expected_sif_sha256=arguments.expected_sif_sha256,
        )
    except (AssetError, OSError, json.JSONDecodeError) as exc:
        error = json.dumps({"status": "INVALID", "reason": str(exc)}, sort_keys=True)
        print(error, file=sys.stderr)
        return 2
    print(json.dumps({"status": "SUCCESS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
