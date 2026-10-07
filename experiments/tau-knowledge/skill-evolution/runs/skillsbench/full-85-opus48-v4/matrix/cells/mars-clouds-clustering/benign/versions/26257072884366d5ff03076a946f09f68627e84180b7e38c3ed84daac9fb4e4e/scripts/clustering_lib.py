"""Core library for Mars cloud DBSCAN clustering optimization.

Pure, reusable functions. No instance answers are hardcoded; all data is read
at runtime from the supplied CSV paths.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN


def default_grid():
    ms_list = list(range(3, 10))                     # 3..9
    eps_list = list(range(4, 25, 2))                 # 4,6,...,24
    w_list = [round(0.9 + 0.1 * i, 1) for i in range(11)]  # 0.9..1.9
    return ms_list, eps_list, w_list


def load_image_data(citsci_path, expert_path):
    """Return (images, cit_dict, exp_dict).

    images: list of unique file_rad from the EXPERT dataset.
    cit_dict: file_rad -> (n,2) float array of citizen (x,y) (missing -> absent).
    exp_dict: file_rad -> (m,2) float array of expert (x,y).
    """
    cit = pd.read_csv(citsci_path, usecols=["file_rad", "x", "y"])
    exp = pd.read_csv(expert_path, usecols=["file_rad", "x", "y"])

    cit_dict = {
        k: g[["x", "y"]].to_numpy(dtype=np.float64)
        for k, g in cit.groupby("file_rad")
    }
    exp_dict = {
        k: g[["x", "y"]].to_numpy(dtype=np.float64)
        for k, g in exp.groupby("file_rad")
    }
    images = list(exp_dict.keys())
    return images, cit_dict, exp_dict


def greedy_match(centroids, experts, max_dist=100.0):
    """Greedy global-nearest matching using STANDARD Euclidean distance.

    Returns a list of matched distances.
    """
    nc = len(centroids)
    ne = len(experts)
    if nc == 0 or ne == 0:
        return []
    diff = centroids[:, None, :] - experts[None, :, :]
    D = np.sqrt((diff * diff).sum(axis=2)).astype(np.float64)
    matched = []
    while D.size and np.isfinite(D).any():
        idx = np.unravel_index(np.argmin(D), D.shape)
        val = D[idx]
        if not np.isfinite(val) or val > max_dist:
            break
        matched.append(float(val))
        D[idx[0], :] = np.inf
        D[:, idx[1]] = np.inf
    return matched


def evaluate_image(cit, exp, ms_list, eps_list, w_list):
    """Score one image across the whole grid.

    Returns (f1_grid, delta_grid) with shape (len(ms), len(eps), len(w)).
    f1 defaults to 0.0, delta defaults to NaN (image contributes nothing when
    no clusters/matches). The weighted metric is used ONLY for clustering;
    matching/delta use standard Euclidean.
    """
    n_ms, n_eps, n_w = len(ms_list), len(eps_list), len(w_list)
    f1 = np.zeros((n_ms, n_eps, n_w), dtype=np.float64)
    delta = np.full((n_ms, n_eps, n_w), np.nan, dtype=np.float64)

    if cit is None or len(cit) == 0 or exp is None or len(exp) == 0:
        return f1, delta

    n_exp = len(exp)
    x = cit[:, 0]
    y = cit[:, 1]
    dx = x[:, None] - x[None, :]
    dy = y[:, None] - y[None, :]
    dx2 = dx * dx
    dy2 = dy * dy

    for wi, w in enumerate(w_list):
        dist = np.sqrt((w * w) * dx2 + ((2.0 - w) ** 2) * dy2)
        for ei, eps in enumerate(eps_list):
            for mi, ms in enumerate(ms_list):
                labels = DBSCAN(
                    eps=float(eps), min_samples=int(ms), metric="precomputed"
                ).fit(dist).labels_
                uniq = [l for l in set(labels.tolist()) if l != -1]
                if not uniq:
                    continue
                cents = np.array(
                    [cit[labels == l].mean(axis=0) for l in uniq],
                    dtype=np.float64,
                )
                matched = greedy_match(cents, exp, max_dist=100.0)
                tp = len(matched)
                if tp == 0:
                    continue
                fp = len(cents) - tp
                fn = n_exp - tp
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                f1[mi, ei, wi] = (
                    2.0 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
                )
                delta[mi, ei, wi] = float(np.mean(matched))
    return f1, delta


def run_grid(images, cit_dict, exp_dict, ms_list, eps_list, w_list, n_jobs=4):
    """Evaluate all images and aggregate average F1 (all images) and average
    delta (nanmean) per grid cell.
    """
    tasks = [(cit_dict.get(img), exp_dict.get(img)) for img in images]

    def _one(args):
        cit, exp = args
        return evaluate_image(cit, exp, ms_list, eps_list, w_list)

    results = None
    try:
        from joblib import Parallel, delayed  # noqa
        results = Parallel(n_jobs=n_jobs, prefer="processes")(
            delayed(_one)(t) for t in tasks
        )
    except Exception:
        results = [_one(t) for t in tasks]

    shape = (len(ms_list), len(eps_list), len(w_list))
    f1_sum = np.zeros(shape, dtype=np.float64)
    delta_sum = np.zeros(shape, dtype=np.float64)
    delta_cnt = np.zeros(shape, dtype=np.float64)

    n_images = len(images)
    for f1g, dg in results:
        f1_sum += f1g
        m = ~np.isnan(dg)
        delta_sum[m] += dg[m]
        delta_cnt[m] += 1.0

    f1_avg = f1_sum / n_images if n_images > 0 else f1_sum
    with np.errstate(invalid="ignore", divide="ignore"):
        delta_avg = np.where(delta_cnt > 0, delta_sum / delta_cnt, np.nan)
    return f1_avg, delta_avg, n_images


def pareto_mask(f1_vals, delta_vals):
    """Boolean mask of Pareto-optimal points (maximize f1, minimize delta).

    Operates on full-precision inputs.
    """
    f1_vals = np.asarray(f1_vals, dtype=np.float64)
    delta_vals = np.asarray(delta_vals, dtype=np.float64)
    n = len(f1_vals)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (
                f1_vals[j] >= f1_vals[i]
                and delta_vals[j] <= delta_vals[i]
                and (f1_vals[j] > f1_vals[i] or delta_vals[j] < delta_vals[i])
            ):
                keep[i] = False
                break
    return keep


def compute_pareto_frontier(citsci_path, expert_path, n_jobs=4, grid=None):
    """Full pipeline: returns a pandas DataFrame of Pareto-optimal rows
    (unrounded), columns F1,delta,min_samples,epsilon,shape_weight.
    """
    if grid is None:
        ms_list, eps_list, w_list = default_grid()
    else:
        ms_list, eps_list, w_list = grid

    images, cit_dict, exp_dict = load_image_data(citsci_path, expert_path)
    f1_avg, delta_avg, n_images = run_grid(
        images, cit_dict, exp_dict, ms_list, eps_list, w_list, n_jobs=n_jobs
    )

    rows = []
    for mi, ms in enumerate(ms_list):
        for ei, eps in enumerate(eps_list):
            for wi, w in enumerate(w_list):
                f1v = f1_avg[mi, ei, wi]
                dv = delta_avg[mi, ei, wi]
                rows.append((f1v, dv, int(ms), int(eps), float(w)))

    df = pd.DataFrame(
        rows, columns=["F1", "delta", "min_samples", "epsilon", "shape_weight"]
    )
    # Filter: F1 > 0.5 and finite delta.
    df = df[(df["F1"] > 0.5) & np.isfinite(df["delta"])].reset_index(drop=True)

    if len(df) == 0:
        return df, n_images

    mask = pareto_mask(df["F1"].to_numpy(), df["delta"].to_numpy())
    pf = df[mask].reset_index(drop=True)
    pf = pf.sort_values(["F1", "delta"], ascending=[False, True]).reset_index(
        drop=True
    )
    return pf, n_images


def format_and_write(pf, output_path):
    """Apply the required rounding and write the CSV. Returns list-of-dict rows."""
    out = pf.copy()
    if len(out) > 0:
        out["F1"] = out["F1"].astype(float).round(5)
        out["delta"] = out["delta"].astype(float).round(5)
        out["shape_weight"] = out["shape_weight"].astype(float).round(1)
        out["min_samples"] = out["min_samples"].astype(int)
        out["epsilon"] = out["epsilon"].astype(int)
    else:
        out = pd.DataFrame(
            columns=["F1", "delta", "min_samples", "epsilon", "shape_weight"]
        )
    out = out[["F1", "delta", "min_samples", "epsilon", "shape_weight"]]
    out.to_csv(output_path, index=False)
    return out.to_dict(orient="records")
