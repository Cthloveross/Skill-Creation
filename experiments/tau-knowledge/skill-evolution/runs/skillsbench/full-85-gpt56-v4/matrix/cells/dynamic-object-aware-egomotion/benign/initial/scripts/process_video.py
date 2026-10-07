#!/usr/bin/env python3
"""Video egomotion/dynamic-mask exporter. JSON stdin -> JSON stdout."""
import json
import math
import os
import sys
from typing import Optional, Tuple

import cv2
import numpy as np

VALID_LABELS = {
    "Stay", "Dolly In", "Dolly Out", "Pan Left", "Pan Right",
    "Tilt Up", "Tilt Down", "Roll Left", "Roll Right",
}


def read_config():
    try:
        obj = json.load(sys.stdin)
    except Exception as exc:
        raise ValueError("stdin must contain one JSON configuration object") from exc
    if not isinstance(obj, dict):
        raise ValueError("configuration must be a JSON object")
    fps = float(obj.get("sample_fps", 5))
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("sample_fps must be a positive finite number")
    return (str(obj.get("input_video", "/root/input.mp4")),
            str(obj.get("instructions_output", "/root/pred_instructions.json")),
            str(obj.get("masks_output", "/root/pred_dyn_masks.npz")), fps)


def sample_video(path: str, target_fps: float):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("cannot open input video: " + path)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(source_fps) or source_fps <= 1e-3:
        source_fps = target_fps
    frames = []
    next_time = 0.0
    index = 0
    period = 1.0 / target_fps
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = index / source_fps
        # Sequential index timing is more reliable than container timestamps in many codecs.
        if t + 1e-9 >= next_time:
            frames.append(frame)
            next_time += period
        index += 1
    cap.release()
    if not frames:
        raise RuntimeError("video contained no decodable frames")
    # A video should not change dimensions, but normalize malformed streams safely.
    h, w = frames[0].shape[:2]
    frames = [f if f.shape[:2] == (h, w) else cv2.resize(f, (w, h)) for f in frames]
    return frames, source_fps


def dense_flow(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 19, 3, 5, 1.2, 0)


def estimate_homography(a: np.ndarray, b: np.ndarray):
    orb = cv2.ORB_create(nfeatures=2500, fastThreshold=12)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 4 or len(kb) < 4:
        return None, None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(da, db, k=2)
    good = [x for x in pairs if len(x) == 2 and x[0].distance < 0.75 * x[1].distance]
    if len(good) < 6:
        return None, None
    src = np.float32([ka[m[0].queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kb[m[0].trainIdx].pt for m in good]).reshape(-1, 1, 2)
    hmat, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 2.5, maxIters=2500, confidence=0.995)
    if hmat is None or inliers is None:
        return None, None
    keep = inliers.ravel().astype(bool)
    if int(keep.sum()) < 6 or not np.all(np.isfinite(hmat)) or abs(hmat[2, 2]) < 1e-9:
        return None, None
    hmat = hmat / hmat[2, 2]
    # Degenerate match clusters are unreliable as a global camera model.
    p = src.reshape(-1, 2)[keep]
    if np.ptp(p[:, 0]) < 0.08 * a.shape[1] or np.ptp(p[:, 1]) < 0.08 * a.shape[0]:
        return None, None
    projected = cv2.perspectiveTransform(src[keep].reshape(-1, 1, 2), hmat).reshape(-1, 2)
    err = np.linalg.norm(projected - dst.reshape(-1, 2)[keep], axis=1)
    return hmat, float(np.median(err))


def homography_flow(hmat: np.ndarray, height: int, width: int) -> Optional[np.ndarray]:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    den = hmat[2, 0] * xx + hmat[2, 1] * yy + hmat[2, 2]
    if np.any(np.abs(den) < 1e-7):
        return None
    xp = (hmat[0, 0] * xx + hmat[0, 1] * yy + hmat[0, 2]) / den
    yp = (hmat[1, 0] * xx + hmat[1, 1] * yy + hmat[1, 2]) / den
    flow = np.dstack((xp - xx, yp - yy)).astype(np.float32)
    return flow if np.all(np.isfinite(flow)) else None


def robust_sigma(values: np.ndarray) -> float:
    med = float(np.median(values))
    return 1.4826 * float(np.median(np.abs(values - med)))


def labels_for_motion(hmat, flow, residual_error, height, width):
    """Classify independent scale/translation/rotation axes with stable label order."""
    diag = math.hypot(width, height)
    if hmat is None:
        dx, dy = np.median(flow.reshape(-1, 2), axis=0)
        dispersion = robust_sigma(np.linalg.norm(flow - np.array([dx, dy]), axis=2))
        trans_noise = max(0.75, 2.5 * dispersion)
        scale, angle = 1.0, 0.0
    else:
        cx, cy = (width - 1) * 0.5, (height - 1) * 0.5
        p = np.array([[[cx, cy]]], dtype=np.float32)
        q = cv2.perspectiveTransform(p, hmat)[0, 0]
        dx, dy = float(q[0] - cx), float(q[1] - cy)
        # Numerical local Jacobian separates roll/zoom from center displacement.
        eps = max(1.0, min(width, height) * 0.002)
        probes = np.array([[[cx, cy], [cx + eps, cy], [cx, cy + eps]]], dtype=np.float32)
        out = cv2.perspectiveTransform(probes, hmat)[0]
        jac = np.column_stack(((out[1] - out[0]) / eps, (out[2] - out[0]) / eps))
        if not np.all(np.isfinite(jac)):
            jac = np.eye(2)
        singular = np.linalg.svd(jac, compute_uv=False)
        scale = float(math.sqrt(max(1e-9, singular[0] * singular[1])))
        angle = math.atan2(float(jac[1, 0] - jac[0, 1]), float(jac[0, 0] + jac[1, 1]))
        trans_noise = max(0.75, 2.5 * float(residual_error or 0.0))
    # Resolution-aware lower bounds avoid making sub-pixel estimator jitter semantic motion.
    trans_threshold = max(trans_noise, 0.0015 * diag)
    scale_threshold = max(0.004, trans_noise / max(diag * 0.75, 1.0))
    roll_threshold = max(math.radians(0.35), trans_noise / max(diag * 0.35, 1.0))
    ans = []
    if scale > 1.0 + scale_threshold:
        ans.append("Dolly In")
    elif scale < 1.0 - scale_threshold:
        ans.append("Dolly Out")
    if abs(float(dx)) > trans_threshold:
        ans.append("Pan Left" if dx > 0 else "Pan Right")
    if abs(float(dy)) > trans_threshold:
        ans.append("Tilt Up" if dy > 0 else "Tilt Down")
    if abs(angle) > roll_threshold:
        # Positive image-coordinate rotation is clockwise; map label by visible rotation.
        ans.append("Roll Right" if angle > 0 else "Roll Left")
    return ans or ["Stay"]


def dynamic_mask(flow: np.ndarray, hmat, height: int, width: int) -> np.ndarray:
    expected = homography_flow(hmat, height, width) if hmat is not None else None
    if expected is None:
        global_motion = np.median(flow.reshape(-1, 2), axis=0)
        expected = np.empty_like(flow)
        expected[:, :, 0] = global_motion[0]
        expected[:, :, 1] = global_motion[1]
    mag = np.linalg.norm(flow - expected, axis=2)
    med = float(np.median(mag))
    sigma = robust_sigma(mag)
    threshold = max(0.9, med + 3.0 * max(sigma, 0.12))
    mask = (mag > threshold).astype(np.uint8)
    # Remove a one-pixel boundary, where flow estimation has no matching support.
    if height > 4 and width > 4:
        mask[[0, -1], :] = 0
        mask[:, [0, -1]] = 0
    k = max(1, int(round(min(height, width) / 220)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    minimum_area = max(6, int(height * width * 0.00003))
    count, components, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    for i in range(1, count):
        if int(stats[i, cv2.CC_STAT_AREA]) >= minimum_area:
            clean[components == i] = 1
    return clean.astype(bool)


def csr_arrays(mask: np.ndarray):
    h, _ = mask.shape
    rows, cols = np.nonzero(mask)
    counts = np.bincount(rows, minlength=h).astype(np.int64)
    indptr = np.empty(h + 1, dtype=np.int64)
    indptr[0] = 0
    indptr[1:] = np.cumsum(counts)
    return np.ones(len(cols), dtype=np.bool_), cols.astype(np.int32), indptr


def intervals(labels):
    result = {}
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            result[f"{start}->{i}"] = labels[start]
            start = i
    return result


def validate(instructions, arrays, n, height, width):
    pos = 0
    for key, value in instructions.items():
        a, b = (int(x) for x in key.split("->"))
        if a != pos or b <= a or not value or any(x not in VALID_LABELS for x in value):
            raise RuntimeError("invalid interval encoding")
        pos = b
    if pos != n:
        raise RuntimeError("intervals do not cover sampled frames")
    if tuple(np.asarray(arrays["shape"]).tolist()) != (height, width):
        raise RuntimeError("invalid shape")
    for i in range(n):
        data, ind, ptr = arrays[f"f_{i}_data"], arrays[f"f_{i}_indices"], arrays[f"f_{i}_indptr"]
        if len(ptr) != height + 1 or ptr[0] != 0 or ptr[-1] != len(ind) or len(ind) != len(data):
            raise RuntimeError("invalid CSR lengths")
        if np.any(np.diff(ptr) < 0) or np.any(ind < 0) or np.any(ind >= width):
            raise RuntimeError("invalid CSR values")


def main():
    source, out_json, out_npz, sample_fps = read_config()
    frames, source_fps = sample_video(source, sample_fps)
    height, width = frames[0].shape[:2]
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    n = len(gray)
    pair_labels, pair_masks, fallbacks = [], [], 0
    for i in range(max(0, n - 1)):
        flow = dense_flow(gray[i], gray[i + 1])
        hmat, err = estimate_homography(gray[i], gray[i + 1])
        if hmat is None:
            fallbacks += 1
        pair_labels.append(labels_for_motion(hmat, flow, err, height, width))
        pair_masks.append(dynamic_mask(flow, hmat, height, width))
    if n == 1:
        frame_labels = [["Stay"]]
        frame_masks = [np.zeros((height, width), dtype=bool)]
    else:
        # Pair i labels frame i; copy the final transition label to frame N-1.
        frame_labels = pair_labels + [pair_labels[-1]]
        frame_masks = []
        for i in range(n):
            incident = []
            if i > 0:
                incident.append(pair_masks[i - 1])
            if i < n - 1:
                incident.append(pair_masks[i])
            # Both endpoint observations reduce one-pair flicker without inventing unsupported regions.
            frame_masks.append(np.logical_or.reduce(incident))
    encoded = {"shape": np.asarray([height, width], dtype=np.int64)}
    for i, mask in enumerate(frame_masks):
        data, ind, ptr = csr_arrays(mask)
        encoded[f"f_{i}_data"] = data
        encoded[f"f_{i}_indices"] = ind
        encoded[f"f_{i}_indptr"] = ptr
    instruction_map = intervals(frame_labels)
    validate(instruction_map, encoded, n, height, width)
    for path in (out_json, out_npz):
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(instruction_map, f, indent=2)
        f.write("\n")
    np.savez_compressed(out_npz, **encoded)
    print(json.dumps({"ok": True, "sampled_frames": n, "shape": [height, width],
                      "source_fps": source_fps, "sample_fps": sample_fps,
                      "homography_fallback_pairs": fallbacks,
                      "instructions_output": out_json, "masks_output": out_npz}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
