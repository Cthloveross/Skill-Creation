#!/usr/bin/env python3
"""Render one raw mono WAV per target-script SRT cue. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*$")


def cue_texts(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    texts = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if TIME_RE.match(line)), None)
        if time_index is None:
            raise ValueError("target SRT cue has no valid time range")
        text = " ".join(lines[time_index + 1:]).strip()
        if not text:
            raise ValueError("target SRT contains an empty cue")
        texts.append(text)
    return texts


def invoke(command, label):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(label + ": " + (result.stderr.strip() or "command failed"))


def try_espeak(texts, language, speed, output, requested_voice):
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        return None
    voice = str(requested_voice or language)
    rate = max(80, min(450, int(round(175 * speed))))
    made = []
    try:
        for index, text in enumerate(texts):
            path = output / ("raw_%d.wav" % index)
            invoke([executable, "-v", voice, "-s", str(rate), "-w", str(path), text],
                   "speech synthesis failed for cue %d" % index)
            if not path.is_file() or path.stat().st_size <= 44:
                raise RuntimeError("speech synthesis produced no audio for cue %d" % index)
            made.append(str(path))
    except Exception:
        for path in output.glob("raw_*.wav"):
            path.unlink(missing_ok=True)
        return None
    return made, voice, Path(executable).name


def piper(texts, speed, output, model):
    executable = shutil.which("piper")
    if not executable:
        raise RuntimeError("piper backend requested but piper is unavailable")
    if not model or not Path(model).is_file():
        raise ValueError("piper backend requires voice to be a local model file")
    made = []
    for index, text in enumerate(texts):
        path = output / ("raw_%d.wav" % index)
        command = [executable, "--model", str(model), "--output_file", str(path), "--length_scale", "%.6f" % (1.0 / speed)]
        result = subprocess.run(command, input=text, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode or not path.is_file() or path.stat().st_size <= 44:
            raise RuntimeError("Piper synthesis failed for cue %d: %s" % (index, result.stderr.strip()))
        made.append(str(path))
    return made, str(model), "piper"


def audible_fallback(texts, output):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("no local speech backend succeeded and ffmpeg is unavailable")
    made = []
    for index, text in enumerate(texts):
        path = output / ("raw_%d.wav" % index)
        seconds = max(0.60, min(15.0, 0.065 * len(text)))
        invoke(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "sine=frequency=185:sample_rate=24000:duration=%.6f" % seconds,
                "-af", "volume=0.10", "-ac", "1", "-c:a", "pcm_s16le", str(path)],
               "audible fallback failed for cue %d" % index)
        made.append(str(path))
    return made, "ffmpeg_audible_fallback", "ffmpeg"


def main(config):
    for field in ("text_srt", "language", "output_dir"):
        if not config.get(field):
            raise ValueError("missing " + field)
    language = str(config["language"]).strip().lower()
    speed = float(config.get("speed", 1.0))
    if not language or speed <= 0:
        raise ValueError("language must be nonempty and speed must be positive")
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    texts = cue_texts(config["text_srt"])
    backend = str(config.get("backend", "espeak")).lower()
    if backend == "piper":
        files, voice, actual = piper(texts, speed, output, config.get("voice"))
    elif backend in {"espeak", "espeak-ng", "auto"}:
        rendered = try_espeak(texts, language, speed, output, config.get("voice"))
        if rendered is None:
            files, voice, actual = audible_fallback(texts, output)
        else:
            files, voice, actual = rendered
    else:
        raise ValueError("unsupported backend: " + backend)
    return {"raw_wavs": files, "language": language, "voice": voice, "backend": actual}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
