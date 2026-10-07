---
name: mario-template-frame-counter
description: >
  Extract codec key frames from a gameplay/screen-recording video, convert each
  extracted frame to grayscale in place, count repeated sprite instances
  (coins, enemies, turtles, or any supplied templates) per frame with grayscale
  template matching plus non-maximum suppression, and write one tabular record
  per frame. Use this when a task gives a video plus small reference sprite
  images and asks for a per-key-frame count CSV. Thresholds and scales are
  parameters to be calibrated on the actual video, not fixed answers.
---

# Mario / sprite per-frame template counting

This Skill turns a video plus small template images into a CSV with one row per
extracted key frame and an integer count column per template object. It mirrors
the public task "mario-coin-counting": extract key frames -> grayscale in place
-> template-match -> CSV.

## What the task requires (read the live request at runtime)

The public opening for this instance asks to:
1. Extract **codec key frames** from the input video into the work folder as
   `keyframes_%03d.png` (1-indexed, presentation/timeline order).
2. Confirm the template sprite images exist.
3. Convert every extracted key frame to grayscale **in place** (overwrite the
   original RGB PNG).
4. Count coins using `coin.png` as template on each frame.
5. Repeat for enemies (`enemy.png`) and turtles (`turtle.png`).
6. Write a CSV with columns `frame_id,coins,enemies,turtles`, where `frame_id`
   is the absolute path `/root/keyframes_%03d.png` for each frame, sorted in
   timeline order, one row per key frame.

Always re-read the live `public_inputs.opening`, `environment.copies`,
`environment.workdir`, and `public_input_manifest` for the exact paths and the
exact CSV output location before running. Do not hardcode counts: the counts
must be computed from the supplied video and templates. The CSV output path and
column names come from the live request (for this instance the opening names
`/root/counting_results.csv` and columns `frame_id,coins,enemies,turtles`).

## Method and assumptions

- **Key-frame extraction** uses ffmpeg `-skip_frame nokey` with passthrough
  sync so only self-contained (I) frames are written, preserving presentation
  order with no frame-rate duplication/dropping. ffmpeg numbers `%03d` starting
  at 001. Confirm the written files afterward (count + ordering).
- **Grayscale in place** reads each frame as color, converts BGR->GRAY, and
  overwrites the same path as a single-channel PNG. Both the frame (read with
  `IMREAD_GRAYSCALE`) and each template (converted to gray) go through the same
  grayscale pipeline before matching, as the background requires.
- **Counting** uses `cv2.matchTemplate` with `TM_CCOEFF_NORMED` over a small
  set of scales (templates may not be at the video's native sprite scale),
  thresholds the score map, then applies IoU non-maximum suppression so each
  object cluster is counted once rather than per above-threshold pixel.
- **No threshold is universal.** Defaults are provided (threshold 0.70, scales
  0.5..2.0, IoU 0.3) but you should calibrate with `scripts/calibrate.py`,
  compare positive peaks against background responses, and confirm that small
  threshold changes do not swing counts wildly. Adjust per-object thresholds in
  the pipeline config if a template is noisy on a repetitive background.

## Scripts (all take JSON on stdin, emit JSON on stdout)

- `scripts/extract_keyframes.py`
  - in: `{"video": path, "out_dir": dir, "basename": "keyframes"}`
  - out: `{"frames": [paths sorted], "count": N}`
- `scripts/to_grayscale.py`
  - in: `{"frames": [paths]}`
  - out: `{"converted": [paths], "all_grayscale": true/false, "shapes": [...]}`
- `scripts/count_objects.py`
  - in: `{"frames":[paths], "templates":{"coins":p,"enemies":p,"turtles":p},`
    `"thresholds":{...}|0.7, "scales":[...], "iou":0.3}`
  - out: `{"results":[{"frame":p,"coins":n,"enemies":n,"turtles":n}, ...]}`
- `scripts/calibrate.py` (diagnostic only, does not write outputs)
  - in: `{"frames":[paths], "templates":{name:path}, "scales":[...], "top":5}`
  - out: per template: best per-frame peak scores so you can pick a threshold.
- `scripts/run_pipeline.py` (end-to-end entrypoint, writes the CSV)
  - in (all optional, sensible defaults for this task):
    `{"video":"/root/super-mario.mp4", "out_dir":"/root",`
    `"templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png",`
    `"turtles":"/root/turtle.png"}, "csv":"/root/counting_results.csv",`
    `"columns":["coins","enemies","turtles"], "thresholds":0.7,`
    `"scales":[0.5,0.75,1.0,1.25,1.5,2.0], "iou":0.3}`
  - out: `{"csv":path, "rows":N, "frames":N, "results":[...], "all_grayscale":bool}`
  - It extracts frames, converts them to grayscale in place, counts, writes the
    CSV (header `frame_id` + the column names, integer counts, one row per
    frame sorted by index), and validates row count == frame count.

Scripts resolve `scripts/matching.py` for shared helpers via their own
directory, so run them from anywhere.

## Runnable example

```bash
cd /app/environment/skills/current   # or wherever this Skill is installed

# One-shot: do everything with task defaults.
echo '{"video":"/root/super-mario.mp4","out_dir":"/root",
  "templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png",
  "turtles":"/root/turtle.png"},"csv":"/root/counting_results.csv",
  "columns":["coins","enemies","turtles"]}' \
  | python3 scripts/run_pipeline.py
```

Calibration before trusting a threshold:

```bash
# After extraction+grayscale, inspect peak scores to choose thresholds.
echo '{"frames":["/root/keyframes_001.png"],
  "templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png",
  "turtles":"/root/turtle.png"},"scales":[0.5,0.75,1.0,1.25,1.5,2.0]}' \
  | python3 scripts/calibrate.py
```

## Validation the executor should run

1. `extract_keyframes` wrote `count` files; `ls /root/keyframes_*.png` matches
   and names are contiguous `001..NNN`.
2. After grayscale, `all_grayscale` is true (each PNG is single channel).
3. The CSV opens with header exactly `frame_id` + the requested columns, has
   exactly `frames` data rows, counts are integers, `frame_id` values are the
   `/root/keyframes_%03d.png` paths in sorted order, and there are no extra
   rows/columns. `run_pipeline.py` asserts `rows == frames` and raises on
   mismatch.
4. Re-run `run_pipeline.py` to confirm the entrypoint regenerates the CSV
   deterministically.
5. Sanity-check counts against `calibrate.py` peaks; if a column is uniformly 0
   or implausibly large, lower/raise that template's threshold or widen scales,
   and confirm stability under a small threshold perturbation.

## Failure handling

- Missing ffmpeg: `extract_keyframes.py` reports a clear error; install or use
  the system ffmpeg named in the environment background.
- Missing template/video path: scripts raise with the offending path.
- Template larger than a frame at a given scale: that scale is skipped.
- If no key frames are produced (unusual codec), fall back to extracting I-like
  frames via `select='eq(pict_type,I)'` (documented in
  `references/notes.md`).
