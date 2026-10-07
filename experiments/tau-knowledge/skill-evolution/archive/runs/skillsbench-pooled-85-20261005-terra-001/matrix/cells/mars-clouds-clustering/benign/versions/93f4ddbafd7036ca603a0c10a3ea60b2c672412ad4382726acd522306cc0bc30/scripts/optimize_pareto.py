#!/usr/bin/env python3
"""Run the Mars annotation DBSCAN grid search and write a Pareto CSV.

Reads a JSON configuration from stdin and writes a JSON status object to stdout.
"""
import csv
import json
import math
import os
import sys
import tempfile
import traceback
from itertools import product
from multiprocessing import get_context

# Each outer worker evaluates one complete configuration. Prevent native
# neighbor-search libraries from multiplying that parallelism with threads.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

DEFAULT_CITSCI = "/root/data/citsci_train.csv"
DEFAULT_EXPERT = "/root/data/expert_train.csv"
DEFAULT_OUTPUT = "/root/pareto_frontier.csv"
MATCH_DISTANCE = 100.0

# Set in workers by _worker_init. An entry is (citizen_xy, expert_xy), and the
# entry order is the order of expert file_rad groups.
_IMAGES = None


def _worker_init(images):
    global _IMAGES
    _IMAGES = images


def centroids_from_dbscan(points, epsilon, min_samples, weight):
    """Return original-coordinate centroids of all non-noise DBSCAN clusters."""
    if len(points) == 0:
        # sklearn rejects a zero-row matrix; its meaningful clustering result is
        # nevertheless zero clusters. Nonempty small inputs always reach DBSCAN.
        return np.empty((0, 2), dtype=np.float64)

    scale = np.array([weight, 2.0 - weight], dtype=np.float64)
    labels = DBSCAN(
        eps=float(epsilon),
        min_samples=int(min_samples),
        metric="euclidean",
        algorithm="auto",
        n_jobs=1,
    ).fit_predict(points * scale)
    cluster_labels = np.unique(labels[labels >= 0])
    if len(cluster_labels) == 0:
        return np.empty((0, 2), dtype=np.float64)
    return np.vstack([points[labels == label].mean(axis=0) for label in cluster_labels])


def greedy_match(centroids, experts):
    """Return (TP, mean_matched_standard_euclidean_distance).

    At every iteration this selects one global minimum among all still available
    centroid/expert pairs. Distances exactly 100 are not matches.
    """
    if len(centroids) == 0 or len(experts) == 0:
        return 0, math.nan

    delta = centroids[:, None, :] - experts[None, :, :]
    distances = np.sqrt(np.sum(delta * delta, axis=2))
    remaining_centroids = np.ones(len(centroids), dtype=bool)
    remaining_experts = np.ones(len(experts), dtype=bool)
    matched_distances = []

    while remaining_centroids.any() and remaining_experts.any():
        available = distances.copy()
        available[~remaining_centroids, :] = np.inf
        available[:, ~remaining_experts] = np.inf
        flat_index = int(np.argmin(available))
        distance = float(available.flat[flat_index])
        if not math.isfinite(distance) or distance >= MATCH_DISTANCE:
            break
        centroid_index, expert_index = np.unravel_index(flat_index, available.shape)
        matched_distances.append(distance)
        remaining_centroids[centroid_index] = False
        remaining_experts[expert_index] = False

    if not matched_distances:
        return 0, math.nan
    return len(matched_distances), float(np.mean(matched_distances))


def evaluate_configuration(task):
    """Evaluate one (min_samples, epsilon, shape_weight) tuple over all images."""
    min_samples, epsilon, weight = task
    f1_values = []
    image_deltas = []
    for citizen_points, expert_points in _IMAGES:
        centroids = centroids_from_dbscan(citizen_points, epsilon, min_samples, weight)
        matches, image_delta = greedy_match(centroids, expert_points)
        # This form is algebraically the requested precision/recall F1 and also
        # safely gives zero when no matches were made.
        denominator = len(centroids) + len(expert_points)
        f1_values.append(0.0 if matches == 0 else (2.0 * matches / denominator))
        if matches:
            image_deltas.append(image_delta)

    average_f1 = float(np.mean(f1_values))
    average_delta = float(np.mean(image_deltas)) if image_deltas else math.inf
    return {
        "F1": average_f1,
        "delta": average_delta,
        "min_samples": int(min_samples),
        "epsilon": int(epsilon),
        "shape_weight": float(weight),
    }


def require_columns_and_values(frame, path):
    required = ["file_rad", "x", "y"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
    if frame["file_rad"].isna().any():
        raise ValueError(f"{path} has missing file_rad values")
    for column in ("x", "y"):
        numeric = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=np.float64)
        if not np.isfinite(numeric).all():
            raise ValueError(f"{path} has non-finite {column} coordinates")
        frame[column] = numeric


def build_images(citizen_frame, expert_frame):
    """Pre-group point arrays for precisely the images that experts identify."""
    expert_groups = []
    expert_keys = set()
    for key, group in expert_frame.groupby("file_rad", sort=False):
        expert_keys.add(key)
        expert_groups.append((key, group[["x", "y"]].to_numpy(dtype=np.float64, copy=True)))
    if not expert_groups:
        raise ValueError("expert CSV contains no images")

    # Citizen records for images with no expert group can never affect the
    # requested all-expert-image evaluation, so omit them before grouping.
    citizen_subset = citizen_frame[citizen_frame["file_rad"].isin(expert_keys)]
    citizen_by_key = {
        key: group[["x", "y"]].to_numpy(dtype=np.float64, copy=True)
        for key, group in citizen_subset.groupby("file_rad", sort=False)
    }
    empty = np.empty((0, 2), dtype=np.float64)
    return [(citizen_by_key.get(key, empty), expert_points) for key, expert_points in expert_groups]


def pareto_mask(rows):
    """True for rows not dominated on max F1/min delta using full precision."""
    f1 = np.asarray([row["F1"] for row in rows], dtype=np.float64)
    delta = np.asarray([row["delta"] for row in rows], dtype=np.float64)
    keep = np.ones(len(rows), dtype=bool)
    for index in range(len(rows)):
        dominates = (
            (f1 >= f1[index])
            & (delta <= delta[index])
            & ((f1 > f1[index]) | (delta < delta[index]))
        )
        if np.any(dominates):
            keep[index] = False
    return keep


def validate_search(rows, filtered, frontier):
    if len(rows) != 7 * 11 * 11:
        raise RuntimeError(f"incomplete grid: expected 847 results, got {len(rows)}")
    parameter_keys = {(r["min_samples"], r["epsilon"], r["shape_weight"]) for r in rows}
    if len(parameter_keys) != 847:
        raise RuntimeError("grid contains duplicate or missing parameter tuples")
    if any(not (r["F1"] > 0.5 and math.isfinite(r["delta"])) for r in filtered):
        raise RuntimeError("filtered results violate F1/delta eligibility")
    if frontier:
        expected = pareto_mask(filtered)
        expected_keys = {
            (filtered[i]["min_samples"], filtered[i]["epsilon"], filtered[i]["shape_weight"])
            for i in np.flatnonzero(expected)
        }
        actual_keys = {(r["min_samples"], r["epsilon"], r["shape_weight"]) for r in frontier}
        if actual_keys != expected_keys:
            raise RuntimeError("frontier validation failed")


def write_csv(path, frontier):
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        raise ValueError(f"output directory does not exist: {parent}")
    ordered = sorted(
        frontier,
        key=lambda row: (-row["F1"], row["delta"], row["min_samples"], row["epsilon"], row["shape_weight"]),
    )
    fd, temporary_path = tempfile.mkstemp(prefix=".pareto_frontier_", suffix=".csv", dir=parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["F1", "delta", "min_samples", "epsilon", "shape_weight"])
            for row in ordered:
                writer.writerow([
                    f'{row["F1"]:.5f}',
                    f'{row["delta"]:.5f}',
                    str(row["min_samples"]),
                    str(row["epsilon"]),
                    f'{row["shape_weight"]:.1f}',
                ])
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def main(config):
    if not isinstance(config, dict):
        raise ValueError("stdin JSON must be an object")
    citizen_path = config.get("citsci_path", DEFAULT_CITSCI)
    expert_path = config.get("expert_path", DEFAULT_EXPERT)
    output_path = config.get("output_path", DEFAULT_OUTPUT)
    n_jobs = config.get("n_jobs", 4)
    if not isinstance(n_jobs, int) or isinstance(n_jobs, bool) or n_jobs < 1:
        raise ValueError("n_jobs must be a positive integer")
    if not all(isinstance(value, str) and value for value in (citizen_path, expert_path, output_path)):
        raise ValueError("CSV and output paths must be nonempty strings")

    citizen_frame = pd.read_csv(citizen_path)
    expert_frame = pd.read_csv(expert_path)
    require_columns_and_values(citizen_frame, citizen_path)
    require_columns_and_values(expert_frame, expert_path)
    images = build_images(citizen_frame, expert_frame)

    weights = [round(0.9 + 0.1 * i, 1) for i in range(11)]
    tasks = list(product(range(3, 10), range(4, 25, 2), weights))
    if n_jobs == 1:
        _worker_init(images)
        rows = [evaluate_configuration(task) for task in tasks]
    else:
        # fork is available in the declared Linux runtime and efficiently shares
        # the read-only, pre-grouped arrays until a worker needs private memory.
        context = get_context("fork")
        with context.Pool(processes=n_jobs, initializer=_worker_init, initargs=(images,)) as pool:
            rows = list(pool.imap_unordered(evaluate_configuration, tasks, chunksize=1))

    filtered = [row for row in rows if row["F1"] > 0.5 and math.isfinite(row["delta"])]
    mask = pareto_mask(filtered)
    frontier = [row for row, selected in zip(filtered, mask) if selected]
    validate_search(rows, filtered, frontier)
    write_csv(output_path, frontier)
    return {
        "ok": True,
        "output_path": output_path,
        "expert_images": len(images),
        "evaluated_combinations": len(rows),
        "filtered_combinations": len(filtered),
        "frontier_combinations": len(frontier),
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        config = json.loads(raw) if raw.strip() else {}
        print(json.dumps(main(config), sort_keys=True), flush=True)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}), flush=True)
        sys.exit(1)
