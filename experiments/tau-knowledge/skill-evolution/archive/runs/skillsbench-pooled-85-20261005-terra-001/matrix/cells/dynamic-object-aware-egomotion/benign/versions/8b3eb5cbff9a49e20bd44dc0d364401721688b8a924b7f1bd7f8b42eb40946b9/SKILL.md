---
name: dynamic-object-aware-egomotion
version: 1.1.0
description: Analyze a monocular video at a target sample rate and produce complete half-open camera-motion intervals plus a valid per-sampled-frame dynamic-object CSR mask archive. Use when Stay/Dolly/Pan/Tilt/Roll labels and independent-motion masks are required.
---

# Dynamic-object-aware egomotion and masks

This Skill provides an executable OpenCV/Numpy pipeline for the required video artifacts. It samples the input at `5` fps by default, estimates spatially distributed RANSAC background transforms for each pair of samples, classifies camera motion using documented image-displacement signs, and writes complete binary dynamic masks in CSR form.

## Runtime requirements

Python 3, `numpy`, and `opencv-python` (`cv2`) must be available. The supplied video must be readable by OpenCV. The pipeline uses no network access, downloads, or external model.

## Run

Pass a JSON object on standard input:

```bash
python3 scripts/analyze_video.py <<'JSON'
{"video":"/root/input.mp4","fps":5,"instructions_out":"/root/pred_instructions.json","masks_out":"/root/pred_dyn_masks.npz"}
JSON
```

On success, stdout contains a JSON object with `status: "ok"`, the two output paths, sample count, image shape, and model diagnostics. Invalid input, unreadable video, or artifact-writing failure produces `status: "error"` and a nonzero exit status.

### Input schema

```json
{
  "video": "/path/to/input.mp4",
  "fps": 5.0,
  "instructions_out": "/path/to/pred_instructions.json",
  "masks_out": "/path/to/pred_dyn_masks.npz",
  "smooth_labels": false,
  "residual_sigma": 3.0,
  "residual_floor": 0.75
}
```

Only `video` is required. Defaults are `/root/input.mp4`, `5.0`, `/root/pred_instructions.json`, `/root/pred_dyn_masks.npz`, `false`, `3.0`, and `0.75`. `fps` must be positive and residual settings must be nonnegative. Label smoothing is disabled by default because a brief, well-supported camera movement must not be erased; it is only appropriate when an executor explicitly requests it.

## Method

1. Decode source frames and select frames at source-frame positions separated by `source_fps / target_fps`, beginning with source frame zero. The first decoded resolution is retained for all samples.
2. For every adjacent sampled pair, use ORB ratio matches and a spatial-coverage check. Estimate both a RANSAC homography and a RANSAC partial affine background model. The affine model, when reliably supported by distributed inliers, is the primary motion-classification model because it robustly measures center displacement without local moving-object flow dominating the decision. The homography is retained for static-flow compensation.
3. Transform the image center with the selected robust background model. Positive image `dx` emits `Pan Left`; negative image `dx` emits `Pan Right`. Positive image `dy` emits `Tilt Up`; negative image `dy` emits `Tilt Down`. Local scale and rotation independently emit Dolly and Roll labels. The no-motion threshold is based on transform reprojection noise but bounded conservatively, so a clear global translation is never suppressed by a high flow-residual field. `Stay` is emitted only if no axis is present.
4. Compute Farneback flow, subtract flow predicted by the RANSAC homography, and threshold robust residual magnitude. If no homography is available, use median-flow compensation. Resolution-scaled cleanup, component filtering, and conservative forward temporal support suppress isolated flow artifacts without marking globally explained background as dynamic.
5. Assign each pair label to its source sampled frame and duplicate the last pair label for the final sampled frame. Run-length encode equal label lists as contiguous half-open `start->end` intervals.
6. Store every boolean mask as CSR arrays `f_i_data`, `f_i_indices`, and `f_i_indptr`; shared `shape` is `[H, W]`. `data` stores True values only, each row's columns are ordered, and every pointer array has `H + 1` elements.

## Validation and deliverables

Before writing, the script verifies that intervals are nonempty, contiguous, and cover exactly every sampled-frame index. It also validates mask dimensions and CSR pointer/value invariants. The executor must retain the exact declared output paths; the generated `/root/pred_instructions.json` and `/root/pred_dyn_masks.npz` are the requested deliverables. A one-sampled-frame video receives one `Stay` interval and one valid all-false CSR mask.

## Limitations

A single global homography is most reliable for planar or rotation-dominated backgrounds. Depth parallax, occlusion, blur, and textureless scenes can make independent motion ambiguous. The implementation degrades to median-flow compensation when a homography cannot be estimated and never omits required frame entries. A robust affine model is used only when its inliers have broad spatial support, avoiding use of a cluster on a moving object as egomotion.
