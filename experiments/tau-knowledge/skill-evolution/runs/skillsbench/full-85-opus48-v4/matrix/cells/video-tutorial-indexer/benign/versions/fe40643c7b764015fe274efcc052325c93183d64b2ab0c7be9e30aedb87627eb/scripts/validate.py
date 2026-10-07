#!/usr/bin/env python3
"""Validate a chapter index JSON against the required structural invariants.

stdin JSON: {"output_path": path, "chapters": [expected titles...],
             "duration": float, "title": optional expected video title}
stdout JSON: {"ok": bool, "errors": [str, ...]}
"""
import json
import sys


def validate(doc, expected_titles, duration, expected_title=None):
    errors = []
    if not isinstance(doc, dict):
        return ["root is not an object"]
    vi = doc.get("video_info")
    if not isinstance(vi, dict):
        errors.append("missing video_info object")
    else:
        if "title" not in vi or not isinstance(vi.get("title"), str):
            errors.append("video_info.title missing or not a string")
        elif expected_title is not None and vi.get("title") != expected_title:
            errors.append("video_info.title does not match expected title")
        if not isinstance(vi.get("duration_seconds"), (int, float)):
            errors.append("video_info.duration_seconds missing or not numeric")

    chapters = doc.get("chapters")
    if not isinstance(chapters, list):
        return errors + ["chapters missing or not a list"]
    if len(chapters) != len(expected_titles):
        errors.append(
            "chapter count %d != expected %d" % (len(chapters), len(expected_titles)))

    prev = None
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            errors.append("chapter %d not an object" % i)
            continue
        t = ch.get("time")
        title = ch.get("title")
        if not isinstance(t, (int, float)) or isinstance(t, bool):
            errors.append("chapter %d time not numeric" % i)
        else:
            if t < 0 or t > duration:
                errors.append("chapter %d time %s out of [0,%s]" % (i, t, duration))
            if i == 0 and t != 0:
                errors.append("first chapter time must be 0, got %s" % t)
            if prev is not None and not (t > prev):
                errors.append(
                    "chapter %d time %s not strictly > previous %s" % (i, t, prev))
            prev = t
        if i < len(expected_titles):
            if title != expected_titles[i]:
                errors.append(
                    "chapter %d title mismatch: got %r expected %r"
                    % (i, title, expected_titles[i]))
    return errors


def run(cfg):
    with open(cfg["output_path"]) as f:
        doc = json.load(f)
    errors = validate(doc, cfg["chapters"], float(cfg["duration"]),
                      cfg.get("title"))
    return {"ok": len(errors) == 0, "errors": errors}


if __name__ == "__main__":
    cfg = json.load(sys.stdin)
    print(json.dumps(run(cfg)))
