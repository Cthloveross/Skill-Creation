#!/usr/bin/env python3
"""End-to-end: transcribe, align, write and validate the chapter index JSON.

stdin JSON config:
{
  "video": "/root/tutorial_video.mp4",
  "output": "/root/tutorial_index.json",
  "video_info": {"title": "...", "duration_seconds": 1382},
  "chapters": ["title1", "title2", ...],      # verbatim, in order
  "transcript_cache": "/root/transcript.json", # optional
  "model": "small",                             # optional
  "lookahead": 1,                               # optional
  "pos_weight": 0.15                            # optional
}

stdout JSON report:
{"status":..., "output_path":..., "backend":..., "chapters":[...],
 "validation":{"ok":bool,"errors":[...]}, "warnings":[...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import align as align_mod  # noqa: E402
import transcribe as transcribe_mod  # noqa: E402
import validate as validate_mod  # noqa: E402


def run(cfg):
    video = cfg["video"]
    output = cfg["output"]
    video_info = cfg["video_info"]
    chapters = cfg["chapters"]
    duration = float(video_info["duration_seconds"])
    model = cfg.get("model", "small")
    cache = cfg.get("transcript_cache", "/root/transcript.json")

    warnings = []

    tr = transcribe_mod.run({"video": video, "model": model, "out": cache,
                             "allow_install": cfg.get("allow_install", True)})
    segments = tr.get("segments", [])
    backend = tr.get("backend")
    if not segments:
        warnings.append("empty transcript")

    aligned = align_mod.run({"transcript": segments, "chapters": chapters,
                             "duration": duration,
                             "lookahead": int(cfg.get("lookahead", 1)),
                             "pos_weight": float(cfg.get("pos_weight", 0.15))})
    warnings += aligned.get("warnings", [])

    doc = {
        "video_info": {
            "title": video_info["title"],
            "duration_seconds": video_info["duration_seconds"],
        },
        "chapters": aligned["chapters"],
    }
    with open(output, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    val = validate_mod.run({"output_path": output, "chapters": chapters,
                            "duration": duration,
                            "title": video_info["title"]})

    status = "ok" if val["ok"] else "validation_failed"
    return {"status": status, "output_path": output, "backend": backend,
            "chapters": aligned["chapters"], "validation": val,
            "warnings": warnings}


if __name__ == "__main__":
    cfg = json.load(sys.stdin)
    print(json.dumps(run(cfg)))
