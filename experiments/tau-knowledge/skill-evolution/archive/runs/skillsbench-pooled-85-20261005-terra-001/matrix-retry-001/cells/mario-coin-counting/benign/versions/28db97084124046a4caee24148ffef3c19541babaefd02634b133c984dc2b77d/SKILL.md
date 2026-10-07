---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNGs, count supplied object templates in each final frame, and produce a one-row-per-frame CSV. Use for video tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when requested frames are **codec keyframes**, rather than periodic samples. Counts are per saved keyframe; do not deduplicate objects across time.

## Required workflow

1. Inspect `frame=key_frame` metadata with `ffprobe` and retain the presentation-order frame indexes of every `key_frame=1` record.
2. Extract all selected frames in presentation order. The entrypoint first uses FFmpeg's decoded-frame `key` selector and verifies its output count against `ffprobe`. If a particular FFmpeg build exposes different `key` filter metadata, it falls back to selecting the exact decoded frame indexes obtained from the same `ffprobe` frame listing.
3. Stage every frame as `keyframes_%03d.png`, reopen it, and overwrite it as a native one-channel grayscale PNG.
4. Convert every template through the same grayscale pipeline. Use normalized template matching, local response peaks, and template-scale non-maximum suppression; never count every above-threshold response-map pixel.
5. Create and validate the CSV only after the complete staged frame set exists. Publish all final frames before publishing the CSV.

The script rejects an extraction unless its final PNG count exactly equals the codec-keyframe count. It does not publish a CSV referring to missing staged frames.

## Runtime interface

Run `scripts/analyze_mario.py` once. It reads one JSON object from stdin and writes one JSON object to stdout.

Required JSON fields:

- `video_path`: readable video path.
- `templates`: object with exactly `coins`, `enemies`, and `turtles`; values are readable image paths.

Optional fields:

- `output_dir`: keyframe destination directory, default `/root`.
- `keyframe_prefix`: PNG filename prefix, default `keyframes_`.
- `frame_id_dir`: directory represented by absolute CSV frame IDs, default `output_dir`.
- `csv_path`: CSV destination, default `/root/counting_results.csv`.

For the supplied inputs:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful JSON result has `ok: true`, equal `codec_keyframes` and `frames` values, and `validation.ok: true`. For `N` keyframes, final files are `/root/keyframes_001.png` through `/root/keyframes_NNN.png`, and the CSV has exactly `N` ordered records with this exact header:

```text
frame_id,coins,enemies,turtles
```

## Validation and failure handling

The runtime requires `ffprobe`, `ffmpeg`, Python, NumPy, and OpenCV (`cv2`). The video and all templates must be readable. On missing dependencies, invalid input, failed extraction, metadata/file-count disagreement, unreadable or non-grayscale output, or invalid CSV records, the script emits `{"ok":false,"error":"..."}` and exits nonzero. Resolve the reported condition and rerun the complete entrypoint. Do not hand-create CSV records for frames that were not written.
