#!/usr/bin/env python3
"""Entrypoint: build pred_instructions.json and pred_dyn_masks.npz.

stdin JSON (all keys optional):
  {
    "video_path": "/root/input.mp4",
    "fps": 5,
    "out_instructions": "/root/pred_instructions.json",
    "out_masks": "/root/pred_dyn_masks.npz",
    "params": { ...optional overrides of DEFAULT_PARAMS... }
  }

stdout JSON summary:
  {"num_frames": N, "shape": [H,W], "num_intervals": k,
   "instructions_path": ..., "masks_path": ...,
   "fallback_pairs": [...], "mask_pixel_counts": [...]}
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np  # noqa: E402
import common  # noqa: E402


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except Exception:
        cfg = {}
    video_path = cfg.get("video_path", "/root/input.mp4")
    fps = float(cfg.get("fps", 5))
    out_instr = cfg.get("out_instructions", "/root/pred_instructions.json")
    out_masks = cfg.get("out_masks", "/root/pred_dyn_masks.npz")

    params = dict(common.DEFAULT_PARAMS)
    params.update(cfg.get("params", {}))

    frames, orig_fps, interval = common.sample_frames(video_path, fps)
    n = len(frames)
    if n == 0:
        sys.stderr.write("no frames decoded from %s\n" % video_path)
        return 2
    h, w = frames[0].shape

    # resolution-relative threshold defaults (unless explicitly overridden)
    if "pan_thr" not in cfg.get("params", {}):
        params["pan_thr"] = max(1.5, 0.004 * w)
    if "tilt_thr" not in cfg.get("params", {}):
        params["tilt_thr"] = max(2.0, 0.006 * h)

    transition_labels = []
    masks = []
    fallback_pairs = []

    if n == 1:
        masks.append(np.zeros((h, w), dtype=bool))
        frame_labels = [["Stay"]]
    else:
        for t in range(n - 1):
            g0, g1 = frames[t], frames[t + 1]
            H, info = common.estimate_homography(
                g0, g1,
                n_features=params["n_features"],
                min_matches=params["min_matches"])
            if H is None:
                fallback_pairs.append(t)
            flow = common.farneback_flow(g0, g1)
            transition_labels.append(
                common.classify_motion(H, flow, (h, w), params))
            masks.append(common.dynamic_mask(H, flow, (h, w), params))
        transition_labels = common.smooth_labels(
            transition_labels, params["smooth_window"])
        frame_labels = common.expand_frame_labels(transition_labels, n)
        # duplicate last transition mask for final frame
        masks.append(masks[-1].copy())

    intervals = common.merge_intervals(frame_labels)
    with open(out_instr, "w") as f:
        json.dump(intervals, f, indent=2)

    npz = {"shape": np.asarray([h, w], dtype=np.int32)}
    pixel_counts = []
    for i, m in enumerate(masks):
        data, indices, indptr = common.mask_to_csr(m)
        npz["f_%d_data" % i] = data
        npz["f_%d_indices" % i] = indices
        npz["f_%d_indptr" % i] = indptr
        pixel_counts.append(int(data.shape[0]))
    np.savez_compressed(out_masks, **npz)

    summary = {
        "num_frames": n,
        "shape": [int(h), int(w)],
        "orig_fps": orig_fps,
        "interval": interval,
        "num_intervals": len(intervals),
        "instructions_path": out_instr,
        "masks_path": out_masks,
        "fallback_pairs": fallback_pairs,
        "mask_pixel_counts": pixel_counts,
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
