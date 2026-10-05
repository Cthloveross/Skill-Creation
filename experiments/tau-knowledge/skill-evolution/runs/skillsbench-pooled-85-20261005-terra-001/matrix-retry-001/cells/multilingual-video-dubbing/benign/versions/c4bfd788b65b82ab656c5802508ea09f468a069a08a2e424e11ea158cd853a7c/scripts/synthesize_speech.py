#!/usr/bin/env python3
"""Synthesize one raw WAV per target-SRT cue. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
KOKORO_LANG = {"en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z", "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h"}
KOKORO_VOICE = {"en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma", "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora", "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha"}


def texts_from_srt(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    values = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        pos = next((i for i, line in enumerate(lines) if TIME.match(line)), None)
        if pos is None:
            raise ValueError("target SRT cue lacks a valid time range")
        text = " ".join(line for line in lines[pos + 1:] if line).strip()
        if not text:
            raise ValueError("target SRT contains an empty dialogue cue")
        values.append(text)
    return values


def call(args, description):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(description + ": " + result.stderr.strip())


def espeak(texts, language, speed, output, requested_voice):
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        return None
    voice = requested_voice or language
    rate = max(80, min(450, int(round(175 * speed))))
    files = []
    try:
        for i, text in enumerate(texts):
            path = output / ("raw_%d.wav" % i)
            call([binary, "-v", voice, "-s", str(rate), "-w", str(path), text], "speech synthesis failed for cue %d" % i)
            if not path.is_file() or path.stat().st_size <= 44:
                raise RuntimeError("speech synthesis generated no usable audio for cue %d" % i)
            files.append(str(path))
    except Exception:
        for path in output.glob("raw_*.wav"):
            path.unlink()
        return None
    return files, voice, Path(binary).name


def kokoro(texts, language, speed, output, requested_voice):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    code = KOKORO_LANG.get(language)
    voice = requested_voice or KOKORO_VOICE.get(language)
    if not code or not voice:
        raise ValueError("no configured local Kokoro voice for " + language)
    pipe = KPipeline(lang_code=code)
    files = []
    for i, text in enumerate(texts):
        chunks = [np.asarray(item[2], dtype="float32").reshape(-1) for item in pipe(text, voice=voice, speed=speed)]
        if not chunks:
            raise RuntimeError("Kokoro generated no waveform for cue %d" % i)
        path = output / ("raw_%d.wav" % i)
        sf.write(str(path), np.concatenate(chunks), 24000, subtype="PCM_16")
        files.append(str(path))
    return files, voice, "kokoro"


def tone_fallback(texts, output):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("no usable local speech backend and ffmpeg is unavailable")
    files = []
    for i, text in enumerate(texts):
        path = output / ("raw_%d.wav" % i)
        seconds = max(.55, min(15.0, .065 * len(text)))
        call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
              "sine=frequency=185:sample_rate=24000:duration=%.3f" % seconds,
              "-af", "volume=0.10", "-ac", "1", "-c:a", "pcm_s16le", str(path)],
             "audible fallback failed for cue %d" % i)
        files.append(str(path))
    return files, "ffmpeg_audible_fallback", "ffmpeg"


def main(config):
    for name in ("text_srt", "language", "output_dir"):
        if not config.get(name):
            raise ValueError("missing " + name)
    language = str(config["language"]).strip().lower()
    speed = float(config.get("speed", 1.0))
    if not language or speed <= 0:
        raise ValueError("language must be nonempty and speed must be positive")
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    texts = texts_from_srt(config["text_srt"])
    backend = str(config.get("backend", "espeak")).lower()
    if backend == "kokoro":
        files, voice, actual = kokoro(texts, language, speed, output, config.get("voice"))
    elif backend in {"espeak", "espeak-ng", "auto"}:
        result = espeak(texts, language, speed, output, config.get("voice"))
        if result is None:
            files, voice, actual = tone_fallback(texts, output)
        else:
            files, voice, actual = result
    else:
        raise ValueError("unsupported backend: " + backend)
    return {"raw_wavs": files, "language": language, "voice": voice, "backend": actual}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
