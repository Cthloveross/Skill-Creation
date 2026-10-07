---
name: dynamic-object-aware-egomotion
version: 1.0.0
description: Analyze an input video at a requested sampling rate, write half-open per-sampled-frame camera-motion intervals, and write per-frame dynamic-object masks as validated CSR arrays in an NPZ file. Use for monocular video tasks requiring Stay/Dolly/Pan/Tilt/Roll labels and independently moving-object masks.
---

# Dynamic-object-aware egomotion and masks

This Skill packages a runnable OpenCV/Numpy pipeline. It samples the supplied video at the requested rate (default `5.0` fps), estimates a robust global homography for each adjacent sample pair, and uses dense optical-flow residuals relative to that global model as dynamic-object evidence.

## Runtime requirements

The executor needs Python 3 with `opencv-python` (`cv2`) and `numpy`. The input video must be readable by OpenCV. No network access or external model downloads are used.

## Run

Invoke the script with one JSON object on standard input:

```bash
python3 scripts/analyze_video.py <<'JSON'
{"video":"/root/input.mp4","fps":5,"instructions_out":"/root/pred_instructions.json","masks_out":"/root/pred_dyn_masks.npz"}
JSON
```

The script emits one JSON result object on stdout. On success it contains `status: "ok"`, output paths, sampled-frame count, and diagnostics. On a bad input or output failure it emits `status: "error"` with a message and exits nonzero.

### Input schema

```json
{
  "video": "/path/to/input.mp4",
  "fps": 5.0,
  "instructions_out": "/path/to/pred_instructions.json",
  "masks_out": "/path/to/pred_dyn_masks.npz",
  "smooth_labels": true,
  "residual_sigma": 3.0,
  "residual_floor": 0.75
}
```

Only `video` is required. Defaults are `/root/input.mp4`, `5.0`, `/root/pred_instructions.json`, `/root/pred_dyn_masks.npz`, `true`, `3.0`, and `0.75` respectively. `fps` must be positive. The residual settings are exposed because flow noise and motion scale depend on source footage; the default threshold is otherwise adaptive from the median and MAD of each residual field.

## Method

1. Decode frames near uniform target timestamps and convert them to grayscale for geometry.
2. For each adjacent pair, use ORB descriptor matches and RANSAC homography estimation. A model is accepted only when it has adequate inlier count and spatial extent. If unavailable, median dense flow supplies the global fallback.
3. Evaluate the local homography at the image center. Its center displacement supplies pan/tilt; its local Jacobian supplies scale and roll. Thresholds derive from robust residual noise with explicit floors. Image displacement signs follow the required convention: positive content `dx` is `Pan Left`, negative `dx` is `Pan Right`; positive content `dy` is `Tilt Up`, negative `dy` is `Tilt Down`. Multiple independent motion labels may be emitted. Roll names describe camera roll, hence are opposite to apparent image rotation.
4. Compute Farneback flow and subtract homography-predicted flow (or median flow fallback). Threshold its robust residual magnitude, apply resolution-scaled morphology and connected-component cleanup, and use forward-warped neighboring masks as conservative temporal support. The last sampled frame receives the forward-propagated last pair mask.
5. Assign each pair label to its source sampled frame and duplicate the final pair label for the final sampled frame. Optionally remove isolated one-frame label flicker. Merge equal label lists into `start->end` half-open intervals.
6. Encode every final dense boolean mask as CSR. `shape` is `[H, W]`; every frame has `f_i_data`, `f_i_indices`, and `f_i_indptr`, with sorted columns and an `indptr` of length `H + 1`.

## Output validation

Before saving, the script validates that instruction intervals are contiguous, nonempty, and cover exactly `0..N-1`, and it reconstructs/validates CSR invariants for every frame: correct key set, monotonic pointers, final pointer equal to data length, in-range sorted columns, and `H+1` row pointers. The executor should treat a non-`ok` script result as a failed artifact run; otherwise the declared JSON and NPZ paths are the required deliverables.

## Limitations and handling

A single homography is best for rotation-dominated or planar backgrounds. Strong depth parallax can create residuals that resemble moving objects; conservative morphology and temporal support reduce, but cannot fully eliminate, this ambiguity. If feature matching fails, the implementation continues using median-flow global compensation rather than producing malformed or missing outputs. A video yielding one sampled frame receives a `Stay` interval and an all-false, valid CSR mask.
