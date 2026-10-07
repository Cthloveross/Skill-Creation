---
name: dynamic-object-aware-egomotion
description: >
  Analyze a monocular video to (1) classify camera egomotion into the nine
  motion labels and emit merged frame-interval instructions, and (2) detect
  independently moving (dynamic) objects as per-frame binary masks stored in
  CSR sparse format. Use this when a task supplies a video path and asks for a
  pred_instructions.json (interval -> motion-label mapping) plus a
  pred_dyn_masks.npz (CSR masks per sampled frame), sampling at a given fps.
---

# Dynamic-Object-Aware Egomotion

## When to use
The public task gives a video (e.g. `/root/input.mp4`) and a sample rate
(e.g. `fps = 5`) and requires two deliverables:

1. `/root/pred_instructions.json` — merged `"start->end"` half-open intervals
   mapping to a list of motion labels drawn from exactly:
   `Stay, Dolly In, Dolly Out, Pan Left, Pan Right, Tilt Up, Tilt Down,
   Roll Left, Roll Right`.
2. `/root/pred_dyn_masks.npz` — a `shape` key `[H, W]` plus, for every sampled
   frame `i`, the keys `f_{i}_data`, `f_{i}_indices`, `f_{i}_indptr`
   (scipy CSR of the per-frame boolean dynamic mask).

## Method (what the pipeline does)
Implemented end-to-end in `scripts/pipeline.py`. The approach follows the
frozen background:

- **Sampling.** Open the video, read `orig_fps`, compute
  `interval = max(1, round(orig_fps / target_fps))`, keep every `interval`-th
  frame, convert to grayscale. This yields `N` sampled frames.
- **Pairwise analysis.** `N` sampled frames give `N-1` adjacent transitions.
  Each transition `i -> i+1` produces one motion-label set and one dynamic
  mask, both assigned to sampled frame `i`. Per the task convention, the label
  set and mask of the **final transition** `(N-2 -> N-1)` are also assigned to
  frame `N-1` (last-frame duplication), so outputs cover indices `0..N-1`.
- **Global motion model.** For each pair, detect ORB keypoints, match with a
  brute-force Hamming matcher, and estimate a homography `H` with RANSAC. If
  there are too few inliers/matches, fall back to the per-pixel **median flow**
  as the global model (no `H`).
- **Egomotion classification.** Transform the image center and the four
  quadrant centers through `H`:
  - horizontal center displacement `dx`: `dx > +pan_thr` => `Pan Left`,
    `dx < -pan_thr` => `Pan Right` (sign inversion: content shift is opposite
    to camera motion);
  - vertical center displacement `dy`: `dy > +tilt_thr` => `Tilt Up`,
    `dy < -tilt_thr` => `Tilt Down` (tilt threshold higher than pan);
  - mean distance ratio of quadrant points from center: `> 1+scale_thr` =>
    `Dolly In`, `< 1-scale_thr` => `Dolly Out`;
  - in-plane rotation angle `atan2(H[1,0], H[0,0])`: beyond `roll_thr` =>
    `Roll Right`/`Roll Left`.
  Axes are checked **independently** and all applicable labels returned
  (compound motion). If no axis fires, the label is `Stay`.
  Thresholds are derived from image resolution (not a hidden class
  distribution) and are exposed as parameters; a light temporal median
  smoothing (default window 3) reduces single-frame flicker.
- **Interval merging.** Consecutive sampled frames with identical label sets
  are run-length encoded into `"start->end"` keys where `end` is exclusive
  (the first index of the next interval). The last interval ends at `N`.
- **Dynamic masks.** Compute dense Farneback optical flow. Build the
  **expected flow** from `H` (`H*(x,y,1)` minus `(x,y)`), take the residual
  `actual - expected` (or `actual - median_flow` in fallback), and threshold
  its magnitude with an **adaptive** cutoff (`mean + k*std`, with a floor).
  Clean with morphological opening then closing and drop connected components
  below a resolution-relative minimum area. Masks are stored as scipy CSR.

## Running it
The script reads an optional JSON config object on **stdin** and writes a JSON
summary to **stdout**. All keys are optional; defaults match the public task.

```
cd /app/environment/skills/current   # or wherever this Skill is installed
echo '{"video":"/root/input.mp4","fps":5,
       "out_instructions":"/root/pred_instructions.json",
       "out_masks":"/root/pred_dyn_masks.npz"}' \
  | python3 scripts/pipeline.py
```

With no stdin (empty), it uses: `video=/root/input.mp4`, `fps=5`,
`out_instructions=/root/pred_instructions.json`,
`out_masks=/root/pred_dyn_masks.npz`.

Read the actual task text at runtime to confirm the video path, fps, and
output paths; pass them in the config rather than assuming. If a required
input (e.g. the video) is missing or unreadable, the script exits non-zero
with a JSON `{"error": ...}` on stdout — surface that instead of writing
placeholder outputs.

### Stdout summary schema
```
{"n_frames": int, "shape": [H, W], "orig_fps": float, "interval": int,
 "instructions_path": str, "masks_path": str,
 "n_intervals": int, "label_counts": {label: count}}
```

## Validating the output (do this after running)
After the pipeline runs, verify both artifacts with
`scripts/validate.py` (reads a JSON config on stdin with `instructions`,
`masks`, and optional `n_frames`):

```
echo '{"instructions":"/root/pred_instructions.json",
       "masks":"/root/pred_dyn_masks.npz"}' | python3 scripts/validate.py
```

It checks, and reports failures for, the public contract:
- every interval key matches `"<int>-><int>"`, `start < end`, intervals are
  disjoint and contiguous, cover `0..N-1`, and the final interval ends at `N`;
- every label is one of the nine valid labels and `Stay` never co-occurs with
  another label;
- the npz has a `shape` key `[H, W]` and, for each frame `i` in `0..N-1`,
  the three CSR keys exist, `indptr` has length `H+1`, is non-decreasing,
  starts at 0, ends at `len(indices)`, and `indices` are in `[0, W)`;
- the two artifacts agree on `N` (number of sampled frames).

Treat any reported failure as a defect to fix in the pipeline (sampling,
duplication, merging, or CSR construction) rather than editing the artifact by
hand. When regenerating as part of a revision, rerun `scripts/pipeline.py`
end-to-end and re-validate — do not rely on files left by a previous run.

## Notes and limits
- Requires `opencv-python`, `numpy`, `scipy`. Internet is permitted; if a
  module is missing, install it (`pip install opencv-python-headless numpy
  scipy`) before running.
- Roll Left/Right sign is a convention choice; it is isolated in
  `classify_motion` so it can be flipped in one place if validation indicates.
- Thresholds are tunable parameters, not fixed to any assumed class
  distribution; adjust them from the data/validation, keeping each axis
  independent and preserving the sign conventions above.
