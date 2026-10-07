#!/usr/bin/env python3
"""Extract tutorial audio. Reads JSON stdin, writes one JSON result to stdout.

Input: {"video_path": str, "audio_path": str}
Output success: {"ok": true, "audio_path": str, "command": [str, ...]}
Output failure: {"ok": false, "errors": [str]}
"""
import json
import os
import subprocess
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "errors": [f"Invalid input JSON: {exc}"]})
        return
    video = data.get("video_path")
    audio = data.get("audio_path")
    errors = []
    if not isinstance(video, str) or not video:
        errors.append("video_path must be a nonempty string")
    elif not os.path.isfile(video):
        errors.append(f"Video does not exist: {video}")
    if not isinstance(audio, str) or not audio:
        errors.append("audio_path must be a nonempty string")
    if errors:
        emit({"ok": False, "errors": errors})
        return
    parent = os.path.dirname(os.path.abspath(audio))
    if not os.path.isdir(parent):
        emit({"ok": False, "errors": [f"Output directory does not exist: {parent}"]})
        return
    command = [
        "ffmpeg", "-y", "-i", video, "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", audio,
    ]
    try:
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=False)
    except FileNotFoundError:
        emit({"ok": False, "errors": ["ffmpeg is not available on PATH"]})
        return
    if completed.returncode != 0 or not os.path.isfile(audio) or os.path.getsize(audio) == 0:
        message = completed.stderr.strip()[-2000:] or "ffmpeg did not create a nonempty audio file"
        emit({"ok": False, "errors": [message], "command": command})
        return
    emit({"ok": True, "audio_path": audio, "command": command})


if __name__ == "__main__":
    main()
