#!/usr/bin/env python3
"""Generate camera-motion intervals and sparse dynamic masks from one video.

Reads one JSON configuration object from stdin, writes requested artifacts, and
prints a JSON status object to stdout.
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
VALID_LABELS = set(LABEL_ORDER) | {"Stay"}


def read_samples(path: str, target_fps: float) -> Tuple[List[np.ndarray], float]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("cannot open video: " + path)
    source_fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(source_fps) or source_fps <= 0:
        source_fps = target_fps
    interval = source_fps / target_fps
    next_source = 0.0
    source_index = 0
    frames: List[np.ndarray] = []
    shape = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if source_index + 1e-8 >= next_source:
            if shape is None:
                shape = frame.shape[:2]
            elif frame.shape[:2] != shape:
                frame = cv2.resize(frame, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)
            frames.append(frame)
            next_source += interval
        source_index += 1
    cap.release()
    if not frames:
        raise ValueError("video contains no decodable frames")
    return frames, source_fps


def matched_points(gray0: np.ndarray, gray1: np.ndarray, ratio: float = 0.74) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Return ORB correspondence arrays, or None when matching is insufficient."""
    orb = cv2.ORB_create(nfeatures=1800, fastThreshold=8)
    kp0, des0 = orb.detectAndCompute(gray0, None)
    kp1, des1 = orb.detectAndCompute(gray1, None)
    if des0 is None or des1 is None or len(kp0) < 8 or len(kp1) < 8:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des0, des1, k=2)
    good = [m for pair in pairs if len(pair) == 2 for m, nxt in [pair]
            if m.distance < ratio * nxt.distance]
    if len(good) < 8:
        return None
    src = np.float32([kp0[m.queryIdx].pt for m in good])
    dst = np.float32([kp1[m.trainIdx].pt for m in good])
    return src, dst


def broad_coverage(src: np.ndarray, keep: np.ndarray, height: int, width: int,
                   x_fraction: float = 0.20, y_fraction: float = 0.20) -> bool:
    pts = src[keep]
    if len(pts) == 0:
        return False
    spread = np.ptp(pts, axis=0)
    return bool(spread[0] >= x_fraction * width and spread[1] >= y_fraction * height)


def estimate_homography(gray0: np.ndarray, gray1: np.ndarray) -> Optional[np.ndarray]:
    matches = matched_points(gray0, gray1)
    if matches is None:
        return None
    src, dst = matches
    if len(src) < 8:
        return None
    hmat, inliers = cv2.findHomography(
        src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2), cv2.RANSAC, 3.0,
        maxIters=2500, confidence=0.995,
    )
    if hmat is None or inliers is None or not np.all(np.isfinite(hmat)):
        return None
    keep = inliers.ravel().astype(bool)
    height, width = gray0.shape
    if int(keep.sum()) < 8 or not broad_coverage(src, keep, height, width, 0.12, 0.12):
        return None
    if abs(float(hmat[2, 2])) < 1e-10:
        return None
    return (hmat / hmat[2, 2]).astype(np.float64)


def estimate_affine_motion(gray0: np.ndarray, gray1: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[float]]:
    """Estimate a distributed RANSAC affine background model for label decisions.

    The returned matrix is homogeneous 3x3 and the second value is the median
    inlier reprojection error. Broad inlier support prevents a local moving
    object from defining camera motion.
    """
    matches = matched_points(gray0, gray1, ratio=0.72)
    if matches is None:
        return None, None
    src, dst = matches
    if len(src) < 18:
        return None, None
    affine, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0,
        maxIters=3000, confidence=0.995,
    )
    if affine is None or inliers is None or not np.all(np.isfinite(affine)):
        return None, None
    keep = inliers.ravel().astype(bool)
    height, width = gray0.shape
    if int(keep.sum()) < 18 or not broad_coverage(src, keep, height, width):
        return None, None
    predicted = src[keep] @ affine[:, :2].T + affine[:, 2]
    error = np.linalg.norm(predicted - dst[keep], axis=1)
    median_error = float(np.median(error))
    if not np.isfinite(median_error) or median_error > 1.5:
        return None, None
    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :] = affine
    return matrix, median_error


def farneback(gray0: np.ndarray, gray1: np.ndarray) -> np.ndarray:
    return cv2.calcOpticalFlowFarneback(gray0, gray1, None, 0.5, 3, 15, 3, 5, 1.2, 0)


def transform_points(hmat: np.ndarray, points: np.ndarray) -> np.ndarray:
    flat = points.reshape(-1, 2).astype(np.float64)
    homogeneous = np.column_stack((flat, np.ones(len(flat))))
    result = homogeneous @ hmat.T
    denom = result[:, 2]
    output = np.empty((len(flat), 2), dtype=np.float64)
    valid = np.abs(denom) > 1e-8
    output[valid] = result[valid, :2] / denom[valid, None]
    output[~valid] = flat[~valid]
    return output.reshape(points.shape)


def expected_flow(hmat: Optional[np.ndarray], flow: np.ndarray) -> np.ndarray:
    height, width = flow.shape[:2]
    if hmat is None:
        median = np.median(flow.reshape(-1, 2), axis=0)
        return np.broadcast_to(median, flow.shape).copy()
    yy, xx = np.mgrid[0:height, 0:width]
    points = np.dstack((xx, yy)).astype(np.float64)
    predicted = transform_points(hmat, points) - points
    predicted[~np.isfinite(predicted)] = 0
    return predicted.astype(np.float32)


def robust_sigma(values: np.ndarray) -> float:
    flat = np.asarray(values, dtype=np.float64).ravel()
    median = float(np.median(flat))
    return float(1.4826 * np.median(np.abs(flat - median)))


def model_parameters(model: Optional[np.ndarray], flow: np.ndarray) -> Tuple[float, float, float, float]:
    """Return center dx/dy, local scale, and apparent-image rotation."""
    height, width = flow.shape[:2]
    cx, cy = (width - 1.0) / 2.0, (height - 1.0) / 2.0
    if model is None:
        delta = np.median(flow.reshape(-1, 2), axis=0)
        return float(delta[0]), float(delta[1]), 1.0, 0.0
    probes = np.array([[cx, cy], [cx + 1.0, cy], [cx, cy + 1.0]], dtype=np.float64)
    mapped = transform_points(model, probes)
    center_delta = mapped[0] - probes[0]
    jacobian = np.column_stack((mapped[1] - mapped[0], mapped[2] - mapped[0]))
    determinant = float(np.linalg.det(jacobian))
    scale = math.sqrt(abs(determinant)) if np.isfinite(determinant) else 1.0
    theta = math.atan2(float(jacobian[1, 0] - jacobian[0, 1]),
                       float(jacobian[0, 0] + jacobian[1, 1]))
    return (float(center_delta[0]), float(center_delta[1]),
            scale if np.isfinite(scale) else 1.0,
            theta if np.isfinite(theta) else 0.0)


def classify(model: Optional[np.ndarray], flow: np.ndarray, fit_noise: Optional[float]) -> List[str]:
    """Classify independent axes from a robust global transform.

    Flow residual magnitude is intentionally not used to inflate this threshold:
    residuals can be large because of parallax or objects while the RANSAC
    background transform still provides clear egomotion.
    """
    height, width = flow.shape[:2]
    dx, dy, scale, theta = model_parameters(model, flow)
    if fit_noise is not None and np.isfinite(fit_noise):
        displacement_threshold = max(1.25, min(4.5, 3.0 * fit_noise))
    else:
        displacement_threshold = 3.0
    radius = max(1.0, 0.25 * (width + height))
    scale_threshold = max(0.003, min(0.05, displacement_threshold / radius))
    roll_threshold = max(math.radians(0.25), min(math.radians(6.0), displacement_threshold / radius))
    labels: List[str] = []
    if scale > 1.0 + scale_threshold:
        labels.append("Dolly In")
    elif scale < 1.0 - scale_threshold:
        labels.append("Dolly Out")
    # These are image-content displacements, hence the documented inverse
    # camera naming: content left/negative dx is a rightward camera pan.
    if dx > displacement_threshold:
        labels.append("Pan Left")
    elif dx < -displacement_threshold:
        labels.append("Pan Right")
    if dy > displacement_threshold:
        labels.append("Tilt Up")
    elif dy < -displacement_threshold:
        labels.append("Tilt Down")
    # Positive image-coordinate rotation is visually clockwise; camera-roll
    # naming is opposite apparent scene rotation.
    if theta > roll_threshold:
        labels.append("Roll Left")
    elif theta < -roll_threshold:
        labels.append("Roll Right")
    return labels if labels else ["Stay"]


def cleanup_mask(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    scale = min(height, width)
    kernel_size = max(1, int(round(scale / 320.0)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    binary = mask.astype(np.uint8)
    if kernel_size > 1:
        kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    count, components, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    min_area = max(3, int(round(height * width * 0.00001)))
    result = np.zeros_like(binary)
    for component in range(1, count):
        if int(stats[component, cv2.CC_STAT_AREA]) >= min_area:
            result[components == component] = 1
    return result.astype(bool)


def residual_mask(residual: np.ndarray, sigma_multiplier: float, floor: float) -> np.ndarray:
    magnitude = np.linalg.norm(residual, axis=2)
    median = float(np.median(magnitude))
    threshold = max(float(floor), median + float(sigma_multiplier) * robust_sigma(magnitude))
    return cleanup_mask(magnitude > threshold)


def forward_warp_mask(mask: np.ndarray, flow: np.ndarray) -> np.ndarray:
    """Forward-splat source mask pixels using source-to-destination flow."""
    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    output = np.zeros((height, width), dtype=bool)
    if len(xs) == 0:
        return output
    tx = np.rint(xs + flow[ys, xs, 0]).astype(np.int64)
    ty = np.rint(ys + flow[ys, xs, 1]).astype(np.int64)
    valid = (tx >= 0) & (tx < width) & (ty >= 0) & (ty < height)
    output[ty[valid], tx[valid]] = True
    return output


def soften_labels(labels: List[List[str]]) -> List[List[str]]:
    """Optional isolated-label smoothing; disabled by default by the caller."""
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
    for index in range(1, len(frame_labels) + 1):
        if index == len(frame_labels) or frame_labels[index] != frame_labels[start]:
            result[f"{start}->{index}"] = list(frame_labels[start])
            start = index
    return result


def csr_entries(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, _ = mask.shape
    parts: List[np.ndarray] = []
    indptr = np.zeros(height + 1, dtype=np.int64)
    total = 0
    for row in range(height):
        columns = np.flatnonzero(mask[row]).astype(np.int32)
        parts.append(columns)
        total += len(columns)
        indptr[row + 1] = total
    indices = np.concatenate(parts) if total else np.empty(0, dtype=np.int32)
    return np.ones(total, dtype=bool), indices, indptr


def validate_outputs(instructions: Dict[str, List[str]], masks: List[np.ndarray]) -> None:
    cursor = 0
    for key, labels in instructions.items():
        try:
            start_text, end_text = key.split("->")
            start, end = int(start_text), int(end_text)
        except Exception as exc:
            raise ValueError("invalid interval key: " + str(key)) from exc
        if (start != cursor or end <= start or not labels or
                any(label not in VALID_LABELS for label in labels) or
                len(labels) != len(set(labels)) or
                ("Stay" in labels and len(labels) != 1)):
            raise ValueError("invalid or noncontiguous instruction intervals")
        cursor = end
    if cursor != len(masks):
        raise ValueError("instruction intervals do not cover sampled frames")
    height, width = masks[0].shape
    for mask in masks:
        if mask.shape != (height, width) or mask.dtype != np.bool_:
            raise ValueError("invalid mask dimensions or dtype")
        data, indices, indptr = csr_entries(mask)
        if (len(indptr) != height + 1 or indptr[0] != 0 or indptr[-1] != len(data) or
                np.any(np.diff(indptr) < 0) or np.any(indices < 0) or np.any(indices >= width)):
            raise ValueError("invalid CSR representation")


def analyze(config: dict) -> dict:
    video = str(config.get("video", "/root/input.mp4"))
    target_fps = float(config.get("fps", 5.0))
    if not np.isfinite(target_fps) or target_fps <= 0:
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
    affine_count = 0

    for i in range(len(grays) - 1):
        flow = farneback(grays[i], grays[i + 1])
        homography = estimate_homography(grays[i], grays[i + 1])
        affine, affine_noise = estimate_affine_motion(grays[i], grays[i + 1])
        if homography is not None:
            homography_count += 1
        if affine is not None:
            affine_count += 1
        # The affine is deliberately primary for center displacement; use the
        # homography for background-flow residuals when it is available.
        motion_model = affine if affine is not None else homography
        fit_noise = affine_noise if affine is not None else None
        residual = flow - expected_flow(homography, flow)
        pair_labels.append(classify(motion_model, flow, fit_noise))
        pair_masks.append(residual_mask(residual, sigma_multiplier, residual_floor))
        pair_flows.append(flow)

    if len(frames) == 1:
        final_labels = [["Stay"]]
        final_masks = [np.zeros((height, width), dtype=bool)]
    else:
        final_labels = pair_labels + [list(pair_labels[-1])]
        if bool(config.get("smooth_labels", False)):
            final_labels = soften_labels(final_labels)
        final_masks = [pair_masks[0]]
        for i in range(1, len(pair_masks)):
            propagated = forward_warp_mask(final_masks[-1], pair_flows[i - 1])
            nearby = cv2.dilate(pair_masks[i].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            final_masks.append(cleanup_mask(pair_masks[i] | (propagated & nearby)))
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
    for index, mask in enumerate(final_masks):
        data, indices, indptr = csr_entries(mask)
        arrays[f"f_{index}_data"] = data
        arrays[f"f_{index}_indices"] = indices
        arrays[f"f_{index}_indptr"] = indptr
    np.savez_compressed(masks_out, **arrays)
    return {
        "status": "ok",
        "instructions_out": instructions_out,
        "masks_out": masks_out,
        "sampled_frames": len(frames),
        "shape": [height, width],
        "source_fps": source_fps,
        "homography_pairs": homography_count,
        "affine_motion_pairs": affine_count,
        "total_pairs": max(0, len(frames) - 1),
    }


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(analyze(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
