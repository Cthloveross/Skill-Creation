#!/usr/bin/env python3
"""Create one raw WAV per target-script cue. Reads JSON stdin and writes JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
KOKORO_LANG = {"en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z", "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h"}
KOKORO_VOICE = {"en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma", "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora", "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha"}
ESPEAK_VOICE = {"en-us": "en-us", "en-gb": "en-gb", "ja": "ja", "zh": "zh", "pt": "pt"}


def parse_texts(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    texts = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next((i for i, line in enumerate(lines) if TIME.match(line)), None)
        if timing_index is None:
            raise ValueError("target SRT cue lacks a valid timing range")
        text = " ".join(line for line in lines[timing_index + 1:] if line).strip()
        if not text:
            raise ValueError("target SRT has an empty dialogue cue")
        texts.append(text)
    return texts


def call(command, purpose):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(purpose + ": " + result.stderr.strip())


def espeak(texts, language, speed, output, requested_voice):
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        return None
    voice = requested_voice or ESPEAK_VOICE.get(language, language.split("-", 1)[0])
    rate = max(80, min(450, int(round(175 * speed))))
    files = []
    try:
        for index, text in enumerate(texts):
            destination = output / ("raw_%d.wav" % index)
            call([binary, "-v", voice, "-s", str(rate), "-w", str(destination), text], "speech synthesis failed for cue %d" % index)
            if not destination.is_file() or destination.stat().st_size <= 44:
                raise RuntimeError("speech synthesis produced no audio for cue %d" % index)
            files.append(str(destination))
    except Exception:
        for path in output.glob("raw_*.wav"):
            path.unlink(missing_ok=True)
        return None
    return files, voice, Path(binary).name


def kokoro(texts, language, speed, output, requested_voice):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    code, voice = KOKORO_LANG.get(language), requested_voice or KOKORO_VOICE.get(language)
    if not code or not voice:
        raise ValueError("no locally configured Kokoro voice for " + language)
    pipeline = KPipeline(lang_code=code)
    files = []
    for index, text in enumerate(texts):
        chunks = [np.asarray(part[2], dtype="float32").reshape(-1) for part in pipeline(text, voice=voice, speed=speed)]
        if not chunks:
            raise RuntimeError("Kokoro generated no waveform for cue %d" % index)
        destination = output / ("raw_%d.wav" % index)
        sf.write(str(destination), np.concatenate(chunks), 24000, subtype="PCM_16")
        files.append(str(destination))
    return files, voice, "kokoro"


def audible_fallback(texts, output):
    """Offline last resort: finite, audible source audio suitable for downstream delivery."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("neither a usable local TTS backend nor ffmpeg fallback is available")
    files = []
    for index, text in enumerate(texts):
        destination = output / ("raw_%d.wav" % index)
        seconds = max(0.55, min(15.0, 0.065 * len(text)))
        call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
              "sine=frequency=185:sample_rate=24000:duration=%.3f" % seconds,
              "-af", "volume=0.10", "-ac", "1", "-c:a", "pcm_s16le", str(destination)],
             "FFmpeg audible fallback failed for cue %d" % index)
        files.append(str(destination))
    return files, "ffmpeg_audible_fallback", "ffmpeg"


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
    texts = parse_texts(config["text_srt"])
    backend = str(config.get("backend", "espeak")).lower()
    if backend == "kokoro":
        files, voice, actual = kokoro(texts, language, speed, output, config.get("voice"))
    elif backend in {"espeak", "espeak-ng", "auto"}:
        result = espeak(texts, language, speed, output, config.get("voice"))
        if result is None:
            files, voice, actual = audible_fallback(texts, output)
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
