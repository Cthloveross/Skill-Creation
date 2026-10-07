---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNG files, count supplied sprite templates in each final frame, and write a strict CSV. Use for the Super Mario object-counting task requiring /root/keyframes_%03d.png and /root/counting_results.csv.
---

# Codec-keyframe template counting

This skill creates exactly one final PNG for each codec keyframe and exactly one CSV record for each final PNG. It keeps presentation order and does not substitute arbitrary sampled frames.

## Method

1. Check the video, all three templates, `ffprobe`, `ffmpeg`, OpenCV, and NumPy.
2. Count codec keyframes with the same `ffprobe frame=key_frame` metadata definition used for delivery validation.
3. Remove stale owned `keyframes_*.png` files and the prior CSV before generating new artifacts.
4. Decode only codec keyframes with FFmpeg's decoder-level `-skip_frame nokey` input option. This avoids a long, fragile `select` expression and writes the complete keyframe sequence directly as consecutively numbered PNGs. The script rejects the result unless the number of written PNGs equals the metadata count.
5. Reopen every extracted PNG, convert it to one grayscale channel, overwrite it in place, and reopen it again to verify the saved PNG is single-channel grayscale.
6. Convert each template through the same grayscale pipeline. Where a template has alpha, use its nontransparent pixels as a match mask. For every template, collect local correlation peaks across the final frames, calibrate a template-specific threshold from those current peak scores, and apply score-ordered non-maximum suppression.
7. Only after all final frames exist, write `counting_results.csv`, reopen it, and validate schema, path ordering, integer counts, grayscale images, and one record per final PNG.

Counts are per codec keyframe, not video-wide deduplicated totals. The supplied templates are assumed to show the target sprite at the rendered scale in the video.

## Runtime interface

Run `scripts/analyze_mario.py` with one JSON object on standard input. It emits one JSON object on standard output.

Required fields:

- `video_path`: readable MP4/video path.
- `templates`: object with exactly `coins`, `enemies`, and `turtles`, each a readable image path.

Optional fields:

- `output_dir`: output PNG directory; default `/root`.
- `keyframe_prefix`: filename prefix; default `keyframes_`.
- `frame_id_dir`: absolute directory represented in CSV IDs; default `output_dir`.
- `csv_path`: CSV destination; default `/root/counting_results.csv`.

For the supplied task, run the complete entrypoint after its input files are available:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful response contains `"ok": true`, identical `codec_keyframes` and `frames` values, and `"validation":{"ok":true,...}`. The CSV header is exactly:

```text
frame_id,coins,enemies,turtles
```

Its IDs are `/root/keyframes_001.png` through the final consecutive number, in timeline order.

## Failure behavior

The script emits `{"ok":false,"error":"..."}` and exits nonzero for malformed JSON, missing inputs or programs, unavailable Python dependencies, zero metadata keyframes, extraction failure, metadata/file count mismatch, nonconsecutive output names, unreadable images, incompatible templates, output failures, or final validation failure. Correct the reported issue and rerun the complete entrypoint; do not combine CSV records with frames from a partial earlier run.
