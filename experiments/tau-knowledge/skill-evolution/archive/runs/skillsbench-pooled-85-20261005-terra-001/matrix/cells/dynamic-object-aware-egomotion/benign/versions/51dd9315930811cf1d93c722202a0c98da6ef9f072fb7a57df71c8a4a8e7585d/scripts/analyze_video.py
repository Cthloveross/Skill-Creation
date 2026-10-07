#!/usr/bin/env python3
"""Video egomotion and dynamic-mask artifact generator.

Reads one JSON object from stdin and writes artifacts named by its output fields.
Prints a JSON status object to stdout.
"""
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

LABEL_ORDER = [
    "Dolly In", "Dolly Out", "Pan Left", "Pan Right",
    "Tilt Up", "Tilt Down", "Roll Left", "Roll Right",
]


def read_samples(path: str, target_fps: float) -> Tuple[List[np.ndarray], float]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("cannot open video: " + path)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = target_fps
    period = source_fps / target_fps
    next_source_index = 0.0
    source_index = 0
    frames: List[np.ndarray] = []
    first_shape = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if source_index + 1e-8 >= next_source_index:
            if first_shape is None:
                first_shape = frame.shape[:2]
            elif frame.shape[:2] != first_shape:
                frame = cv2.resize(frame, (first_shape[1], first_shape[0]), interpolation=cv2.INTER_AREA)
            frames.append(frame)
            next_source_index += period
        source_index += 1
    cap.release()
    if not frames:
        raise ValueError("video contains no decodable frames")
    return frames, source_fps


def estimate_homography(gray0: np.ndarray, gray1: np.ndarray) -> Optional[np.ndarray]:
    orb = cv2.ORB_create(nfeatures=1800, fastThreshold=12)
    kp0, des0 = orb.detectAndCompute(gray0, None)
    kp1, des1 = orb.detectAndCompute(gray1, None)
    if des0 is None or des1 is None or len(kp0) < 8 or len(kp1) < 8:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des0, des1, k=2)
    good = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < 0.75 * b.distance]
    if len(good) < 8:
        return None
    src = np.float32([kp0[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    hmat, inlier = cv2.findHomography(src, dst, cv2.RANSAC, 3.0, maxIters=2500, confidence=0.995)
    if hmat is None or inlier is None or not np.all(np.isfinite(hmat)):
        return None
    keep = inlier.ravel().astype(bool)
    if int(keep.sum()) < 8:
        return None
    # Reject a fit supported by a nearly point-like feature cluster.
    pts = src.reshape(-1, 2)[keep]
    height, width = gray0.shape
    extent = (pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())
    if extent < 0.002 * height * width:
        return None
    hmat = hmat / hmat[2, 2]
    return hmat.astype(np.float64)


def farneback(gray0: np.ndarray, gray1: np.ndarray) -> np.ndarray:
    return cv2.calcOpticalFlowFarneback(
        gray0, gray1, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )


def transform_points(hmat: np.ndarray, points: np.ndarray) -> np.ndarray:
    flat = points.reshape(-1, 2).astype(np.float64)
    homogeneous = np.column_stack((flat, np.ones(len(flat))))
    result = homogeneous @ hmat.T
    denom = result[:, 2]
    out = np.empty((len(flat), 2), dtype=np.float64)
    valid = np.abs(denom) > 1e-8
    out[valid] = result[valid, :2] / denom[valid, None]
    out[~valid] = flat[~valid]
    return out.reshape(points.shape)


def expected_flow(hmat: Optional[np.ndarray], flow: np.ndarray) -> np.ndarray:
    height, width = flow.shape[:2]
    if hmat is None:
        median = np.median(flow.reshape(-1, 2), axis=0)
        return np.broadcast_to(median, flow.shape).copy()
    yy, xx = np.mgrid[0:height, 0:width]
    points = np.dstack((xx, yy)).astype(np.float64)
    mapped = transform_points(hmat, points)
    expected = mapped - points
    # A singular projective region must not turn into a dynamic-object mask.
    expected[~np.isfinite(expected)] = 0
    return expected.astype(np.float32)


def robust_sigma(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64).ravel()
    med = float(np.median(values))
    return float(1.4826 * np.median(np.abs(values - med)))


def model_parameters(hmat: Optional[np.ndarray], flow: np.ndarray) -> Tuple[float, float, float, float]:
    """Return center dx, center dy, local scale, and apparent-image rotation."""
    height, width = flow.shape[:2]
    cx, cy = (width - 1) * 0.5, (height - 1) * 0.5
    if hmat is None:
        delta = np.median(flow.reshape(-1, 2), axis=0)
        return float(delta[0]), float(delta[1]), 1.0, 0.0
    probe = np.array([[cx, cy], [cx + 1.0, cy], [cx, cy + 1.0]], dtype=np.float64)
    mapped = transform_points(hmat, probe)
    center_delta = mapped[0] - probe[0]
    jacobian = np.column_stack((mapped[1] - mapped[0], mapped[2] - mapped[0]))
    det = float(np.linalg.det(jacobian))
    scale = math.sqrt(abs(det)) if np.isfinite(det) else 1.0
    # Polar-rotation angle in image coordinates (positive is visually clockwise).
    theta = math.atan2(float(jacobian[1, 0] - jacobian[0, 1]),
                       float(jacobian[0, 0] + jacobian[1, 1]))
    if not np.isfinite(scale):
        scale = 1.0
    if not np.isfinite(theta):
        theta = 0.0
    return float(center_delta[0]), float(center_delta[1]), scale, theta


def classify(hmat: Optional[np.ndarray], flow: np.ndarray, residual: np.ndarray) -> List[str]:
    height, width = flow.shape[:2]
    dx, dy, scale, theta = model_parameters(hmat, flow)
    magnitude = np.linalg.norm(residual, axis=2)
    sigma = robust_sigma(magnitude)
    diagonal = math.hypot(width, height)
    # Adapt to observed model disagreement but cap the threshold so widespread
    # parallax cannot make all deliberate global motion appear as Stay.
    displacement_threshold = max(0.60, min(0.03 * diagonal, 2.5 * sigma))
    radius = max(1.0, 0.25 * (width + height))
    scale_threshold = max(0.003, min(0.08, displacement_threshold / radius))
    roll_threshold = max(math.radians(0.25), min(math.radians(10.0), displacement_threshold / radius))
    labels: List[str] = []
    if scale > 1.0 + scale_threshold:
        labels.append("Dolly In")
    elif scale < 1.0 - scale_threshold:
        labels.append("Dolly Out")
    if dx > displacement_threshold:
        labels.append("Pan Left")
    elif dx < -displacement_threshold:
        labels.append("Pan Right")
    if dy > displacement_threshold:
        labels.append("Tilt Up")
    elif dy < -displacement_threshold:
        labels.append("Tilt Down")
    # Camera roll naming is opposite apparent scene rotation.
    if theta > roll_threshold:
        labels.append("Roll Left")
    elif theta < -roll_threshold:
        labels.append("Roll Right")
    return labels if labels else ["Stay"]


def cleanup_mask(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    scale = min(height, width)
    k = max(1, int(round(scale / 320.0)))
    if k % 2 == 0:
        k += 1
    binary = mask.astype(np.uint8)
    if k > 1:
        kernel = np.ones((k, k), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    count, components, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    minimum_area = max(3, int(round(height * width * 0.00001)))
    cleaned = np.zeros_like(binary)
    for component in range(1, count):
        if int(stats[component, cv2.CC_STAT_AREA]) >= minimum_area:
            cleaned[components == component] = 1
    return cleaned.astype(bool)


def residual_mask(residual: np.ndarray, sigma_multiplier: float, floor: float) -> np.ndarray:
    magnitude = np.linalg.norm(residual, axis=2)
    baseline = float(np.median(magnitude))
    threshold = max(float(floor), baseline + float(sigma_multiplier) * robust_sigma(magnitude))
    return cleanup_mask(magnitude > threshold)


def forward_warp_mask(mask: np.ndarray, flow: np.ndarray) -> np.ndarray:
    """Forward splat a source mask using source-to-destination flow."""
    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    result = np.zeros((height, width), dtype=bool)
    if len(xs) == 0:
        return result
    tx = np.rint(xs + flow[ys, xs, 0]).astype(np.int64)
    ty = np.rint(ys + flow[ys, xs, 1]).astype(np.int64)
    valid = (tx >= 0) & (tx < width) & (ty >= 0) & (ty < height)
    result[ty[valid], tx[valid]] = True
    return result


def soften_labels(labels: List[List[str]]) -> List[List[str]]:
    if len(labels) < 3:
        return labels
    output = [list(item) for item in labels]
    for i in range(1, len(labels) - 1):
        if labels[i - 1] == labels[i + 1] and labels[i] != labels[i - 1]:
            output[i] = list(labels[i - 1])
    return output


def interval_map(frame_labels: List[List[str]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    start = 0
    for i in range(1, len(frame_labels) + 1):
        if i == len(frame_labels) or frame_labels[i] != frame_labels[start]:
            result[f"{start}->{i}"] = frame_labels[start]
            start = i
    return result


def csr_entries(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, _ = mask.shape
    indices: List[np.ndarray] = []
    indptr = np.zeros(height + 1, dtype=np.int64)
    total = 0
    for row in range(height):
        cols = np.flatnonzero(mask[row]).astype(np.int32)
        indices.append(cols)
        total += len(cols)
        indptr[row + 1] = total
    col_array = np.concatenate(indices) if total else np.empty(0, dtype=np.int32)
    return np.ones(total, dtype=bool), col_array, indptr


def validate_outputs(instructions: Dict[str, List[str]], masks: List[np.ndarray]) -> None:
    nframes = len(masks)
    cursor = 0
    for key, labels in instructions.items():
        try:
            start_s, end_s = key.split("->")
            start, end = int(start_s), int(end_s)
        except Exception as exc:
            raise ValueError("invalid interval key: " + str(key)) from exc
        if start != cursor or end <= start or not labels or any(x not in LABEL_ORDER and x != "Stay" for x in labels):
            raise ValueError("invalid or noncontiguous instruction intervals")
        cursor = end
    if cursor != nframes:
        raise ValueError("instruction intervals do not cover sampled frames")
    height, width = masks[0].shape
    for mask in masks:
        if mask.shape != (height, width) or mask.dtype != np.bool_:
            raise ValueError("mask dimensions or dtype are invalid")
        data, indices, indptr = csr_entries(mask)
        if len(indptr) != height + 1 or indptr[0] != 0 or indptr[-1] != len(data):
            raise ValueError("invalid CSR pointer array")
        if np.any(np.diff(indptr) < 0) or np.any(indices < 0) or np.any(indices >= width):
            raise ValueError("invalid CSR values")


def analyze(config: dict) -> dict:
    video = str(config.get("video", "/root/input.mp4"))
    target_fps = float(config.get("fps", 5.0))
    if target_fps <= 0:
        raise ValueError("fps must be positive")
    instructions_out = str(config.get("instructions_out", "/root/pred_instructions.json"))
    masks_out = str(config.get("masks_out", "/root/pred_dyn_masks.npz"))
    sigma_multiplier = float(config.get("residual_sigma", 3.0))
    residual_floor = float(config.get("residual_floor", 0.75))
    if sigma_multiplier < 0 or residual_floor < 0:
        raise ValueError("residual settings must be nonnegative")

    frames, source_fps = read_samples(video, target_fps)
    grays = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames]
    height, width = grays[0].shape
    pair_labels: List[List[str]] = []
    pair_masks: List[np.ndarray] = []
    pair_flows: List[np.ndarray] = []
    homography_count = 0
    for i in range(len(grays) - 1):
        flow = farneback(grays[i], grays[i + 1])
        hmat = estimate_homography(grays[i], grays[i + 1])
        if hmat is not None:
            homography_count += 1
        expected = expected_flow(hmat, flow)
        residual = flow - expected
        pair_labels.append(classify(hmat, flow, residual))
        pair_masks.append(residual_mask(residual, sigma_multiplier, residual_floor))
        pair_flows.append(flow)

    if len(frames) == 1:
        final_labels = [["Stay"]]
        final_masks = [np.zeros((height, width), dtype=bool)]
    else:
        final_labels = pair_labels + [list(pair_labels[-1])]
        if bool(config.get("smooth_labels", True)):
            final_labels = soften_labels(final_labels)
        final_masks = [pair_masks[0]]
        # Retain propagated evidence only where it has nearby current support.
        for i in range(1, len(pair_masks)):
            propagated = forward_warp_mask(final_masks[-1], pair_flows[i - 1])
            nearby_current = cv2.dilate(pair_masks[i].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            final_masks.append(cleanup_mask(pair_masks[i] | (propagated & nearby_current)))
        # The final sampled frame has no outgoing pair; forward propagation gives
        # it neighbor evidence in the correct source-to-destination direction.
        final_masks.append(cleanup_mask(forward_warp_mask(final_masks[-1], pair_flows[-1])))

    instructions = interval_map(final_labels)
    validate_outputs(instructions, final_masks)
    for destination in (instructions_out, masks_out):
        parent = os.path.dirname(os.path.abspath(destination))
        if parent:
            os.makedirs(parent, exist_ok=True)
    with open(instructions_out, "w", encoding="utf-8") as handle:
        json.dump(instructions, handle, indent=2)
        handle.write("\n")
    arrays: Dict[str, np.ndarray] = {"shape": np.asarray([height, width], dtype=np.int32)}
    for i, mask in enumerate(final_masks):
        data, indices, indptr = csr_entries(mask)
        arrays[f"f_{i}_data"] = data
        arrays[f"f_{i}_indices"] = indices
        arrays[f"f_{i}_indptr"] = indptr
    np.savez_compressed(masks_out, **arrays)
    return {
        "status": "ok",
        "instructions_out": instructions_out,
        "masks_out": masks_out,
        "sampled_frames": len(frames),
        "shape": [height, width],
        "source_fps": source_fps,
        "homography_pairs": homography_count,
        "total_pairs": max(0, len(frames) - 1),
    }


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        result = analyze(config)
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
