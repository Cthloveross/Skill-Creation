---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe of a video into consecutive grayscale PNG files, count supplied object templates per frame, and produce a one-to-one CSV. Use for Super Mario-style tasks requiring /root/keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

Use this Skill when the requested frames are **codec keyframes**, not periodic samples. Counts are per saved frame and must not be temporally deduplicated.

## Method

1. Use `ffprobe` to count `frame=key_frame` records. This is the authoritative expected frame count.
2. Use FFmpeg's decoder input option `-skip_frame nokey` to extract every codec keyframe in presentation order. This avoids fragile frame-number `select` expressions and avoids FPS/timestamp sampling.
3. Extract into a staging directory and require exactly the metadata count under consecutive names `keyframes_001.png` through `keyframes_NNN.png`.
4. Reopen each extracted PNG and overwrite it as a one-channel grayscale PNG. Convert templates through the same grayscale pipeline before matching.
5. Match each template using local score peaks and non-maximum suppression; do not count every score-map pixel over a threshold. The script derives a conservative threshold from the supplied video/template score distribution and reports its calibration.
6. Publish all final frame files, then generate the CSV from that final ordered file list. The CSV must have exactly this header and exactly one data row per published frame:

```text
frame_id,coins,enemies,turtles
```

The entrypoint removes stale numbered files and the old CSV before a new run. It writes no CSV until it has verified the complete final keyframe set.

## Runtime interface

Run `scripts/analyze_mario.py` once with a JSON object on stdin. It emits one JSON object on stdout.

Required fields:

- `video_path`: readable input video path.
- `templates`: object with exactly `coins`, `enemies`, and `turtles`, each a readable image path.

Optional fields:

- `output_dir`: output directory, default `/root`.
- `keyframe_prefix`: output filename prefix, default `keyframes_`.
- `frame_id_dir`: directory represented in CSV `frame_id` values, default `output_dir`.
- `csv_path`: CSV destination, default `/root/counting_results.csv`.

For this task invoke it as follows:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful response has this shape:

```json
{"ok":true,"codec_keyframes":8,"frames":8,"csv_path":"/root/counting_results.csv","extraction_method":"ffmpeg_skip_frame_nokey","calibration":{},"validation":{"ok":true,"frames_checked":8,"csv_rows_checked":8}}
```

The numeric values are only illustrative. On success, `codec_keyframes` and `frames` are equal and are computed from the current video.

## Completion checks

Treat a nonzero exit or an `ok:false` response as failure; do not deliver partial files or precomputed CSV rows. Before success, the script checks:

- FFprobe keyframe count equals extracted and published frame count;
- output names are consecutive from `keyframes_001.png`;
- each final PNG is readable and natively grayscale;
- CSV header, row count, ordered absolute frame IDs, and non-negative integer fields are exact.

The runtime requires Python 3, NumPy, OpenCV, FFmpeg, and ffprobe. If an input, executable, extraction, image, or validation check is unavailable, stdout contains `{"ok":false,"error":"..."}` and the process exits nonzero.
