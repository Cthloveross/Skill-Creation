#!/usr/bin/env python3
"""Extract tutorial audio and create a Whisper JSON transcript.

JSON stdin:
{
  "video_path": "/path/video.mp4",
  "audio_path": "/optional/output.wav",
  "transcript_path": "/required/output.json",
  "model": "small",
  "language": "en",
  "asr_command": ["optional", "argv", "using", "{audio}", "{outdir}", "{model}"]
}

Without asr_command, requires the OpenAI Whisper-compatible `whisper` CLI. stdout is
JSON with resulting paths, ffprobe duration, and transcript segment count. External
commands are invoked without a shell.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def fail(message):
    print(json.dumps({"ok": False, "error": message}), file=sys.stdout)
    raise SystemExit(2)


def require_string(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        fail(f"{key} must be a nonempty string")
    return value


def run(argv):
    try:
        return subprocess.run(argv, check=True, text=True, capture_output=True)
    except FileNotFoundError:
        fail(f"required executable not found: {argv[0]}")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        fail(f"command failed ({argv[0]}): {detail[-1500:]}")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid input JSON: {exc}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    video = Path(require_string(data, "video_path"))
    transcript = Path(require_string(data, "transcript_path"))
    if not video.is_file():
        fail(f"video_path does not exist or is not a file: {video}")
    audio = Path(data.get("audio_path") or str(transcript.with_suffix(".wav")))
    model = data.get("model", "small")
    language = data.get("language", "en")
    if not isinstance(model, str) or not model or not isinstance(language, str) or not language:
        fail("model and language must be nonempty strings")

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            fail(f"{tool} is required but not available on PATH")
    audio.parent.mkdir(parents=True, exist_ok=True)
    transcript.parent.mkdir(parents=True, exist_ok=True)

    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", str(video)])
    try:
        measured_duration = float(json.loads(probe.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        fail("ffprobe did not return a numeric media duration")

    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(audio)])

    with tempfile.TemporaryDirectory(prefix="chapter_asr_") as tmp:
        outdir = Path(tmp)
        custom = data.get("asr_command")
        if custom is None:
            if shutil.which("whisper") is None:
                fail("whisper CLI is required but not available on PATH; install/configure an ASR CLI or supply asr_command")
            argv = ["whisper", str(audio), "--model", model, "--language", language,
                    "--output_format", "json", "--output_dir", str(outdir)]
        else:
            if not isinstance(custom, list) or not custom or not all(isinstance(x, str) for x in custom):
                fail("asr_command must be a nonempty JSON array of strings")
            argv = [x.format(audio=str(audio), outdir=str(outdir), model=model, language=language)
                    for x in custom]
        run(argv)
        candidates = list(outdir.glob("*.json"))
        if len(candidates) != 1:
            fail("ASR did not produce exactly one JSON transcript in its output directory")
        try:
            parsed = json.loads(candidates[0].read_text(encoding="utf-8"))
            segments = parsed["segments"]
            if not isinstance(segments, list):
                raise ValueError
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            fail("ASR JSON lacks a usable segments array")
        shutil.copyfile(candidates[0], transcript)

    print(json.dumps({"ok": True, "audio_path": str(audio), "transcript_path": str(transcript),
                      "measured_duration_seconds": measured_duration, "segment_count": len(segments)}))


if __name__ == "__main__":
    main()
