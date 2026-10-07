---
name: pedestrian-video-counting
version: 1.0.0
description: Count unique on-foot pedestrians in one or more fixed-camera videos with YOLO detection, temporal tracking, conservative tracklet repair, cyclist/vehicle-occupant exclusion, and an exact Excel results workbook. Use for surveillance-video pedestrian counting tasks requiring one row per source video.
---

# Pedestrian video counting

Use this Skill when each physical person must be counted once across a video rather than once per frame. A pedestrian is a person travelling on foot (including standing, walking, jogging, or running). Do not count a cyclist who remains riding, or a person inside a vehicle. A rider who dismounts and is subsequently on foot does count.

The packaged counter runs a COCO YOLO detector with ByteTrack across every frame, records a tracklet ledger, rejects person tracks consistently associated with bicycles or vehicle interiors, and conservatively joins short, geometrically compatible tracking fragments. It writes the required workbook with exactly one `results` sheet and exactly `filename` and `number` columns.

## Prerequisites

The execution environment needs Python 3, network access or an already cached YOLO weight, and these packages:

- `ultralytics` (downloads `yolov8s.pt` by default on first use)
- `opencv-python`
- `openpyxl`

Install unavailable packages in the execution environment before running. The first model download is normal; do not substitute per-frame detection totals for tracking.

## Run

Run the script from a directory containing this Skill package. It receives one JSON object on stdin and emits a JSON report on stdout.

```bash
python scripts/count_pedestrians.py <<'JSON'
{
  "video_dir": "/app/video",
  "output_path": "/app/video/count.xlsx",
  "diagnostics_path": "/app/video/pedestrian_diagnostics.json",
  "model": "yolov8s.pt",
  "confidence": 0.20,
  "imgsz": 640
}
JSON
```

Input fields:

- `video_dir` (required): directory recursively searched for supported video files.
- `output_path` (required): `.xlsx` destination. It must not be inside a video filename set.
- `diagnostics_path` (optional): JSON ledger of raw tracks, classification evidence, repaired groups, and preliminary counts. It is useful for audit and is not included in the workbook.
- `model` (optional): an Ultralytics YOLO detection weight/path; default `yolov8s.pt`.
- `confidence` (optional): detector confidence in `(0,1)`, default `0.20`.
- `imgsz` (optional): inference image size, default `640`.
- `review_overrides` (optional): object mapping an exact source filename to a manually audited nonnegative integer. Overrides are deliberately explicit and replace only that video's computed count.

The stdout report contains `videos`, each with the source name, computed count, and whether an override was used, plus output paths. It raises an error for missing input directories, duplicate basenames in recursive input, invalid options, unavailable videos, or invalid overrides rather than silently creating an ambiguous result.

## Recommended audit

For crowded scenes, tiny subjects, unusual viewpoints, long occlusions, or possible rider/dismount events, review the source video and the diagnostics ledger before delivery. Track IDs are intermediate hypotheses: inspect tracklets whose status is `candidate` but have bicycle or vehicle evidence, and short tracklets near an entry/exit area. Use `review_overrides` only for counts established from a temporal review of the actual video, never to compensate by summing frame detections.

If visual review needs sparse frames, create a contact sheet:

```bash
python scripts/extract_review_frames.py <<'JSON'
{"video_path":"/app/video/example.mp4","output_path":"/app/video/review.jpg","interval_seconds":1.0}
JSON
```

A contact sheet supports scene familiarization but cannot by itself establish identity across widely separated frames; inspect the video chronology for final ambiguous cases.

## Validate the delivery file

After counting (and after any override run), validate workbook structure and ordering:

```bash
python scripts/validate_workbook.py <<'JSON'
{"video_dir":"/app/video","workbook_path":"/app/video/count.xlsx"}
JSON
```

Validation confirms one sheet named `results`, the exact two headers, one deterministically filename-sorted row per discovered video, no blank/extra rows or columns, and nonnegative integer counts. The workbook intentionally contains no title, formatting metadata rows, summaries, or diagnostics.
