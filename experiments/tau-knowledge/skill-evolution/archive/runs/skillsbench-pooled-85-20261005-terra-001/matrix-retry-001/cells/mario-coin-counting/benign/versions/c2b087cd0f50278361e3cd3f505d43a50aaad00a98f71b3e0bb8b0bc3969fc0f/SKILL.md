---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNGs, count supplied object templates in each final frame, and produce a one-row-per-frame CSV. Use for video tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when requested frames are **codec keyframes**, not periodic samples. Counts are per saved keyframe and do not deduplicate objects over time.

## Required workflow

1. Use `ffprobe` to count every `key_frame=1` video-frame record.
2. Extract those same decoded keyframes in presentation order with FFmpeg's `select=eq(key\,1)` frame selector. Do not use frame-rate conversion or arbitrary timestamp sampling.
3. Save the selected frames to a staging directory as `keyframes_%03d.png`, then reopen and overwrite each as a native one-channel grayscale PNG.
4. Convert templates through the same grayscale conversion. Use normalized template matching, local response peaks, and template-scale non-maximum suppression. Do not count all score-map pixels above a threshold.
5. Build and validate the CSV only after every staged frame exists. Publish all validated frames first, then publish the CSV.

The entrypoint checks that the written PNG count exactly equals the codec-keyframe count. It never deliberately writes a CSV referring to unstaged or missing frames.

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

Success output contains `ok: true`, with equal `codec_keyframes` and `frames` values and `validation.ok: true`. For `N` keyframes, final files must be `/root/keyframes_001.png` through `/root/keyframes_NNN.png`, and the CSV must contain exactly `N` ordered records with this exact header:

```text
frame_id,coins,enemies,turtles
```

## Validation and failure handling

The runtime needs `ffprobe`, `ffmpeg`, Python, NumPy, and OpenCV (`cv2`). The video and all templates must be readable. On malformed configuration, missing dependencies, extraction/count disagreement, unreadable images, non-grayscale outputs, or CSV validation errors, the script emits `{"ok":false,"error":"..."}` and exits nonzero. Resolve the reported issue and rerun the full entrypoint; do not hand-create rows for frames that have not been written.
