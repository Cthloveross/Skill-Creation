---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video in presentation order, overwrite each extracted PNG as grayscale, count supplied image templates per frame, and create a matching CSV. Use for video tasks requiring keyframes_%03d.png files and one ordered count record per codec keyframe.
---

# Codec-keyframe template counting

Use this Skill when “key frames” means the video stream's **codec keyframes**, rather than frames sampled at a regular time interval. Counts are independent per saved frame; do not deduplicate objects across time.

## Required workflow

1. Inspect the input video with `ffprobe` and count `frame=key_frame` records. This is the expected output-frame count.
2. Decode the video normally and use FFmpeg's `select=eq(key\,1)` video filter to emit keyframes in presentation order. The entrypoint uses `-vsync 0` so selected frames are not duplicated by an output frame-rate policy.
3. Require the extracted result to contain exactly the metadata count under consecutive names `keyframes_001.png` through `keyframes_NNN.png`. The script has an I-picture-filter fallback only if the key-flag selector cannot produce the metadata count.
4. Reopen every extracted PNG, convert it to one-channel grayscale, overwrite the same file, and verify that the written PNG is natively grayscale. Convert templates through the same grayscale pipeline for matching.
5. Use template-score local maxima followed by non-maximum suppression. Do not count every score-map pixel above a threshold. Thresholds are calibrated from score peaks in the supplied video and templates and reported in the JSON result.
6. Create the CSV only after all final keyframes have been written and validated. It must have exactly this header and one timeline-ordered row per final frame:

```text
frame_id,coins,enemies,turtles
```

The entrypoint clears stale numbered output files and an old CSV before beginning. It uses staging for extraction and does not write the CSV unless extraction, grayscale conversion, matching, and validation have all succeeded.

## Runtime interface

Run `scripts/analyze_mario.py` once. It reads one JSON object from stdin and emits one JSON object to stdout.

Required input fields:

- `video_path`: readable video file.
- `templates`: object containing exactly `coins`, `enemies`, and `turtles`; each value is a readable image path.

Optional fields:

- `output_dir`: directory for numbered PNGs; defaults to `/root`.
- `keyframe_prefix`: filename prefix; defaults to `keyframes_`.
- `frame_id_dir`: directory represented by `frame_id` values; defaults to `output_dir`.
- `csv_path`: output CSV path; defaults to `/root/counting_results.csv`.

For the supplied task, invoke it with:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A success response contains `ok: true`, matching `codec_keyframes` and `frames` values computed from the current video, the CSV path, extraction selector used, calibration details, and validation results. A failure response is `{"ok":false,"error":"..."}` and has a nonzero process exit.

## Delivery checks

Treat a nonzero process exit or `ok:false` as failure; never deliver partial files or a CSV generated before frame creation finishes. The script validates that:

- ffprobe's codec-keyframe count equals the published PNG count;
- names are consecutive from `keyframes_001.png` with no gaps;
- every saved PNG is readable and natively grayscale;
- the CSV has the exact header, exactly one row per final keyframe, ordered absolute frame IDs, and non-negative integer count fields.

The runtime needs Python 3, NumPy, OpenCV, FFmpeg, and ffprobe. Missing inputs, unavailable executables, failed extraction, invalid image data, or validation mismatches are explicit failures.
