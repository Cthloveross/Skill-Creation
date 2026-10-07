---
name: mario-codec-keyframe-template-counting
description: Extract every codec keyframe from a video into consecutively numbered grayscale PNG files, count supplied sprite templates per final frame, and generate a strict frame-aligned CSV. Use for the Super Mario task requiring /root/keyframes_%03d.png and /root/counting_results.csv.
---

# Codec-keyframe template counting

This skill creates one final grayscale PNG for every codec keyframe reported by `ffprobe`, in presentation order, and exactly one CSV record for every written PNG. Counts are per frame; they are not video-wide deduplicated totals.

## Method

1. Inspect the video with `ffprobe -show_entries frame=key_frame` and retain the zero-based presentation positions whose flag is `1`.
2. Extract precisely those decoded frame positions with FFmpeg's `select=eq(n\,...)` filter. Using positions derived from the same metadata used for validation avoids decoder skip modes that can omit keyframes. The script rejects extraction unless the resulting PNG count equals the metadata count.
3. Write extraction results to a staging directory, reopen every result, overwrite it as a one-channel grayscale PNG, and verify the rewritten image is grayscale.
4. Convert each supplied template with the same grayscale conversion. Match it against every final frame, retain local score maxima, calibrate a high score cutoff from the observed peak distribution, and apply template-scale non-maximum suppression. This counts object candidates, not every above-threshold response-map pixel.
5. Build the CSV only after the complete staged frame set exists. Validate the exact header, ordered absolute frame IDs, non-negative integer values, grayscale PNGs, and one-to-one frame/row correspondence before publishing all staged outputs.

The supplied templates are assumed to depict target sprites at the video render scale. Template matching is heuristic; inspect the returned calibration information if sprite variants or repetitive backgrounds require threshold adjustment.

## Runtime interface

Run `scripts/analyze_mario.py` with one JSON object on stdin. It emits one JSON object on stdout.

Required fields:

- `video_path`: readable input video path.
- `templates`: an object with exactly `coins`, `enemies`, and `turtles`, each mapped to a readable image path.

Optional fields:

- `output_dir`: directory for keyframe PNGs, default `/root`.
- `keyframe_prefix`: output file prefix, default `keyframes_`.
- `frame_id_dir`: absolute directory written into CSV frame IDs, default `output_dir`.
- `csv_path`: output CSV path, default `/root/counting_results.csv`.

For the supplied task, execute the entrypoint once after all public inputs are copied:

```bash
python3 scripts/analyze_mario.py <<'JSON'
{"video_path":"/root/super-mario.mp4","templates":{"coins":"/root/coin.png","enemies":"/root/enemy.png","turtles":"/root/turtle.png"},"output_dir":"/root","keyframe_prefix":"keyframes_","frame_id_dir":"/root","csv_path":"/root/counting_results.csv"}
JSON
```

A successful result has `"ok": true`; `codec_keyframes` and `frames` must be equal, and `validation.ok` must be true. The final CSV has exactly this header:

```text
frame_id,coins,enemies,turtles
```

Do not retain an earlier CSV after rerunning extraction. The script replaces all matching final keyframe names and the CSV together only after the new complete staged result validates.

## Failure behavior

The program emits `{"ok":false,"error":"..."}` and exits nonzero for malformed input, missing files or executables, unavailable OpenCV/NumPy, no codec keyframes, extraction/count mismatches, unreadable or non-grayscale images, incompatible templates, invalid output paths, or final validation failures. Correct the reported prerequisite and rerun the complete entrypoint; do not manually combine partial PNGs with an old CSV.
