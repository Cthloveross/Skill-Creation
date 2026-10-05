#!/usr/bin/env python3
"""Synthesize reference-SRT cues using installed Kokoro. JSON stdin -> JSON stdout."""
import json
import re
import sys
from pathlib import Path

TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
DEFAULT_VOICES = {
    "en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma",
    "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora",
    "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha",
}
KOKORO_LANG = {
    "en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z",
    "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h",
}


def parse_text_srt(path):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty target SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        time_i = next((i for i, line in enumerate(lines) if TIME_RE.match(line)), None)
        if time_i is None:
            raise ValueError("invalid target SRT block (missing time range)")
        text = " ".join(line for line in lines[time_i + 1:] if line).strip()
        if not text:
            raise ValueError("target SRT contains an empty dialogue cue")
        cues.append(text)
    return cues


def main(cfg):
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError("Kokoro synthesis requires installed kokoro, numpy, and soundfile") from exc

    for key in ("text_srt", "language", "output_dir"):
        if not cfg.get(key):
            raise ValueError("missing " + key)
    language = str(cfg["language"]).strip().lower()
    if language not in KOKORO_LANG:
        raise ValueError("no packaged Kokoro mapping for %r; use an installed neural TTS supporting that language" % language)
    speed = float(cfg.get("speed", 1.0))
    if speed <= 0:
        raise ValueError("speed must be positive")
    voice = cfg.get("voice") or DEFAULT_VOICES.get(language)
    if not voice:
        raise ValueError("a Kokoro voice must be supplied for " + language)

    output = Path(cfg["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code=KOKORO_LANG[language])
    files = []
    for index, text in enumerate(parse_text_srt(cfg["text_srt"])):
        pieces = []
        for result in pipeline(text, voice=voice, speed=speed):
            waveform = result[2]  # Kokoro's (graphemes, phonemes, waveform) result.
            pieces.append(np.asarray(waveform, dtype="float32").reshape(-1))
        if not pieces:
            raise RuntimeError("Kokoro returned no waveform for target cue %d" % index)
        audio = np.concatenate(pieces)
        if audio.size == 0:
            raise RuntimeError("Kokoro returned an empty waveform for target cue %d" % index)
        name = output / ("raw_%d.wav" % index)
        # Kokoro's standard packaged voices produce 24 kHz waveforms.
        sf.write(str(name), audio, 24000, subtype="PCM_24")
        files.append(str(name))
    return {"raw_wavs": files, "language": language, "voice": voice}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
