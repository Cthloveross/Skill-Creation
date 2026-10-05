---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video as consecutively numbered grayscale PNG files, count supplied sprite templates on each final frame, and write a CSV with exactly one ordered record per frame. Use for Super Mario-style video/template counting tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when the requested images are **codec keyframes**, rather than arbitrary periodic video samples. Counts are per saved frame; they are not video-wide deduplicated totals.

## Method

1. Inspect the input video with `ffprobe` and treat every video-frame `key_frame=1` flag as required output.
2. Extract all keyframes in one FFmpeg pass to a staging directory. The script uses FFmpeg's keyframe-only decode mode, preserving presentation order and avoiding a frame-rate conversion. If that decoder mode does not agree with `ffprobe`, it retries with FFmpeg's decoded-frame key flag selector.
3. FFmpeg writes each extracted image with gray pixel format. The script reopens every saved image and requires a one-channel grayscale result before publishing it.
4. Convert templates through the same grayscale pipeline. For every template/frame pair, use normalized template matching, retain spatial local maxima, estimate a conservative cutoff from the observed peak-score distribution, and apply template-scale non-maximum suppression. Do not count every score-map pixel above a cutoff.
5. Build the CSV only after the complete staged frame set is present. Validate the exact header, the consecutive numbering, one record per image, ordered absolute frame IDs, non-negative integer counts, and grayscale saved files before replacing final outputs.

The entrypoint never intentionally publishes a CSV containing references to images that were not successfully staged and validated.

## Runtime interface

Run `scripts/analyze_mario.py` once. It receives one JSON object on stdin and writes one JSON object to stdout.

Required fields:

- `video_path` — readable input video path.
- `templates` — object containing exactly `coins`, `enemies`, and `turtles`, each with a readable template image path.

Optional fields:

- `output_dir` — directory for keyframe PNGs; default `/root`.
- `keyframe_prefix` — image filename prefix; default `keyframes_`.
- `frame_id_dir` — absolute directory represented in CSV `frame_id` values; default `output_dir`.
- `csv_path` — destination CSV path; default `/root/counting_results.csv`.

For the supplied task inputs:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful result has `ok: true`, equal `codec_keyframes` and `frames` values, and `validation.ok: true`. For `N` codec keyframes, the final files are `/root/keyframes_001.png` through `/root/keyframes_NNN.png` in presentation order, and the CSV has exactly `N` data records. Its header is exactly:

```text
frame_id,coins,enemies,turtles
```

## Prerequisites and failure behavior

The runtime must provide `ffprobe`, `ffmpeg`, Python, NumPy, and OpenCV (`cv2`). The supplied video and all three templates must be readable. The script exits nonzero and emits `{"ok":false,"error":"..."}` for invalid JSON/configuration, missing prerequisites, extraction failures, keyframe metadata/file-count disagreement, incompatible images/templates, non-grayscale output, or CSV validation failure. Correct the stated problem and rerun the complete entrypoint; do not retain an old CSV after changing the extracted image set.
