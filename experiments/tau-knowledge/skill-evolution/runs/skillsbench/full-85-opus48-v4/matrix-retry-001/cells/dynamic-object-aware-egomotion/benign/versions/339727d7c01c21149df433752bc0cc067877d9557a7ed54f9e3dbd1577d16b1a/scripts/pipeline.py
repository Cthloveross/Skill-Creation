#!/usr/bin/env python3
"""End-to-end egomotion + dynamic-mask pipeline.

Reads an optional JSON config on stdin:
  {"video": str, "fps": float,
   "out_instructions": str, "out_masks": str,
   "pan_thr_frac": float, "tilt_thr_frac": float,
   "scale_thr": float, "roll_thr_deg": float,
   "resid_k": float, "min_area_frac": float,
   "smooth_window": int, "orb_features": int,
   "min_inliers": int}

All keys optional; defaults match the public task (fps=5, /root paths).
Writes a JSON summary to stdout. On fatal error writes {"error": ...} and
exits non-zero.
"""
import sys, json, math, os


def _read_config():
    cfg = {}
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            cfg = json.loads(raw)
            if not isinstance(cfg, dict):
                cfg = {}
    except Exception:
        cfg = {}
    return cfg


def main():
    cfg = _read_config()
    video = cfg.get("video", "/root/input.mp4")
    fps = float(cfg.get("fps", 5))
    out_instructions = cfg.get("out_instructions", "/root/pred_instructions.json")
    out_masks = cfg.get("out_masks", "/root/pred_dyn_masks.npz")

    pan_thr_frac = float(cfg.get("pan_thr_frac", 0.004))
    tilt_thr_frac = float(cfg.get("tilt_thr_frac", 0.008))
    scale_thr = float(cfg.get("scale_thr", 0.02))
    roll_thr_deg = float(cfg.get("roll_thr_deg", 1.0))
    resid_k = float(cfg.get("resid_k", 2.0))
    min_area_frac = float(cfg.get("min_area_frac", 0.0005))
    smooth_window = int(cfg.get("smooth_window", 3))
    orb_features = int(cfg.get("orb_features", 2000))
    min_inliers = int(cfg.get("min_inliers", 12))

    try:
        import numpy as np
        import cv2
        from scipy import sparse
    except Exception as e:  # pragma: no cover
        print(json.dumps({"error": "missing dependency: %s" % e}))
        return 2

    if not os.path.exists(video):
        print(json.dumps({"error": "video not found: %s" % video}))
        return 2

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        print(json.dumps({"error": "cannot open video: %s" % video}))
        return 2
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if not orig_fps or orig_fps <= 0 or math.isnan(orig_fps):
        orig_fps = 30.0
    interval = max(1, int(round(orig_fps / fps)))

    frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % interval == 0:
            frames.append(frame)
        idx += 1
    cap.release()

    if len(frames) == 0:
        print(json.dumps({"error": "no frames decoded"}))
        return 2

    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    H_img, W_img = grays[0].shape[:2]
    N = len(grays)

    pan_thr = pan_thr_frac * W_img
    tilt_thr = tilt_thr_frac * H_img
    min_area = max(25, int(min_area_frac * H_img * W_img))

    orb = cv2.ORB_create(nfeatures=orb_features)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    def estimate_homography(g0, g1):
        k0, d0 = orb.detectAndCompute(g0, None)
        k1, d1 = orb.detectAndCompute(g1, None)
        if d0 is None or d1 is None or len(k0) < 4 or len(k1) < 4:
            return None
        matches = bf.match(d0, d1)
        if len(matches) < max(4, min_inliers):
            return None
        src = np.float32([k0[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst = np.float32([k1[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        Hm, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if Hm is None:
            return None
        inliers = int(mask.sum()) if mask is not None else 0
        if inliers < min_inliers:
            return None
        return Hm

    def classify_motion(Hm):
        if Hm is None:
            return ["Stay"]
        cx, cy = W_img / 2.0, H_img / 2.0
        pts = np.array([
            [cx, cy],
            [W_img * 0.25, H_img * 0.25],
            [W_img * 0.75, H_img * 0.25],
            [W_img * 0.25, H_img * 0.75],
            [W_img * 0.75, H_img * 0.75],
        ], dtype=np.float32).reshape(-1, 1, 2)
        tp = cv2.perspectiveTransform(pts, Hm).reshape(-1, 2)
        dx = tp[0, 0] - cx
        dy = tp[0, 1] - cy
        orig_d = np.linalg.norm(pts.reshape(-1, 2)[1:] - np.array([cx, cy]), axis=1)
        new_d = np.linalg.norm(tp[1:] - np.array([cx, cy]), axis=1)
        valid = orig_d > 1e-6
        scale = float(np.mean(new_d[valid] / orig_d[valid])) if valid.any() else 1.0
        angle = math.degrees(math.atan2(Hm[1, 0], Hm[0, 0]))

        labels = []
        if scale > 1.0 + scale_thr:
            labels.append("Dolly In")
        elif scale < 1.0 - scale_thr:
            labels.append("Dolly Out")
        # sign inversion: content shift opposite camera motion
        if dx > pan_thr:
            labels.append("Pan Left")
        elif dx < -pan_thr:
            labels.append("Pan Right")
        if dy > tilt_thr:
            labels.append("Tilt Up")
        elif dy < -tilt_thr:
            labels.append("Tilt Down")
        if angle > roll_thr_deg:
            labels.append("Roll Right")
        elif angle < -roll_thr_deg:
            labels.append("Roll Left")
        if not labels:
            labels = ["Stay"]
        return labels

    def dynamic_mask(g0, g1, Hm):
        flow = cv2.calcOpticalFlowFarneback(
            g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        ys, xs = np.mgrid[0:H_img, 0:W_img].astype(np.float32)
        if Hm is not None:
            pts = np.stack([xs.ravel(), ys.ravel()], axis=1).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, Hm).reshape(H_img, W_img, 2)
            exp = np.empty_like(flow)
            exp[..., 0] = dst[..., 0] - xs
            exp[..., 1] = dst[..., 1] - ys
            resid = flow - exp
        else:
            med = np.median(flow.reshape(-1, 2), axis=0)
            resid = flow - med
        mag = np.sqrt(resid[..., 0] ** 2 + resid[..., 1] ** 2)
        thr = float(mag.mean() + resid_k * mag.std())
        thr = max(thr, 1.0)
        mask = (mag > thr).astype(np.uint8)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        n_cc, lbl, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        out = np.zeros((H_img, W_img), dtype=bool)
        for c in range(1, n_cc):
            if stats[c, cv2.CC_STAT_AREA] >= min_area:
                out[lbl == c] = True
        return out

    # Per-pair estimates
    pair_labels = []
    pair_masks = []
    if N == 1:
        pair_labels = [["Stay"]]
        pair_masks = [np.zeros((H_img, W_img), dtype=bool)]
    else:
        for i in range(N - 1):
            Hm = estimate_homography(grays[i], grays[i + 1])
            pair_labels.append(classify_motion(Hm))
            pair_masks.append(dynamic_mask(grays[i], grays[i + 1], Hm))
        # last-frame duplication
        pair_labels.append(list(pair_labels[-1]))
        pair_masks.append(pair_masks[-1])

    # per-frame labels now length N
    frame_labels = pair_labels

    # light temporal median smoothing over label-sets (by exact set match)
    if smooth_window and smooth_window >= 3 and N >= smooth_window:
        half = smooth_window // 2
        smoothed = []
        for i in range(N):
            lo = max(0, i - half)
            hi = min(N, i + half + 1)
            window = [tuple(sorted(frame_labels[j])) for j in range(lo, hi)]
            # pick most frequent set in window
            counts = {}
            for w in window:
                counts[w] = counts.get(w, 0) + 1
            best = max(counts.items(), key=lambda kv: (kv[1], kv[0] == tuple(sorted(frame_labels[i]))))
            smoothed.append(list(best[0]))
        frame_labels = smoothed

    # merge consecutive identical label sets into intervals
    instructions = {}
    start = 0
    for i in range(1, N + 1):
        if i == N or sorted(frame_labels[i]) != sorted(frame_labels[start]):
            key = "%d->%d" % (start, i)
            instructions[key] = list(frame_labels[start])
            start = i

    with open(out_instructions, "w") as f:
        json.dump(instructions, f, indent=2)

    # build CSR npz
    save = {"shape": np.array([H_img, W_img], dtype=np.int64)}
    for i in range(N):
        m = sparse.csr_matrix(pair_masks[i].astype(np.uint8))
        save["f_%d_data" % i] = m.data
        save["f_%d_indices" % i] = m.indices
        save["f_%d_indptr" % i] = m.indptr
    np.savez(out_masks, **save)

    label_counts = {}
    for lab in frame_labels:
        for l in lab:
            label_counts[l] = label_counts.get(l, 0) + 1

    print(json.dumps({
        "n_frames": N,
        "shape": [int(H_img), int(W_img)],
        "orig_fps": float(orig_fps),
        "interval": int(interval),
        "instructions_path": out_instructions,
        "masks_path": out_masks,
        "n_intervals": len(instructions),
        "label_counts": label_counts,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
