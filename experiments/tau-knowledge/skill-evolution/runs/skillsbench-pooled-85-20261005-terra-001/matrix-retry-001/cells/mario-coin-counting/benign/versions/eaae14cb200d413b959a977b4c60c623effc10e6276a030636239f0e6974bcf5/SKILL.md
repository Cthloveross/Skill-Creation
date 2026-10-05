---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNGs, count supplied object templates in each final frame, and write a matching CSV. Use for Super Mario-style tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this skill when requested frames are **codec keyframes**, not periodic samples. Counts are per saved keyframe; do not temporally deduplicate objects.

## Workflow

1. Use `ffprobe frame=key_frame` to determine the required codec-keyframe count and presentation-order decoded-frame indexes.
2. Extract all keyframes into a staging directory. The script first uses FFmpeg decoder option `-skip_frame nokey`, which outputs only codec keyframes. If that does not exactly match ffprobe metadata, it falls back to an FFmpeg `select` expression built from the ffprobe decoded-frame indexes. It never samples by FPS or duration.
3. Require the extracted staging filenames to be consecutive `keyframes_001.png`, `keyframes_002.png`, and so on, with exactly the metadata count.
4. Reopen each frame, overwrite it as a one-channel grayscale PNG, and confirm its PNG color type is grayscale.
5. Convert templates through the same grayscale pipeline. Detect local normalized-template-match peaks and apply template-scale non-maximum suppression; do not count all high-valued score-map pixels.
6. Publish all validated grayscale frames before atomically publishing the CSV. The CSV is generated only from the final frame list and has one ordered record for every file.

The entrypoint removes stale matching keyframes and a stale destination CSV before processing. Therefore a failed run cannot leave an old CSV that claims to describe a partial new extraction.

## Runtime interface

Run `scripts/analyze_mario.py` once. It receives one JSON object on stdin and emits one JSON object on stdout.

Required fields:

- `video_path`: readable source video path.
- `templates`: object with exactly `coins`, `enemies`, and `turtles`, each a readable image path.

Optional fields:

- `output_dir`: directory for keyframes; defaults to `/root`.
- `keyframe_prefix`: output filename prefix; defaults to `keyframes_`.
- `frame_id_dir`: absolute directory represented in CSV frame IDs; defaults to `output_dir`.
- `csv_path`: output CSV path; defaults to `/root/counting_results.csv`.

For the supplied task, invoke it as follows:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

Successful output has the schema:

```json
{"ok":true,"codec_keyframes":8,"frames":8,"csv_path":"/root/counting_results.csv","extraction_method":"skip_frame_nokey","validation":{"ok":true,"frames_checked":8,"csv_rows_checked":8}}
```

The numbers above illustrate the schema only. A valid run always has equal `codec_keyframes` and `frames`. For `N` frames, the files are `keyframes_001.png` through `keyframes_NNN.png`; the CSV header is exactly:

```text
frame_id,coins,enemies,turtles
```

## Failure handling and validation

The runtime needs Python, NumPy, OpenCV, FFmpeg, and ffprobe. Missing inputs/dependencies, failed extraction, a count mismatch, non-grayscale PNG output, invalid output numbering, or invalid CSV rows cause `{"ok":false,"error":"..."}` and a nonzero exit. Fix that condition and rerun the complete entrypoint; do not create CSV rows for files that were not successfully written.
