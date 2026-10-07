---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNG files, count supplied sprite templates in each final frame, and write a strict CSV. Use for the Super Mario object-counting task requiring /root/keyframes_%03d.png and /root/counting_results.csv.
---

# Codec-keyframe template counting

This skill produces exactly one final PNG for every codec keyframe and exactly one CSV row for every final PNG. It preserves the video decode/presentation sequence and does not substitute arbitrary sampled frames.

## Method

1. Verify the video, the three supplied templates, `ffprobe`, `ffmpeg`, OpenCV, and NumPy.
2. Use `ffprobe` frame metadata to enumerate every video frame and identify every frame whose `key_frame` flag is `1`.
3. Remove stale owned `keyframes_*.png` files and the prior destination CSV.
4. Extract precisely those frame ordinals with FFmpeg's `select` filter and `-vsync 0`. Selecting explicit ordinals derived from the same `ffprobe` metadata avoids relying on FFmpeg's `key` filter variable, which can be inconsistent across codecs/builds. The script requires the resulting numbered PNG count to equal the metadata count.
5. Reopen each written PNG, convert it to a single grayscale channel, overwrite it in place, and reopen it again to confirm its saved representation is grayscale.
6. Convert templates through the same grayscale pipeline. For each frame/template pair, use normalized template correlation, local-maxima candidates, and score-ordered non-maximum suppression. Thresholds are calibrated from each current response map using Otsu separation and a high background quantile; no fixed correlation cutoff is assumed.
7. After all final frames exist, write `counting_results.csv`, then reopen and validate every image and CSV row. The CSV is only created after successful final-frame generation.

The counts are per keyframe, not deduplicated totals over the video. Templates are assumed to depict the target sprites at the rendered scale used in the video.

## Runtime interface

Run `scripts/analyze_mario.py` with one JSON object on standard input. It emits one JSON object on standard output.

Required JSON fields:

- `video_path`: source MP4/video path.
- `templates`: object with exactly these keys: `coins`, `enemies`, and `turtles`; each value is a readable template image path.

Optional JSON fields:

- `output_dir`: directory for PNGs, default `/root`.
- `keyframe_prefix`: filename prefix, default `keyframes_`.
- `frame_id_dir`: absolute directory used in CSV frame IDs, default `output_dir`.
- `csv_path`: destination CSV, default `/root/counting_results.csv`.

For this task, execute the complete entrypoint after the supplied inputs are present:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful response has `"ok": true`, reports matching `codec_keyframes` and `frames` counts, and includes `"validation":{"ok":true,...}`. The resulting header is exactly:

```text
frame_id,coins,enemies,turtles
```

The `frame_id` values are `/root/keyframes_001.png` through the last consecutive number in timeline order.

## Failure behavior

The script emits `{"ok":false,"error":"..."}` and exits nonzero for invalid JSON, missing inputs/programs, unavailable Python dependencies, zero codec keyframes, failed extraction, a metadata/file-count mismatch, nonconsecutive output names, unreadable images, incompatible template dimensions, unwritable output, or validation failure. It removes the prior owned CSV before extraction, so a stale CSV cannot claim to describe a partial new frame set. Correct the reported problem and rerun the whole entrypoint rather than combining artifacts from separate runs.
