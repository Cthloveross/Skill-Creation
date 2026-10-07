#!/usr/bin/env python3
"""Shared structural validation for tutorial chapter index JSON."""
import math


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_index(index, expected_titles, duration_seconds, expected_video_title=None):
    errors = []
    if not isinstance(index, dict):
        return ["Top-level JSON value must be an object"]
    info = index.get("video_info")
    if not isinstance(info, dict):
        errors.append("video_info must be an object")
    else:
        if not isinstance(info.get("title"), str):
            errors.append("video_info.title must be a string")
        elif expected_video_title is not None and info["title"] != expected_video_title:
            errors.append("video_info.title does not equal expected_video_title")
        if not is_number(info.get("duration_seconds")):
            errors.append("video_info.duration_seconds must be a finite number")
        elif duration_seconds is not None and info["duration_seconds"] != duration_seconds:
            errors.append("video_info.duration_seconds does not equal duration_seconds")
    if not isinstance(expected_titles, list) or not all(isinstance(x, str) for x in expected_titles):
        errors.append("expected_titles must be an array of strings")
        return errors
    chapters = index.get("chapters")
    if not isinstance(chapters, list):
        errors.append("chapters must be an array")
        return errors
    if len(chapters) != len(expected_titles):
        errors.append(f"chapter count {len(chapters)} does not equal expected count {len(expected_titles)}")
    previous = None
    for i, chapter in enumerate(chapters):
        label = f"chapters[{i}]"
        if not isinstance(chapter, dict):
            errors.append(f"{label} must be an object")
            continue
        if i < len(expected_titles) and chapter.get("title") != expected_titles[i]:
            errors.append(f"{label}.title does not exactly match expected title")
        time = chapter.get("time")
        if not is_number(time):
            errors.append(f"{label}.time must be a finite number")
            continue
        if duration_seconds is not None and not (0 <= time <= duration_seconds):
            errors.append(f"{label}.time is outside the permitted duration range")
        if i == 0 and time != 0:
            errors.append("First chapter time must be exactly 0")
        if previous is not None and time <= previous:
            errors.append(f"{label}.time is not strictly greater than the preceding time")
        previous = time
    return errors
