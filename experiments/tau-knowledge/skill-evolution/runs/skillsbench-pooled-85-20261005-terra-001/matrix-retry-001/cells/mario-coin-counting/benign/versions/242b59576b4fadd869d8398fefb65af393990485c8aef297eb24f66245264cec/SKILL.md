---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video in presentation order as consecutively numbered grayscale PNGs, count supplied coin/enemy/turtle templates on each final image, and create a strict frame-aligned CSV. Use for tasks requiring /root/keyframes_%03d.png and /root/counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when each **codec keyframe** of a video must become one numbered image and one CSV row. Counts are per keyframe, not video-wide deduplicated totals.

## Required procedure

1. Run `ffprobe` to obtain the `key_frame` flag for every decoded presentation frame. The number of `1` flags is the required output-image count.
2. Decode each flagged presentation position individually into a staging directory. Individual extraction prevents frame-rate synchronization, image-sequence, or timestamp behavior from silently dropping later selected frames.
3. Reopen every staged PNG, overwrite it in place as a native one-channel grayscale PNG, and reopen it again to verify the saved image is grayscale.
4. Convert every supplied template through the same grayscale pipeline. Use normalized template matching, retain only local score peaks, calibrate a high cutoff from the observed peak-score distribution, and apply template-sized non-maximum suppression. Do not count all response-map pixels above a threshold.
5. Create the CSV only after all final staged images exist. Validate its exact schema, image ordering, row count, absolute frame IDs, non-negative integer counts, and grayscale images before publishing the staged files.

The extractor deliberately compares the number of staged images with the `ffprobe` keyframe count before it publishes anything. A successful run therefore cannot legitimately produce a CSV for eight keyframes while leaving only two PNG files.

## Runtime interface

Run `scripts/analyze_mario.py` once with one JSON object on stdin. It emits one JSON object on stdout.

Required JSON fields:

- `video_path`: readable video path.
- `templates`: object with exactly these keys: `coins`, `enemies`, `turtles`. Each value is a readable template-image path.

Optional JSON fields:

- `output_dir`: keyframe directory; defaults to `/root`.
- `keyframe_prefix`: filename prefix; defaults to `keyframes_`.
- `frame_id_dir`: absolute directory to use in the CSV frame IDs; defaults to `output_dir`.
- `csv_path`: output CSV path; defaults to `/root/counting_results.csv`.

For the supplied Mario inputs, execute:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

Only treat the task as complete if stdout contains `"ok": true`, `codec_keyframes` equals `frames`, and `validation.ok` is true. The required final CSV header is exactly:

```text
frame_id,coins,enemies,turtles
```

For a video with `N` codec keyframes, final outputs must be exactly `/root/keyframes_001.png` through `/root/keyframes_NNN.png` and exactly `N` ordered CSV records pointing to those existing files. Rerun the complete entrypoint after any extraction failure; never retain an old CSV alongside a partial new image set.

## Failure behavior

The script exits nonzero and emits `{"ok":false,"error":"..."}` for malformed JSON, missing inputs or executables, unavailable OpenCV/NumPy, absent codec keyframes, failed individual extraction, an extraction/metadata count mismatch, non-grayscale saved images, incompatible templates, invalid output paths, or CSV validation failure. Fix the reported prerequisite and rerun the whole entrypoint.
