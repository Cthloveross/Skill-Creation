#!/usr/bin/env python3
"""Synthesize an SRT with installed Kokoro. JSON stdin -> JSON stdout."""
import json
import os
import sys
import re
from pathlib import Path

TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
DEFAULT_VOICES = {
    "en": "af_heart", "en-us": "af_heart", "en-gb": "bf_emma",
    "ja": "jf_alpha", "zh": "zf_xiaobei", "es": "ef_dora",
    "fr": "ff_siwis", "it": "if_sara", "pt": "pf_dora", "hi": "hf_alpha",
}
KOKORO_LANG = {"en": "a", "en-us": "a", "en-gb": "b", "ja": "j", "zh": "z", "es": "e", "fr": "f", "it": "i", "pt": "p", "hi": "h"}

def parse_srt(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    cues = []
    for block in blocks:
        lines = [x.strip() for x in block.splitlines()]
        time_i = next((i for i, x in enumerate(lines) if TIME_RE.match(x)), None)
        if time_i is None:
            raise ValueError("invalid SRT block (missing time range)")
        utterance = " ".join(x for x in lines[time_i + 1:] if x).strip()
        if not utterance:
            raise ValueError("empty target-language cue")
        cues.append(utterance)
    if not cues:
        raise ValueError("SRT contains no cues")
    return cues

def main(cfg):
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as e:
        raise RuntimeError("Kokoro synthesis needs installed kokoro, numpy, and soundfile") from e
    language = str(cfg["language"]).strip().lower()
    if language not in KOKORO_LANG:
        raise ValueError("no Kokoro language mapping for %r; use an installed target-language TTS engine" % language)
    text_srt = cfg["text_srt"]
    output = Path(cfg["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    voice = cfg.get("voice", DEFAULT_VOICES.get(language))
    if not voice:
        raise ValueError("voice is required for this language")
    speed = float(cfg.get("speed", 1.0))
    if speed <= 0:
        raise ValueError("speed must be positive")
    pipeline = KPipeline(lang_code=KOKORO_LANG[language])
    files = []
    for index, utterance in enumerate(parse_srt(text_srt)):
        chunks = []
        for result in pipeline(utterance, voice=voice, speed=speed):
            # Kokoro returns (graphemes, phonemes, waveform) tuples.
            chunks.append(np.asarray(result[2], dtype="float32").reshape(-1))
        if not chunks:
            raise RuntimeError("Kokoro returned no waveform for cue %d" % index)
        waveform = np.concatenate(chunks)
        if waveform.size == 0:
            raise RuntimeError("Kokoro returned empty waveform for cue %d" % index)
        filename = output / ("raw_%d.wav" % index)
        sf.write(str(filename), waveform, 24000, subtype="PCM_24")
        files.append(str(filename))
    return {"raw_wavs": files, "language": language, "voice": voice}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
