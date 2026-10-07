---
name: dynamic-object-aware-egomotion
description: >
  Analyze a monocular video to (1) classify per-frame camera motion
  (egomotion) into the 9 labels Stay / Dolly In / Dolly Out / Pan Left /
  Pan Right / Tilt Up / Tilt Down / Roll Left / Roll Right, emitting a
  run-length JSON of "start->end" intervals, and (2) segment independently
  moving (dynamic) objects per sampled frame, saved as CSR sparse masks in
  an .npz. Use when a task supplies a video path, a target sample fps, and
  asks for an instructions JSON plus a dynamic-mask npz in the exact formats
  described below. The method samples frames to the target fps, estimates a
  per-pair homography (ORB+RANSAC) with a median-flow fallback, decomposes it
  for egomotion, and uses the actual-minus-expected optical-flow residual for
  dynamic masks.
---

# Dynamic-Object-Aware Egomotion

## What this Skill produces

Given a video (default `/root/input.mp4`) and a target sample rate (default
`fps=5`), it writes two deliverables whose formats are fixed by the task:

1. **`/root/pred_instructions.json`** — a mapping of half-open frame intervals
   to motion-label lists, e.g. `{"0->1": ["Pan Right"], "1->4": ["Stay"]}`.
   - Keys are `"start->end"`; the interval covers sampled indices
     `start .. end-1` (half-open). `"0->1"` labels sampled frame 0 only.
   - For `N` sampled frames the expanded intervals cover every index
     `0 .. N-1` exactly once and the final interval ends at `N`.
   - Only `N-1` adjacent transitions exist. Transition `t` (frames t->t+1)
     labels sampled frame `t`. The **last** transition (N-2 -> N-1) label is
     also assigned to the final frame `N-1` (endpoint duplication).
   - Each value is a non-empty list of valid labels; a frame with no motion
     axis above threshold is `["Stay"]`. Compound motion (e.g. Dolly In +
     Pan Right) returns multiple labels.

2. **`/root/pred_dyn_masks.npz`** — one binary mask per sampled frame in CSR.
   - Key `shape` = `[H, W]` (sampled grayscale frame size, shared by all).
   - For frame `i`: `f_{i}_data` (True values), `f_{i}_indices` (sorted column
     indices of True pixels, row by row), `f_{i}_indptr` (length `H+1`,
     cumulative count of True pixels per row). Frame `N-1` duplicates the last
     transition's mask so there are exactly `N` masks (`f_0 .. f_{N-1}`).

## Method summary

- **Sampling**: `interval = round(orig_fps / target_fps)`, keep every
  `interval`-th frame, convert to grayscale. `N` sampled frames give `N-1`
  consecutive pairs.
- **Global motion model**: for each pair detect ORB keypoints, brute-force
  Hamming match, estimate homography `H` with RANSAC. If matches/inliers are
  insufficient, fall back to a pure-translation model from the **median**
  optical flow (robust to the dynamic-object minority).
- **Egomotion** (per pair, each axis checked independently, see
  `references/method-notes.md`):
  - Transform the image center through `H`; `dx>0 => Pan Left`,
    `dx<0 => Pan Right`; `dy>0 => Tilt Up`, `dy<0 => Tilt Down` (sign
    inversion: camera motion is opposite to apparent scene motion). Tilt uses
    a higher threshold than pan.
  - Transform quadrant-center points; mean distance-from-center ratio `>1`
    => Dolly In, `<1` => Dolly Out.
  - Rotation angle `atan2(h21,h11)` beyond a floor => Roll (sign documented in
    references; validate against the clip if a reference is available).
  - No axis above threshold => `Stay`. Then apply short temporal majority
    smoothing and run-length merge into `start->end` intervals.
- **Dynamic masks** (per pair): dense Farneback flow; expected flow from `H`
  computed per pixel by projecting the coordinate grid; residual =
  actual - expected; adaptive magnitude threshold; morphological open/close;
  connected-component area filtering; optional edge-margin suppression. The
  final frame duplicates the last pair's mask.

All thresholds are parameters with resolution-relative defaults (see script
`--help`-style config keys). They are a calibrated starting point, not tuned to
any hidden class distribution; adjust them from data/validation if a reference
becomes available. Do not assume a majority class or suppress a label.

## How the executor runs it

The single entrypoint reads a JSON config on stdin and writes a JSON summary on
stdout, creating the two deliverable files as a side effect:

```bash
echo '{"video_path":"/root/input.mp4","fps":5,
       "out_instructions":"/root/pred_instructions.json",
       "out_masks":"/root/pred_dyn_masks.npz"}' \
  | python3 /app/environment/skills/current/scripts/run.py
```

All config keys are optional; omitted keys use the defaults above. The stdout
summary reports `num_frames` (N), `shape`, output paths, number of intervals,
and per-frame mask pixel counts for inspection.

If OpenCV is missing, install it first (internet is allowed):
`pip install opencv-python-headless numpy`.

## Validating the output

After running, validate structure and self-consistency (does not need a
reference answer):

```bash
echo '{"instructions":"/root/pred_instructions.json",
       "masks":"/root/pred_dyn_masks.npz"}' \
  | python3 /app/environment/skills/current/scripts/validate.py
```

`validate.py` checks: every interval key parses as `start<end`; the union of
expanded indices is exactly `0 .. N-1` with the final interval ending at `N`;
all labels are from the valid set and every value list is non-empty; the npz
has `shape` plus `f_{i}_*` keys for `i=0..N-1`; each CSR reconstructs to an
`H x W` boolean mask (indptr length `H+1`, monotonic, final value equals
`len(indices)`, indices sorted within rows and `< W`); and that the number of
masks equals the number of expanded instruction frames. It emits JSON
`{"ok":true,...}` or `{"ok":false,"errors":[...]}`.

Treat a validation failure or a non-zero exit as a real failure to fix, not a
pass. When regenerating is required, rerun `run.py` (it rebuilds both files
from the video) rather than hand-editing outputs.

## Failure handling / assumptions

- Unreadable video or zero decoded frames: the script exits non-zero with an
  error message on stderr; verify the `video_path`.
- `N == 1` (clip shorter than one sample interval): one frame labeled `Stay`
  with an empty mask.
- Insufficient feature matches on a pair: median-flow fallback is used and the
  summary flags that pair; this still yields valid outputs.
- Roll sign and exact thresholds are the two least-certain choices; they are
  isolated as config/reference values for easy correction.
