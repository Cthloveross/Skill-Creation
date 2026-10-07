"""Shared helpers for egomotion + dynamic-mask estimation.

All functions are task-independent; the entrypoint reads the real video and
parameters at runtime. No instance answers are hardcoded here.
"""
import numpy as np

VALID_LABELS = [
    "Stay", "Dolly In", "Dolly Out", "Pan Left", "Pan Right",
    "Tilt Up", "Tilt Down", "Roll Left", "Roll Right",
]


def sample_frames(video_path, target_fps):
    """Return (gray_frames_list, orig_fps, interval). Grayscale uint8 frames."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("cannot open video: %s" % video_path)
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if not orig_fps or orig_fps <= 0:
        orig_fps = 30.0
    interval = max(1, int(round(orig_fps / float(target_fps))))
    frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % interval == 0:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        idx += 1
    cap.release()
    return frames, orig_fps, interval


def estimate_homography(g0, g1, n_features=2000, min_matches=12):
    """ORB+RANSAC homography from g0->g1.

    Returns (H, info). H is 3x3 float64 or None if estimation failed/weak.
    info has match/inlier counts.
    """
    import cv2
    orb = cv2.ORB_create(nfeatures=n_features)
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    info = {"matches": 0, "inliers": 0, "method": "homography"}
    if d0 is None or d1 is None or len(k0) < 4 or len(k1) < 4:
        return None, {**info, "method": "insufficient_keypoints"}
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(d0, d1)
    info["matches"] = len(matches)
    if len(matches) < min_matches:
        return None, {**info, "method": "insufficient_matches"}
    src = np.float32([k0[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if H is None:
        return None, {**info, "method": "ransac_failed"}
    inliers = int(mask.sum()) if mask is not None else 0
    info["inliers"] = inliers
    if inliers < min_matches:
        return None, {**info, "method": "too_few_inliers"}
    return H.astype(np.float64), info


def farneback_flow(g0, g1):
    import cv2
    return cv2.calcOpticalFlowFarneback(
        g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)


def classify_motion(H, flow, shape, params):
    """Return a sorted list of motion labels for one transition.

    If H is None, use median-flow (pure translation) as the global model.
    """
    h, w = shape
    cx, cy = w / 2.0, h / 2.0
    pan_thr = params["pan_thr"]
    tilt_thr = params["tilt_thr"]
    scale_thr = params["scale_thr"]
    roll_thr_deg = params["roll_thr_deg"]
    labels = []

    if H is None:
        # median flow => apparent scene displacement (mdx, mdy)
        mdx = float(np.median(flow[..., 0]))
        mdy = float(np.median(flow[..., 1]))
        if mdx > pan_thr:
            labels.append("Pan Left")
        elif mdx < -pan_thr:
            labels.append("Pan Right")
        if mdy > tilt_thr:
            labels.append("Tilt Up")
        elif mdy < -tilt_thr:
            labels.append("Tilt Down")
        return labels if labels else ["Stay"]

    # translation of image center
    c = np.array([cx, cy, 1.0])
    cp = H @ c
    cp = cp[:2] / cp[2]
    dx = cp[0] - cx
    dy = cp[1] - cy
    if dx > pan_thr:
        labels.append("Pan Left")
    elif dx < -pan_thr:
        labels.append("Pan Right")
    if dy > tilt_thr:
        labels.append("Tilt Up")
    elif dy < -tilt_thr:
        labels.append("Tilt Down")

    # scale change from quadrant centers
    pts = np.array([
        [0.25 * w, 0.25 * h],
        [0.75 * w, 0.25 * h],
        [0.25 * w, 0.75 * h],
        [0.75 * w, 0.75 * h],
    ])
    homo = np.hstack([pts, np.ones((4, 1))])
    tp = (H @ homo.T).T
    tp = tp[:, :2] / tp[:, 2:3]
    d_before = np.linalg.norm(pts - [cx, cy], axis=1)
    d_after = np.linalg.norm(tp - [cx, cy], axis=1)
    ratio = float(np.mean(d_after) / (np.mean(d_before) + 1e-9))
    if ratio > 1.0 + scale_thr:
        labels.append("Dolly In")
    elif ratio < 1.0 - scale_thr:
        labels.append("Dolly Out")

    # rotation (roll)
    angle = np.degrees(np.arctan2(H[1, 0], H[0, 0]))
    if angle > roll_thr_deg:
        labels.append("Roll Right")
    elif angle < -roll_thr_deg:
        labels.append("Roll Left")

    return sorted(set(labels)) if labels else ["Stay"]


def smooth_labels(label_sets, window=3):
    """Per-label temporal majority vote over a centered window."""
    T = len(label_sets)
    if T == 0:
        return []
    r = window // 2
    out = []
    for t in range(T):
        lo, hi = max(0, t - r), min(T, t + r + 1)
        counts = {}
        for s in range(lo, hi):
            for lab in label_sets[s]:
                if lab == "Stay":
                    continue
                counts[lab] = counts.get(lab, 0) + 1
        need = (hi - lo) // 2 + 1 if (hi - lo) > 1 else 1
        kept = sorted([lab for lab, c in counts.items() if c >= need])
        out.append(kept if kept else ["Stay"])
    return out


def expand_frame_labels(transition_labels, n_frames):
    """Map N-1 transition label-sets to N per-frame label-sets.

    Frame t gets transition t; frame N-1 duplicates the last transition.
    """
    if n_frames <= 1:
        return [["Stay"]]
    frames = [transition_labels[t] for t in range(n_frames - 1)]
    frames.append(transition_labels[-1])
    return frames


def merge_intervals(frame_labels):
    """Run-length merge per-frame label-sets into {\"start->end\": labels}."""
    out = {}
    n = len(frame_labels)
    i = 0
    while i < n:
        j = i + 1
        while j < n and frame_labels[j] == frame_labels[i]:
            j += 1
        out["%d->%d" % (i, j)] = list(frame_labels[i])
        i = j
    return out


def expected_flow(H, shape):
    """Expected (dx,dy) per pixel if the scene were static under H."""
    h, w = shape
    xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    xx = xx.astype(np.float64)
    yy = yy.astype(np.float64)
    X = H[0, 0] * xx + H[0, 1] * yy + H[0, 2]
    Y = H[1, 0] * xx + H[1, 1] * yy + H[1, 2]
    W = H[2, 0] * xx + H[2, 1] * yy + H[2, 2]
    W = np.where(np.abs(W) < 1e-9, 1e-9, W)
    exp_dx = X / W - xx
    exp_dy = Y / W - yy
    return exp_dx, exp_dy


def dynamic_mask(H, flow, shape, params):
    """Compute a binary dynamic-object mask for one transition."""
    import cv2
    h, w = shape
    if H is not None:
        exp_dx, exp_dy = expected_flow(H, shape)
    else:
        exp_dx = np.full(shape, float(np.median(flow[..., 0])))
        exp_dy = np.full(shape, float(np.median(flow[..., 1])))
    res_dx = flow[..., 0] - exp_dx
    res_dy = flow[..., 1] - exp_dy
    mag = np.sqrt(res_dx * res_dx + res_dy * res_dy)

    mean = float(np.mean(mag))
    std = float(np.std(mag))
    thr = max(params["min_residual"], mean + params["k_std"] * std)
    mask = (mag > thr).astype(np.uint8)

    # edge margin suppression (scaled to resolution)
    m = params["edge_margin"]
    mx = int(round(m * w))
    my = int(round(m * h))
    if mx > 0:
        mask[:, :mx] = 0
        mask[:, w - mx:] = 0
    if my > 0:
        mask[:my, :] = 0
        mask[h - my:, :] = 0

    ksz = max(3, int(round(params["kernel_frac"] * min(h, w))) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksz, ksz))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # connected-component area filtering
    num, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    min_area = params["min_area_frac"] * h * w
    out = np.zeros(shape, dtype=bool)
    for c in range(1, num):
        if stats[c, cv2.CC_STAT_AREA] >= min_area:
            out[lab == c] = True
    return out


def mask_to_csr(mask):
    """Return (data, indices, indptr) for a boolean HxW mask.

    indptr length H+1 cumulative True-per-row; indices sorted within row.
    """
    h, w = mask.shape
    indices = []
    indptr = [0]
    count = 0
    for r in range(h):
        cols = np.nonzero(mask[r])[0]
        indices.extend(int(c) for c in cols)
        count += len(cols)
        indptr.append(count)
    data = np.ones(count, dtype=bool)
    return (data,
            np.asarray(indices, dtype=np.int32),
            np.asarray(indptr, dtype=np.int32))


def csr_to_mask(data, indices, indptr, shape):
    h, w = shape
    mask = np.zeros((h, w), dtype=bool)
    for r in range(h):
        cols = indices[indptr[r]:indptr[r + 1]]
        mask[r, cols] = True
    return mask


DEFAULT_PARAMS = {
    # egomotion thresholds (resolution-relative values are set in run.py)
    "pan_thr": 2.0,
    "tilt_thr": 3.0,
    "scale_thr": 0.02,
    "roll_thr_deg": 1.0,
    "smooth_window": 3,
    # mask thresholds
    "min_residual": 1.5,
    "k_std": 2.0,
    "edge_margin": 0.02,
    "kernel_frac": 0.01,
    "min_area_frac": 0.0008,
    # homography robustness
    "n_features": 2000,
    "min_matches": 12,
}
