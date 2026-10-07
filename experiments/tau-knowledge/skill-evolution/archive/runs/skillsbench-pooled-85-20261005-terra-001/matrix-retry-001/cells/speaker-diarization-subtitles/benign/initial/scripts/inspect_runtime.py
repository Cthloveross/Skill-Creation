#!/usr/bin/env python3
"""Report runtime facts useful for selecting an audio diarization pipeline."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def command_version(name):
    path = shutil.which(name)
    if not path:
        return None
    try:
        proc = subprocess.run([name, "-version"], capture_output=True, text=True, timeout=10)
        line = (proc.stdout or proc.stderr).splitlines()
        version = line[0] if line else ""
    except Exception as exc:
        version = "version query failed: %s" % exc
    return {"path": path, "version": version}


def media_probe(path):
    if not os.path.isfile(path) or not shutil.which("ffprobe"):
        return None
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=True)
        data = json.loads(proc.stdout)
        raw = data.get("format", {}).get("duration")
        return {"duration_sec": float(raw)} if raw is not None else {"duration_sec": None}
    except Exception as exc:
        return {"error": str(exc)}


def cache_listing(root):
    p = Path(root).expanduser()
    if not p.is_dir():
        return None
    try:
        names = sorted(x.name for x in p.iterdir())[:100]
        return {"path": str(p), "entries": names}
    except OSError as exc:
        return {"path": str(p), "error": str(exc)}


def main():
    try:
        request = json.load(sys.stdin)
        input_path = request.get("input", "/root/input.mp4")
        if not isinstance(input_path, str):
            raise ValueError("input must be a path string")
        packages = [
            "numpy", "scipy", "sklearn", "torch", "torchaudio", "pyannote.audio",
            "speechbrain", "whisper", "faster_whisper", "transformers", "webrtcvad",
            "silero_vad", "soundfile", "librosa"
        ]
        result = {
            "ok": True,
            "input": {"path": input_path, "exists": os.path.isfile(input_path), "bytes": os.path.getsize(input_path) if os.path.isfile(input_path) else None},
            "executables": {name: command_version(name) for name in ["ffmpeg", "ffprobe", "python3", "whisper"]},
            "importable_packages": {name: importlib.util.find_spec(name) is not None for name in packages},
            "media": media_probe(input_path),
            "cache_roots": [x for x in [cache_listing("/root/.cache"), cache_listing("/root/.cache/huggingface"), cache_listing("/root/.cache/torch")] if x is not None],
            "python": sys.version,
        }
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
