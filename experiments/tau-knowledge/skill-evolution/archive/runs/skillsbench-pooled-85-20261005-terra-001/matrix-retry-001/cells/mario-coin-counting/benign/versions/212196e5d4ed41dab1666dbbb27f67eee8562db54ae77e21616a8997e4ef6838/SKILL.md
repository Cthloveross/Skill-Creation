---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe of a video in presentation order, save consecutive grayscale PNGs, count supplied template objects per frame, and produce a one-to-one ordered CSV. Use for video tasks requiring keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe extraction and template counting

Use this Skill when requested key frames mean codec keyframes, not periodic frame samples. It requires only Python's standard library and the supplied FFmpeg/ffprobe executables; it has no network, OpenCV, NumPy, Pillow, or model dependency.

## Method

1. Read `frame=key_frame` metadata with ffprobe. The positions of `1` values are the required decoded-frame positions and establish the expected count.
2. Extract each reported codec-keyframe position separately into a temporary directory. This deliberately avoids a multi-image FFmpeg operation being partially written or affected by frame-rate synchronization. Each extraction decodes the source from its start, selects exactly that presentation-order decoded frame, and writes one `keyframes_%03d.png`.
3. FFmpeg writes every selected frame with `format=gray`, `-pix_fmt gray`, and the PNG encoder. The script inspects PNG IHDR color type and accepts only native grayscale types 0 or 4.
4. Decode each final frame and supplied object template through the same 8-bit grayscale FFmpeg pipeline. Match templates using high-contrast anchor screening, full-patch mean-absolute-difference confirmation, and spatial non-maximum suppression. Matching parameters are derived from each supplied template's contrast rather than hardcoding a single correlation threshold.
5. Publish all staged PNGs only after all required codec keyframes have been written and validated. Then create the CSV from the actual published frame list, not from a predicted count.
6. Reopen and validate the final CSV, PNGs, ordering, frame IDs, and integer count fields.

Object counts are per keyframe. Do not deduplicate a sprite across different keyframes because the requested CSV has one count for each selected image.

## Runtime interface

Run `scripts/analyze_mario.py` once. It reads exactly one JSON object from stdin and writes exactly one JSON object to stdout.

Required input fields:

- `video_path`: readable input video path.
- `templates`: object with exactly `coins`, `enemies`, and `turtles` keys and readable image paths as values.

Optional fields:

- `output_dir`: numbered-frame destination; default `/root`.
- `keyframe_prefix`: filename prefix; default `keyframes_`.
- `frame_id_dir`: directory represented by CSV frame IDs; default `output_dir`.
- `csv_path`: CSV destination; default `/root/counting_results.csv`.

Example for the supplied task:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

On success, stdout includes `ok: true`, the metadata keyframe count, number of published frames, output paths, matching calibration, and validation summary. On failure it emits `{"ok":false,"error":"..."}` and exits nonzero. A nonzero exit or `ok:false` is not a completed delivery.

## Required delivery checks

The entrypoint deletes stale numbered outputs and an old CSV before processing. It refuses to write a CSV unless all checks succeed:

- exactly one final PNG exists for every ffprobe codec keyframe;
- final PNG names are consecutive beginning with `keyframes_001.png`;
- every final PNG is readable and native grayscale;
- CSV header is exactly `frame_id,coins,enemies,turtles`;
- there is exactly one timeline-ordered data row per published frame;
- each CSV frame ID names the corresponding existing output image; and
- all three count fields are non-negative integers.
