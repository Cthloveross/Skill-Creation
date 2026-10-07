---
name: dynamic-object-aware-egomotion
version: 1.0.0
description: Analyze a video sampled at a requested FPS to create half-open camera-motion intervals and per-sampled-frame dynamic-object masks in CSR NPZ format. Use for monocular video tasks requiring Stay, Dolly, Pan, Tilt, and Roll labels together with sparse dynamic masks.
---

# Dynamic-object-aware egomotion

This Skill uses robust feature-based global motion estimation as the camera-motion model, then marks independently moving regions from dense-flow residuals relative to that model. It writes the two task deliverables directly and validates their structural invariants before reporting success.

## Runtime requirements

The runtime needs Python 3 with `numpy` and OpenCV (`cv2`) including video I/O. The input video must be readable by OpenCV. No network access is needed.

## Entrypoint

Run `scripts/process_video.py`. It reads one JSON object from standard input and writes a JSON result/status object to standard output.

Input schema:

```json
{
  "input_video": "/root/input.mp4",
  "instructions_output": "/root/pred_instructions.json",
  "masks_output": "/root/pred_dyn_masks.npz",
  "sample_fps": 5
}
```

All paths are optional only when using the corresponding defaults shown above. `sample_fps` must be positive and defaults to 5. The script samples at timestamps spaced by `1/sample_fps`; it does not assume that source FPS is an integer multiple of the requested rate.

Example:

```sh
printf '%s\n' '{"input_video":"/root/input.mp4","instructions_output":"/root/pred_instructions.json","masks_output":"/root/pred_dyn_masks.npz","sample_fps":5}' | python3 scripts/process_video.py
```

## Method

For each adjacent sampled-frame pair, the script:

1. detects ORB features, ratio-matches descriptors, and estimates a RANSAC homography when its inlier geometry is adequate;
2. estimates dense Farneback flow;
3. derives camera translation, local scale, and rotation from the global transform. If robust homography estimation is unavailable, it uses median dense flow for translation and explicitly avoids unsupported scale/roll claims;
4. independently emits every camera-motion axis whose magnitude exceeds a resolution- and residual-aware noise threshold. Thus compound labels are possible, while no detected axis is represented by `Stay`;
5. computes the flow expected under the homography, subtracts it from actual flow, adaptively thresholds robust residual outliers, and applies scale-aware morphology/component cleanup. With no homography, median-flow residuals are used instead.

A pair's dynamic evidence supports both of its endpoint frames. Endpoint masks are conservatively fused with adjacent-pair evidence, so the first and last sampled frames are not silently made empty. The final transition's motion labels are assigned to both of its endpoint sampled indices as required.

The JSON interval writer run-length-encodes identical label lists. Its intervals are half-open and cover every sampled-frame index exactly once. The NPZ contains `shape` as `[H, W]` and for every sampled index `i`, `f_i_data`, `f_i_indices`, and `f_i_indptr`. Indices are sorted by row/column and `indptr` has length `H + 1`.

## Failure handling and validation

Unreadable or frame-less inputs cause a JSON error response and a nonzero exit; no success status is claimed. A one-frame readable video produces one `Stay` interval and an empty CSR mask. Before success, the script validates interval coverage, label vocabulary, CSR pointer monotonicity, index bounds, and the presence of all expected frame keys. Inspect its stdout result for sampled-frame count, frame size, output paths, and whether any pair required fallback global motion.
