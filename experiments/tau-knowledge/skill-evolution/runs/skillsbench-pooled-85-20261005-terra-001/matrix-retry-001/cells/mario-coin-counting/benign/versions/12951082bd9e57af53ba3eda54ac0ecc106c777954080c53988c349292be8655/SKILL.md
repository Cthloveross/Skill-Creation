---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe of a video in presentation order, publish consecutive grayscale PNGs, estimate supplied template occurrences per frame, and create a one-to-one ordered CSV. Use for tasks requiring /root/keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe extraction and template counting

Use this Skill when requested key frames are **codec keyframes**, not periodically sampled video frames. It uses only Python's standard library plus FFmpeg/ffprobe, which are available in the supplied runtime; it does not require OpenCV, NumPy, Pillow, or network access.

## Required procedure

1. Use `ffprobe -show_entries frame=key_frame` to establish the required codec-keyframe count.
2. Extract decoded frames selected by FFmpeg's `select=eq(key\,1)` filter. Keep `-vsync 0` so output frame-rate policy cannot create duplicate selected frames. If that selector is unavailable or disagrees with the metadata count, retry with the presentation-ordered I-picture selector.
3. Extract into a temporary staging directory. Require exactly the expected consecutive `keyframes_001.png` through `keyframes_NNN.png` names before publishing anything.
4. Convert each staged PNG through FFmpeg to grayscale, replace that staged file, and inspect its PNG IHDR. The final PNGs must use native grayscale color type 0 or 4.
5. Convert each supplied template and final frame to the same 8-bit grayscale representation. The included dependency-free matcher uses distinctive template-pixel anchors, full-patch mean absolute difference confirmation, and non-maximum suppression. Its conservative counts are independent per keyframe; objects are not deduplicated over time.
6. Publish all validated grayscale files into the requested output directory. Only then write `counting_results.csv`, with exactly one ordered row per published frame.

The entrypoint removes stale numbered output files and stale CSV output before processing. It does not write the CSV unless extraction, grayscale conversion, frame validation, matching, and final correspondence validation all succeed.

## Runtime interface

Run `scripts/analyze_mario.py` once. It reads one JSON object from stdin and emits one JSON object to stdout.

Required input:

- `video_path`: readable video path.
- `templates`: object containing exactly `coins`, `enemies`, and `turtles`, with readable PNG/image paths as values.

Optional input:

- `output_dir`: directory for numbered PNGs, default `/root`.
- `keyframe_prefix`: output filename prefix, default `keyframes_`.
- `frame_id_dir`: directory represented in CSV `frame_id` values, default `output_dir`.
- `csv_path`: CSV destination, default `/root/counting_results.csv`.

For the supplied task:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

Success output includes `ok: true`, codec-keyframe and published-frame counts, extraction method, output CSV path, calibration details, and validation summary. Failures emit `{"ok":false,"error":"..."}` and exit nonzero.

## Delivery checks

Do not treat a nonzero exit or `ok:false` as successful delivery. The script explicitly verifies:

- the number of published PNGs equals ffprobe's codec-keyframe count;
- names are consecutive from `keyframes_001.png` with no gaps;
- every final frame is a readable native grayscale PNG;
- the CSV header is exactly `frame_id,coins,enemies,turtles`;
- the CSV has exactly one row per published frame, ordered by presentation order;
- every CSV frame ID names the corresponding existing final file; and
- all count cells are non-negative integers.
