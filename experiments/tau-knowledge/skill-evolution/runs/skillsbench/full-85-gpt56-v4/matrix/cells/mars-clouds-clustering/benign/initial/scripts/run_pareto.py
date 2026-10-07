#!/usr/bin/env python3
"""Grid-search weighted DBSCAN settings and write a Pareto frontier CSV.

JSON stdin schema:
  {"citizen_csv": str, "expert_csv": str, "output_csv": str, "workers": int}
All keys are optional. A JSON result is emitted on stdout; errors are emitted on stderr.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

# These are populated before a forked pool is created. Their arrays are never mutated.
_CITIZEN: Dict[object, np.ndarray] = {}
_EXPERT: Dict[object, np.ndarray] = {}
_IMAGE_IDS: List[object] = []


def read_groups(path: str, label: str) -> Dict[object, np.ndarray]:
    """Read required CSV columns and return file_rad -> finite Nx2 coordinate array."""
    try:
        frame = pd.read_csv(path, usecols=["file_rad", "x", "y"])
    except ValueError as exc:
        raise ValueError(f"{label} CSV must contain file_rad, x, and y columns") from exc
    if frame["file_rad"].isna().any():
        raise ValueError(f"{label} CSV contains missing file_rad values")
    coords = frame[["x", "y"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(coords).all():
        raise ValueError(f"{label} CSV contains non-finite x or y values")
    # sort=False preserves source order, which gives deterministic sklearn input and tie behavior.
    result: Dict[object, np.ndarray] = {}
    for image_id, indices in frame.groupby("file_rad", sort=False).groups.items():
        result[image_id] = np.ascontiguousarray(coords[np.asarray(indices)], dtype=float)
    return result


def centroids_for(points: np.ndarray, epsilon: int, min_samples: int, weight: float) -> np.ndarray:
    """Run weighted DBSCAN and return one arithmetic centroid for each non-noise label."""
    if len(points) == 0:
        return np.empty((0, 2), dtype=float)
    # Euclidean distance after this transform equals the requested weighted metric.
    scaled = points * np.array([weight, 2.0 - weight], dtype=float)
    # Deliberately call DBSCAN even if len(points) < min_samples: sklearn then supplies
    # the authoritative all-noise result.
    labels = DBSCAN(
        eps=float(epsilon), min_samples=int(min_samples), metric="euclidean",
        algorithm="ball_tree", n_jobs=1,
    ).fit_predict(scaled)
    labels = labels[labels >= 0]
    if labels.size == 0:
        return np.empty((0, 2), dtype=float)
    # Labels produced by sklearn are contiguous; unique also keeps this correct generally.
    all_labels = DBSCAN  # avoid relying on an undocumented maximum-label convention
    del all_labels
    # Recompute labels' unique values from the original assignment (not filtered points).
    # This form keeps centroids in DBSCAN label order.
    assigned = DBSCAN(
        eps=float(epsilon), min_samples=int(min_samples), metric="euclidean",
        algorithm="ball_tree", n_jobs=1,
    ).fit_predict(scaled)
    unique = np.unique(assigned[assigned >= 0])
    return np.asarray([points[assigned == lab].mean(axis=0) for lab in unique], dtype=float)


def greedy_match_distances(centroids: np.ndarray, experts: np.ndarray, threshold: float = 100.0) -> List[float]:
    """Globally greedy one-to-one Euclidean matches, retaining accepted distances."""
    if len(centroids) == 0 or len(experts) == 0:
        return []
    diff = centroids[:, None, :] - experts[None, :, :]
    distances = np.sqrt(np.sum(diff * diff, axis=2))
    matches: List[float] = []
    # np.argmin uses row-major first occurrence for exact ties, consistently selecting
    # the global minimum before either endpoint is removed.
    while distances.size:
        flat_index = int(np.argmin(distances))
        distance = float(distances.flat[flat_index])
        if not math.isfinite(distance) or distance >= threshold:
            break
        row, col = np.unravel_index(flat_index, distances.shape)
        matches.append(distance)
        distances[row, :] = np.inf
        distances[:, col] = np.inf
    return matches


def evaluate_setting(setting: Tuple[int, int, float]) -> Tuple[float, float, int, int, float]:
    """Return full-precision (F1, delta, min_samples, epsilon, shape_weight)."""
    min_samples, epsilon, weight = setting
    image_f1: List[float] = []
    image_delta: List[float] = []
    for image_id in _IMAGE_IDS:
        experts = _EXPERT[image_id]
        points = _CITIZEN.get(image_id)
        if points is None:
            centroids = np.empty((0, 2), dtype=float)
        else:
            centroids = centroids_for(points, epsilon, min_samples, weight)
        matched = greedy_match_distances(centroids, experts)
        tp = len(matched)
        # With at least one expert point for each iterated image, this denominator is
        # nonzero. This expression also correctly assigns zero when tp is zero.
        denom = len(centroids) + len(experts)
        image_f1.append((2.0 * tp / denom) if tp else 0.0)
        if matched:
            image_delta.append(float(np.mean(matched)))
    f1 = float(np.mean(image_f1)) if image_f1 else 0.0
    delta = float(np.mean(image_delta)) if image_delta else float("nan")
    return f1, delta, min_samples, epsilon, weight


def pareto_mask(records: Sequence[Tuple[float, float, int, int, float]]) -> np.ndarray:
    """Mark points not dominated under maximize-F1/minimize-delta objectives."""
    values = np.asarray([(record[0], record[1]) for record in records], dtype=float)
    keep = np.ones(len(records), dtype=bool)
    for i, (f1, delta) in enumerate(values):
        dominates = (
            (values[:, 0] >= f1)
            & (values[:, 1] <= delta)
            & ((values[:, 0] > f1) | (values[:, 1] < delta))
        )
        if np.any(dominates):
            keep[i] = False
    return keep


def write_frontier(path: str, records: Sequence[Tuple[float, float, int, int, float]]) -> None:
    """Atomically write formatted output, then verify its schema and row count."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: (-r[0], r[1], r[2], r[3], r[4]))
    fd, temporary = tempfile.mkstemp(prefix=".pareto-", suffix=".csv", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["F1", "delta", "min_samples", "epsilon", "shape_weight"])
            for f1, delta, min_samples, epsilon, weight in ordered:
                writer.writerow([
                    f"{f1:.5f}", f"{delta:.5f}", str(int(min_samples)),
                    str(int(epsilon)), f"{weight:.1f}",
                ])
        os.replace(temporary, destination)
        with destination.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        expected = ["F1", "delta", "min_samples", "epsilon", "shape_weight"]
        if not rows or rows[0] != expected or len(rows) - 1 != len(ordered):
            raise RuntimeError("output CSV validation failed")
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    raw = sys.stdin.read()
    config = json.loads(raw) if raw.strip() else {}
    if not isinstance(config, dict):
        raise ValueError("stdin JSON must be an object")
    citizen_path = str(config.get("citizen_csv", "/root/data/citsci_train.csv"))
    expert_path = str(config.get("expert_csv", "/root/data/expert_train.csv"))
    output_path = str(config.get("output_csv", "/root/pareto_frontier.csv"))
    workers = int(config.get("workers", min(4, os.cpu_count() or 1)))
    if workers < 1:
        raise ValueError("workers must be a positive integer")

    global _CITIZEN, _EXPERT, _IMAGE_IDS
    _CITIZEN = read_groups(citizen_path, "citizen")
    _EXPERT = read_groups(expert_path, "expert")
    _IMAGE_IDS = list(_EXPERT.keys())
    if not _IMAGE_IDS:
        raise ValueError("expert CSV has no images to evaluate")

    settings = [
        (minimum, epsilon, round(0.9 + 0.1 * weight_index, 1))
        for minimum in range(3, 10)
        for epsilon in range(4, 25, 2)
        for weight_index in range(11)
    ]
    if workers == 1:
        results = [evaluate_setting(setting) for setting in settings]
    else:
        # Docker/Linux uses fork, so already loaded read-only point arrays are shared
        # copy-on-write rather than serialized once per grid setting.
        import multiprocessing as mp
        try:
            context = mp.get_context("fork")
        except ValueError:
            context = None
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            results = list(pool.map(evaluate_setting, settings, chunksize=1))

    eligible = [record for record in results if record[0] > 0.5 and math.isfinite(record[1])]
    frontier = [record for record, keep in zip(eligible, pareto_mask(eligible)) if keep]
    write_frontier(output_path, frontier)
    print(json.dumps({
        "output_csv": output_path,
        "evaluated": len(results),
        "filtered": len(eligible),
        "pareto_rows": len(frontier),
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
