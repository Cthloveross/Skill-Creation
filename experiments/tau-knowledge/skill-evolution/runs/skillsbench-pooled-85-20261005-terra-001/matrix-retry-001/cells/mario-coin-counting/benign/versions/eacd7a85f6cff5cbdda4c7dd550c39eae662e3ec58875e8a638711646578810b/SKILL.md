---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video as consecutively numbered grayscale PNGs, count supplied object templates in each final frame, and create a matching CSV. Use for Super Mario-style video tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when the requested frames are **codec keyframes**, rather than periodic samples. Counts are per saved keyframe; do not perform temporal deduplication.

## Required method

1. Inspect `frame=key_frame` with `ffprobe`. Its decoded presentation-order indexes are the authoritative selection list.
2. Extract that exact index list in one FFmpeg invocation with an explicit `select` filter. Do not extract based on FPS, duration, timestamps, or arbitrary I-frames.
3. Require the generated staging directory to contain exactly the metadata count under consecutive names `keyframes_001.png` through `keyframes_NNN.png`.
4. Reopen and overwrite every extracted PNG as a native one-channel grayscale PNG.
5. Apply the same grayscale conversion to each template. Use local template-match peaks plus non-maximum suppression, rather than counting every score-map pixel above a threshold.
6. Publish all final frame files, then build the CSV from the published ordered file list. The CSV must contain exactly one row per file, with this exact header:

```text
frame_id,coins,enemies,turtles
```

The entrypoint first removes stale numbered outputs and the previous destination CSV. It stages extraction before publication, so a prior incomplete result cannot be mistaken for the current run.

## Runtime interface

Run `scripts/analyze_mario.py` once. It receives one JSON object on stdin and emits one JSON object on stdout.

Required JSON fields:

- `video_path`: readable video path.
- `templates`: object containing exactly `coins`, `enemies`, and `turtles`; each value is a readable template image path.

Optional JSON fields:

- `output_dir`: directory receiving extracted PNGs; default `/root`.
- `keyframe_prefix`: filename prefix; default `keyframes_`.
- `frame_id_dir`: directory represented by CSV frame IDs; default `output_dir`.
- `csv_path`: output CSV path; default `/root/counting_results.csv`.

For this task, invoke exactly:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful response has this schema:

```json
{"ok":true,"codec_keyframes":8,"frames":8,"csv_path":"/root/counting_results.csv","extraction_method":"ffprobe_frame_indexes","validation":{"ok":true,"frames_checked":8,"csv_rows_checked":8}}
```

The numeric values above only illustrate the response shape. For a successful run, `codec_keyframes` always equals `frames`; actual values are determined from the supplied video.

## Validation and failures

The runtime requires Python 3, NumPy, OpenCV, FFmpeg, and ffprobe. Before success is reported, the script validates all of the following:

- extracted count equals codec-keyframe metadata count;
- names are consecutive from `001`;
- every final output is a readable native grayscale PNG;
- CSV header, order, row count, frame IDs, and non-negative integer count fields are exact.

On any missing dependency/input, failed FFmpeg extraction, mismatch, invalid image, or invalid CSV, stdout is `{"ok":false,"error":"..."}` and the process exits nonzero. Correct the condition and rerun the complete entrypoint; never make CSV rows for absent frame files.
