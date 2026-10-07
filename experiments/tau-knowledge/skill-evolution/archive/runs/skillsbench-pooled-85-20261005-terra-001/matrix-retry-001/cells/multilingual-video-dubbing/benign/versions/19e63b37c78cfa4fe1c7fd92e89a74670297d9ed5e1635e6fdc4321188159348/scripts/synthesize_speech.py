#!/usr/bin/env python3
"""Offline target-text speech synthesis. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
KOKORO_LANG = {
    "en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z",
    "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h",
}
KOKORO_VOICE = {
    "en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma",
    "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora",
    "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha",
}
# eSpeak voice identifiers are intentionally separate from Kokoro voice identifiers.
ESPEAK_VOICE = {"en-us": "en-us", "en-gb": "en-gb", "zh": "zh", "pt": "pt", "ja": "ja"}


def cues_from_srt(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    result = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        time_line = next((i for i, line in enumerate(lines) if TIME_RE.match(line)), None)
        if time_line is None:
            raise ValueError("target SRT cue lacks a valid time range")
        text = " ".join(x for x in lines[time_line + 1:] if x).strip()
        if not text:
            raise ValueError("target SRT contains an empty dialogue cue")
        result.append(text)
    return result


def synthesize_kokoro(texts, language, voice, speed, output):
    """Return raw files or raise; imports are deferred so fallback remains usable."""
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    code = KOKORO_LANG.get(language)
    if not code:
        raise ValueError("no Kokoro language mapping for " + language)
    selected_voice = voice or KOKORO_VOICE.get(language)
    if not selected_voice:
        raise ValueError("no default Kokoro voice for " + language)
    pipeline = KPipeline(lang_code=code)
    files = []
    for index, text in enumerate(texts):
        pieces = []
        for item in pipeline(text, voice=selected_voice, speed=speed):
            # Kokoro yields (graphemes, phonemes, waveform).
            pieces.append(np.asarray(item[2], dtype="float32").reshape(-1))
        if not pieces:
            raise RuntimeError("Kokoro returned no waveform for cue %d" % index)
        waveform = np.concatenate(pieces)
        if waveform.size == 0:
            raise RuntimeError("Kokoro returned an empty waveform for cue %d" % index)
        destination = output / ("raw_%d.wav" % index)
        sf.write(str(destination), waveform, 24000, subtype="PCM_24")
        files.append(str(destination))
    return files, selected_voice, "kokoro"


def synthesize_espeak(texts, language, speed, output):
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        raise RuntimeError("neither Kokoro nor an espeak-ng/espeak fallback is available")
    voice = ESPEAK_VOICE.get(language, language.split("-", 1)[0])
    # eSpeak speed is words/minute. 175 is its natural default; bound user scaling.
    rate = max(80, min(450, int(round(175 * speed))))
    files = []
    for index, text in enumerate(texts):
        destination = output / ("raw_%d.wav" % index)
        proc = subprocess.run([executable, "-v", voice, "-s", str(rate), "-w", str(destination), text],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("speech fallback failed for cue %d: %s" % (index, proc.stderr.strip()))
        files.append(str(destination))
    return files, voice, Path(executable).name


def main(cfg):
    for field in ("text_srt", "language", "output_dir"):
        if not cfg.get(field):
            raise ValueError("missing " + field)
    language = str(cfg["language"]).strip().lower()
    if not language:
        raise ValueError("empty language")
    speed = float(cfg.get("speed", 1.0))
    if speed <= 0:
        raise ValueError("speed must be positive")
    texts = cues_from_srt(cfg["text_srt"])
    output = Path(cfg["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    try:
        files, voice, backend = synthesize_kokoro(texts, language, cfg.get("voice"), speed, output)
    except Exception as neural_error:
        try:
            files, voice, backend = synthesize_espeak(texts, language, speed, output)
        except Exception as fallback_error:
            raise RuntimeError("neural synthesis failed (%s); fallback failed (%s)" %
                               (neural_error, fallback_error)) from fallback_error
    return {"raw_wavs": files, "language": language, "voice": voice, "backend": backend}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
