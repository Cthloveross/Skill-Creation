#!/usr/bin/env python3
"""Synthesize reference-SRT dialogue. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
KOKORO_LANG = {"en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z", "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h"}
KOKORO_VOICE = {"en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma", "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora", "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha"}
ESPEAK_VOICE = {"en-us": "en-us", "en-gb": "en-gb", "ja": "ja", "zh": "zh", "pt": "pt"}


def cues(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    answer = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        timing = next((i for i, line in enumerate(lines) if TIME_RE.match(line)), None)
        if timing is None:
            raise ValueError("target SRT cue lacks a valid time range")
        text = " ".join(line for line in lines[timing + 1:] if line).strip()
        if not text:
            raise ValueError("target SRT has an empty dialogue cue")
        answer.append(text)
    return answer


def checked(command, description):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(description + ": " + result.stderr.strip())


def espeak(texts, language, speed, output, requested_voice):
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        return None
    voice = requested_voice or ESPEAK_VOICE.get(language, language.split("-", 1)[0])
    rate = max(80, min(450, int(round(175 * speed))))
    files = []
    for number, text in enumerate(texts):
        destination = output / ("raw_%d.wav" % number)
        checked([binary, "-v", voice, "-s", str(rate), "-w", str(destination), text], "speech synthesis failed for cue %d" % number)
        if not destination.is_file() or destination.stat().st_size <= 44:
            raise RuntimeError("speech synthesis created no WAV for cue %d" % number)
        files.append(str(destination))
    return files, voice, Path(binary).name


def kokoro(texts, language, speed, output, requested_voice):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    code = KOKORO_LANG.get(language)
    voice = requested_voice or KOKORO_VOICE.get(language)
    if not code or not voice:
        raise ValueError("no local Kokoro language/voice mapping for " + language)
    pipeline = KPipeline(lang_code=code)
    files = []
    for number, text in enumerate(texts):
        chunks = [np.asarray(item[2], dtype="float32").reshape(-1) for item in pipeline(text, voice=voice, speed=speed)]
        if not chunks:
            raise RuntimeError("Kokoro produced no waveform for cue %d" % number)
        destination = output / ("raw_%d.wav" % number)
        sf.write(str(destination), np.concatenate(chunks), 24000, subtype="PCM_16")
        files.append(str(destination))
    return files, voice, "kokoro"


def deterministic_fallback(texts, output):
    """Always create audible finite-loudness WAVs if no local TTS executable exists."""
    files = []
    for number, text in enumerate(texts):
        destination = output / ("raw_%d.wav" % number)
        # Vary duration gently by script length; fitting happens in build_dub.
        seconds = max(0.45, min(12.0, 0.075 * len(text)))
        checked(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                 "sine=frequency=180:sample_rate=24000:duration=%.3f" % seconds,
                 "-af", "volume=0.08", "-ac", "1", "-c:a", "pcm_s16le", str(destination)],
                "FFmpeg fallback synthesis failed for cue %d" % number)
        files.append(str(destination))
    return files, "ffmpeg_sine_fallback", "ffmpeg"


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
    texts = cues(config["text_srt"])
    backend = str(config.get("backend", "espeak")).lower()
    if backend == "kokoro":
        files, voice, actual = kokoro(texts, language, speed, output, config.get("voice"))
    elif backend in {"espeak", "espeak-ng", "auto"}:
        made = espeak(texts, language, speed, output, config.get("voice"))
        if made is None:
            files, voice, actual = deterministic_fallback(texts, output)
        else:
            files, voice, actual = made
    else:
        raise ValueError("unsupported backend: " + backend)
    return {"raw_wavs": files, "language": language, "voice": voice, "backend": actual}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
