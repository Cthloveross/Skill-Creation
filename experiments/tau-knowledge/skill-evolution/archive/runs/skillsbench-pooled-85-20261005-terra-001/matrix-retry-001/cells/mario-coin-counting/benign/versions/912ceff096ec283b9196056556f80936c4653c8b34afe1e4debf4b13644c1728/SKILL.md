---
name: mario-keyframe-template-counting
description: Extract every codec keyframe from a video in presentation order, overwrite the PNGs as grayscale, template-match supplied game sprites per frame, and generate a strict frame-path CSV. Use for video object-counting tasks requiring /root/keyframes_%03d.png and counting_results.csv.
---

# Codec-keyframe template counting

This skill creates one numbered PNG for **every codec keyframe** and exactly one CSV row for each final PNG. It accepts a video and a mapping from count-column names to template images.

## Required procedure

1. Confirm that the video and every template are readable, and that `ffmpeg`, `ffprobe`, OpenCV (`cv2`), and NumPy are available.
2. Count codec keyframes with `ffprobe` using `frame=key_frame` on the complete video stream.
3. Remove old PNGs matching the selected prefix and any previous destination CSV. Extract frames with FFmpeg's `select=eq(key\,1)` video filter and `-vsync 0`. The filter selects AVFrames marked as codec keyframes while decoding the normal presentation sequence; it avoids the unreliable behavior of decoding only key packets with `-skip_frame nokey`.
4. Require the generated files to be consecutive (`keyframes_001.png`, `keyframes_002.png`, ...) and to have exactly the same count as ffprobe metadata before any CSV is written.
5. Reopen every extracted PNG, convert it to one grayscale channel, overwrite the same file, then reopen it again to ensure the saved artifact is grayscale. Convert templates through the same grayscale pipeline in memory.
6. Match each template on each grayscale frame. Scores are normalized correlation responses; candidate detections are local maxima and score-ordered non-maximum suppression removes response clusters. The score threshold is estimated separately from each response map using Otsu separation and a high background quantile, rather than using a universal cutoff.
7. Only after final frames have been generated, write the CSV in numeric timeline order and reopen all outputs to validate columns, IDs, integer counts, grayscale encoding, and one row per actual file.

The requested result is a count per keyframe, not a deduplicated count over the whole video. Templates are assumed to be crops rendered at the same scale as their targets.

## Runtime interface

Run `scripts/analyze_mario.py` with one JSON object on standard input. It writes one JSON object to standard output.

Required fields:

- `video_path`: source video path.
- `templates`: nonempty object mapping CSV count column names to template image paths.

Optional fields:

- `output_dir`: output-frame directory; default `/root`.
- `keyframe_prefix`: output prefix; default `keyframes_`.
- `frame_id_dir`: absolute directory represented by CSV IDs; defaults to `output_dir`.
- `csv_path`: output CSV location; default `/root/counting_results.csv`.

For this task, the executor must run the complete entrypoint once after the supplied files are present:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

On success, the CSV header for that invocation is exactly:

```text
frame_id,coins,enemies,turtles
```

Its IDs are `/root/keyframes_001.png` through the final consecutive index. Deliver the artifacts only when stdout reports `"ok": true` and `"validation":{"ok":true,...}`.

## Errors and recovery

The script emits a JSON error and exits nonzero for absent inputs or programs, invalid JSON, zero keyframes, nonconsecutive or metadata-mismatched extraction, unreadable images, template/frame dimension incompatibility, unwritable outputs, or output validation failure. It never substitutes sampled frames for codec keyframes. A failed run removes its owned old CSV before extraction so a stale CSV cannot describe a newly incomplete keyframe set; correct the reported issue and rerun the whole entrypoint.
