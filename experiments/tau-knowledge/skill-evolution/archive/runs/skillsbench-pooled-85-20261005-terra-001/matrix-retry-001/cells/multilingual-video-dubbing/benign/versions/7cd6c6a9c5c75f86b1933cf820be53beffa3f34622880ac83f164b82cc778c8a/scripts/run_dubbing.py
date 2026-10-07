#!/usr/bin/env python3
"""End-to-end dubbing entrypoint. Reads JSON stdin and writes JSON stdout."""
import json
import sys
from pathlib import Path


def main(config):
    from synthesize_speech import main as synthesize
    from build_dub import main as build

    job = {
        "video": "/root/input.mp4",
        "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt",
        "target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt",
        "source_language": "en",
        "output_dir": "/outputs",
        "backend": "espeak",
        "speed": 1.0,
    }
    job.update({key: value for key, value in config.items() if value is not None})
    for field in ("video", "segments_srt", "source_srt", "target_srt", "target_language_file"):
        if not Path(job[field]).is_file():
            raise ValueError("missing required input file: " + str(job[field]))

    target_language = Path(job["target_language_file"]).read_text(encoding="utf-8-sig").strip().lower()
    if not target_language:
        raise ValueError("target language file is empty")
    output_dir = Path(job["output_dir"])
    raw_dir = Path(job.get("raw_wav_dir") or output_dir / "_raw_tts")
    synth_request = {
        "text_srt": job["target_srt"], "language": target_language,
        "output_dir": str(raw_dir), "backend": job["backend"], "speed": job["speed"],
    }
    if job.get("voice"):
        synth_request["voice"] = job["voice"]
    synthesis = synthesize(synth_request)

    result = build({
        "video": job["video"], "segments_srt": job["segments_srt"],
        "source_srt": job["source_srt"], "target_srt": job["target_srt"],
        "source_language": str(job["source_language"]).strip(),
        "target_language": target_language, "output_dir": str(output_dir),
        "raw_wavs": synthesis["raw_wavs"],
    })
    required = [output_dir / "report.json", output_dir / "dubbed.mp4", output_dir / "tts_segments" / "seg_0.wav"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("pipeline did not create required deliverables: " + ", ".join(missing))
    result.update({"synthesis_backend": synthesis["backend"], "synthesis_voice": synthesis["voice"]})
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
