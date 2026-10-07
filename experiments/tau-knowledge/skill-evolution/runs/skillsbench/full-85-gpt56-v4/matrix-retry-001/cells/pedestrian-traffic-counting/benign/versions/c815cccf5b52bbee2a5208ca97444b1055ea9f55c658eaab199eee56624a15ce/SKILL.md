---
name: pedestrian-video-count-xlsx
description: Count unique on-foot pedestrians in one or more fixed-camera video files and produce a strict two-column Excel workbook. Use for surveillance-video pedestrian-counting tasks where repeated appearances across frames must be deduplicated and cyclists/vehicle occupants excluded.
---

# Unique pedestrian counts from video

This Skill creates a strict Excel result after a temporal visual analysis. It deliberately treats a per-frame person detector as evidence rather than as a count: each physical person must be entered once in a tracklet ledger and counted once.

## Inputs and output

- Input: a directory containing video files (`.mp4`, `.avi`, `.mov`, `.mkv`, `.mpeg`, or `.webm`).
- Output: an `.xlsx` workbook at the requested path, with exactly one sheet and exactly `filename`, `number` as the first-row headers.
- `scripts/make_workbook.py` receives JSON on stdin:
  ```json
  {"output": "/path/count.xlsx", "rows": [{"filename": "clip.mp4", "number": 3}]}
  ```
  It emits JSON containing the normalized sorted rows and output path on stdout.

## Procedure

1. Locate only video input files in the requested directory. Exclude the requested output workbook and any analysis artifacts. Sort filenames lexicographically.
2. For each video, inspect its duration/FPS and create review frames with `scripts/video_review.py`. It emits metadata and creates timestamped contact sheets. Start with a broad evenly spaced review, then extract denser frames around each apparent arrival, departure, occlusion, crowd, bicycle, or vehicle interaction.
   ```bash
   python /app/environment/skills/current/scripts/video_review.py \
     --video /app/video/clip.mp4 --out-dir /tmp/clip-review --interval 1.0
   ```
   If the video is short or subjects move quickly, reduce `--interval` (for example, 0.25–0.5 seconds). Use `--start` and `--end` for a focused interval. The script needs OpenCV; if unavailable, use `ffprobe`/`ffmpeg` to make equivalent timestamped frames and continue the same ledger process.
3. Maintain a per-video ledger while reviewing chronological frames. Give each distinct on-foot person a temporary ID and record first/last timestamp, path/entry side, clothing or silhouette cues, and whether they are walking. Do **not** increment a count for every sampled frame.
4. Count people travelling on foot (walking, running, jogging, or standing). Exclude people riding bicycles/motorcycles and people inside vehicles. Count a person walking a bicycle. A partially visible entrant counts if there is enough evidence that it is a distinct on-foot person.
5. Resolve apparent new IDs after short missed intervals by comparing time gap, predicted direction/location, size, and appearance. Do not merge two simultaneous similar-looking people based on clothing alone. If a subject exits and later returns, count the same physical person only once when identity is supportable; otherwise apply a consistent conservative identity decision and document it in the ledger.
6. Review at least one alternate reasonable sampling interval around uncertain scenes. Reconcile tracklet fragments before finalizing each integer. Do not infer a count merely from the number of person detections.
7. Generate the requested workbook using `make_workbook.py` with the final ledger totals. Do not add a ledger, notes, blank rows, summaries, formatting-only sheets, or extra columns to the workbook.
   ```bash
   printf '%s' '{"output":"/app/video/count.xlsx","rows":[...]}' | \
     python /app/environment/skills/current/scripts/make_workbook.py
   ```
8. Validate the file structurally:
   ```bash
   python /app/environment/skills/current/scripts/validate_workbook.py \
     --workbook /app/video/count.xlsx --filenames clip1.mp4 clip2.mp4
   ```
   This checks sheet count/name, exact headers, exact row set/order, no populated extra cells, and integer nonnegative counts. It does not validate visual judgments.

## Assumptions and failure handling

The count requires readable temporal visual evidence. If a video cannot be opened, is corrupt, or has no decodable frames, do not silently write a fabricated zero; report the file and decoding failure to the task executor. If frames are too sparse to identify distinct people, increase review density or use an available detector/tracker only as a review aid, then visually verify activity and identity. The final worksheet must contain one row for every successfully required input video and native integer counts.
