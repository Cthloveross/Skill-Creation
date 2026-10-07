#!/usr/bin/env python3
"""Extract audio and transcribe to timestamped segments.

stdin JSON: {"video": path, "wav": optional path, "model": "small",
             "out": optional transcript cache path, "allow_install": true}
stdout JSON: {"segments":[{"start":float,"end":float,"text":str}], "backend":str}

Prefers faster-whisper (int8 CPU), falls back to openai-whisper. Caches the
transcript to `out` if given.
"""
import json
import os
import subprocess
import sys
import tempfile


def extract_wav(video, wav):
    cmd = ["ffmpeg", "-y", "-i", video, "-vn", "-acodec", "pcm_s16le",
           "-ar", "16000", "-ac", "1", wav]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return wav


def _try_import_faster():
    try:
        from faster_whisper import WhisperModel  # noqa
        return True
    except Exception:
        return False


def _try_import_openai():
    try:
        import whisper  # noqa
        return True
    except Exception:
        return False


def _pip_install(pkg):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", pkg],
                       check=True)
        return True
    except Exception:
        return False


def transcribe_faster(wav, model_size):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(wav, beam_size=1, vad_filter=False)
    out = []
    for s in segments:
        out.append({"start": float(s.start), "end": float(s.end),
                    "text": (s.text or "").strip()})
    return out


def transcribe_openai(wav, model_size):
    import whisper
    model = whisper.load_model(model_size)
    result = model.transcribe(wav, verbose=False)
    out = []
    for s in result.get("segments", []):
        out.append({"start": float(s["start"]), "end": float(s["end"]),
                    "text": (s.get("text") or "").strip()})
    return out


def run(cfg):
    video = cfg["video"]
    model_size = cfg.get("model", "small")
    out_path = cfg.get("out")
    allow_install = cfg.get("allow_install", True)

    # reuse cache if present and non-empty
    if out_path and os.path.exists(out_path):
        try:
            with open(out_path) as f:
                cached = json.load(f)
            if cached.get("segments"):
                return cached
        except Exception:
            pass

    wav = cfg.get("wav")
    tmp = None
    if not wav:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav = tmp.name
        tmp.close()
    extract_wav(video, wav)

    backend = None
    if _try_import_faster():
        backend = "faster-whisper"
    elif _try_import_openai():
        backend = "openai-whisper"
    elif allow_install and _pip_install("faster-whisper") and _try_import_faster():
        backend = "faster-whisper"
    elif allow_install and _pip_install("openai-whisper") and _try_import_openai():
        backend = "openai-whisper"

    if backend == "faster-whisper":
        segments = transcribe_faster(wav, model_size)
    elif backend == "openai-whisper":
        segments = transcribe_openai(wav, model_size)
    else:
        raise RuntimeError(
            "No Whisper backend available (install faster-whisper or openai-whisper).")

    result = {"segments": segments, "backend": backend}
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f)
    return result


if __name__ == "__main__":
    cfg = json.load(sys.stdin)
    print(json.dumps(run(cfg)))
