#!/usr/bin/env python3
"""End-to-end dubbing entrypoint. JSON stdin -> JSON stdout."""
import json
import sys
from pathlib import Path


def main(config):
    from synthesize_speech import main as synthesize
    from build_dub import main as build
    job = {"video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
           "source_srt": "/root/source_text.srt", "target_srt": "/root/reference_target_text.srt",
           "target_language_file": "/root/target_language.txt", "source_language": "en",
           "output_dir": "/outputs", "backend": "espeak", "speed": 1.0}
    job.update({k: v for k, v in config.items() if v is not None})
    for field in ("video", "segments_srt", "source_srt", "target_srt", "target_language_file"):
        if not Path(job[field]).is_file():
            raise ValueError("missing required input file: " + str(job[field]))
    language = Path(job["target_language_file"]).read_text(encoding="utf-8-sig").strip().lower()
    if not language:
        raise ValueError("target language file is empty")
    out = Path(job["output_dir"])
    raw = Path(job.get("raw_wav_dir") or out / "_raw_tts")
    request = {"text_srt": job["target_srt"], "language": language, "output_dir": str(raw),
               "backend": job["backend"], "speed": job["speed"]}
    if job.get("voice"):
        request["voice"] = job["voice"]
    synth = synthesize(request)
    result = build({"video": job["video"], "segments_srt": job["segments_srt"], "source_srt": job["source_srt"],
                    "target_srt": job["target_srt"], "source_language": str(job["source_language"]).strip(),
                    "target_language": language, "output_dir": str(out), "raw_wavs": synth["raw_wavs"]})
    expected = [out / "report.json", out / "dubbed.mp4", out / "tts_segments" / "seg_0.wav"]
    if any(not p.is_file() for p in expected):
        raise RuntimeError("pipeline ended without all required deliverables")
    result.update({"synthesis_backend": synth["backend"], "synthesis_voice": synth["voice"]})
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
