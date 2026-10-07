---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video as consecutively numbered grayscale PNG files, count supplied sprite templates in each final frame, and write a strict CSV. Use for the Super Mario task requiring /root/keyframes_%03d.png and /root/counting_results.csv.
---

# Codec-keyframe template counting

This skill produces exactly one final PNG per codec keyframe and exactly one CSV record per final PNG. It preserves presentation order and does not substitute sampled frames.

## Method

1. Check the video, the three template images, `ffprobe`, `ffmpeg`, OpenCV, and NumPy.
2. Read the codec keyframe flags using `ffprobe`'s `frame=key_frame` metadata, the same definition used by delivery validation.
3. Extract using FFmpeg's decoded-frame `select=eq(key\,1)` filter, rather than decoder `-skip_frame`. This retains every frame marked as a codec keyframe, including keyframes which a decoder-level skip mode might omit. If a codec/filter implementation disagrees with the metadata count, the script retries using the numbered `ffprobe` keyframe positions and rejects any remaining mismatch.
4. Generate frames in a temporary staging directory. The final `/root/keyframes_*.png` files and CSV are replaced only after the complete staged set has been extracted, converted, counted, and validated.
5. Reopen each extracted PNG, convert it to one grayscale channel in place, and reopen it to verify that the saved image is single-channel grayscale.
6. Convert each template through the same grayscale pipeline. For each template, find local correlation maxima, calibrate a threshold from the supplied frames and template, and apply score-ordered non-maximum suppression so nearby response pixels do not become separate objects.
7. Write the CSV only after all final frame files exist. Reopen and validate the CSV header, ordered frame IDs, non-negative integer counts, grayscale images, and one-record-per-frame relationship.

Counts are per codec keyframe, not video-wide deduplicated totals. The supplied templates are assumed to represent target sprites at the rendered scale in the video.

## Runtime interface

Run `scripts/analyze_mario.py` with one JSON object on standard input. It emits one JSON object on standard output.

Required fields:

- `video_path`: readable video path.
- `templates`: object containing exactly `coins`, `enemies`, and `turtles`; each value is a readable image path.

Optional fields:

- `output_dir`: final PNG directory; default `/root`.
- `keyframe_prefix`: PNG filename prefix; default `keyframes_`.
- `frame_id_dir`: absolute directory represented in CSV IDs; default `output_dir`.
- `csv_path`: CSV destination; default `/root/counting_results.csv`.

For the supplied task, run the complete entrypoint after the public inputs are available:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

Success output has `"ok": true`, equal `codec_keyframes` and `frames` values, and `"validation":{"ok":true,...}`. The CSV header is exactly:

```text
frame_id,coins,enemies,turtles
```

The records name `/root/keyframes_001.png` through the final consecutive frame number in timeline order. Do not deliver artifacts if the program reports `ok: false`.

## Failure behavior

The script emits `{"ok":false,"error":"..."}` and exits nonzero for malformed JSON, missing inputs or programs, unavailable Python dependencies, zero metadata keyframes, extraction failure, metadata/file count mismatch, nonconsecutive output names, unreadable images, incompatible templates, output failures, or final validation failure. Staged files are removed on failure; correct the reported issue and rerun the complete entrypoint rather than combining a partial extraction with an older CSV.
