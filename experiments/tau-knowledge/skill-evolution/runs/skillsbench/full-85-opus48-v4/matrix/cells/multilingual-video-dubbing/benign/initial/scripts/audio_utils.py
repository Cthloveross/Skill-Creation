"""ffmpeg / wav helpers. Stdlib wave + numpy for predictable I/O."""
import os
import re
import subprocess
import wave
import numpy as np


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def have(tool):
    from shutil import which
    return which(tool) is not None


def media_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", path])
    try:
        return float(p.stdout.strip())
    except Exception:
        return None


def audio_stream_info(path):
    p = run(["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate,channels",
             "-of", "default=nk=1:nw=1", path])
    vals = [v for v in p.stdout.split() if v.strip()]
    sr = int(vals[0]) if len(vals) >= 1 and vals[0].isdigit() else None
    ch = int(vals[1]) if len(vals) >= 2 and vals[1].isdigit() else None
    return sr, ch


def has_video_stream(path):
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type",
             "-of", "default=nk=1:nw=1", path])
    return "video" in p.stdout


def measure_lufs(path):
    """Integrated loudness (LUFS) via ebur128, or None."""
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-af", "ebur128=peak=true", "-f", "null", "-"])
    matches = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", p.stderr)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except Exception:
        return None


def to_mono48(src, dst):
    """Decode any audio to 48k mono 16-bit PCM WAV."""
    p = run(["ffmpeg", "-y", "-i", src, "-ar", "48000", "-ac", "1",
             "-c:a", "pcm_s16le", dst])
    return p.returncode == 0, p.stderr


def atempo48(src, dst, factor):
    if abs(factor - 1.0) < 1e-6:
        return to_mono48(src, dst)
    p = run(["ffmpeg", "-y", "-i", src, "-filter:a",
             "atempo=%.6f" % factor, "-ar", "48000", "-ac", "1",
             "-c:a", "pcm_s16le", dst])
    return p.returncode == 0, p.stderr


def read_wav(path):
    w = wave.open(path, "rb")
    n, ch, sr, sw = (w.getnframes(), w.getnchannels(),
                     w.getframerate(), w.getsampwidth())
    data = w.readframes(n)
    w.close()
    if sw == 2:
        arr = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(data, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        arr = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError("unsupported sample width %d" % sw)
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr, sr


def write_wav(path, arr, sr=48000):
    arr = np.clip(np.asarray(arr, dtype=np.float32), -1.0, 1.0)
    ints = (arr * 32767.0).astype("<i2")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(ints.tobytes())
    w.close()


def apply_gain_db(arr, gain_db):
    return np.asarray(arr, dtype=np.float32) * (10.0 ** (gain_db / 20.0))


def normalize_file_to_lufs(path, target_lufs=-23.0):
    """Measure then linearly gain a wav to target LUFS. Returns measured_after."""
    meas = measure_lufs(path)
    if meas is None:
        return None
    arr, sr = read_wav(path)
    arr = apply_gain_db(arr, target_lufs - meas)
    write_wav(path, arr, sr)
    return measure_lufs(path)


def mux(video, audio, dst):
    p = run(["ffmpeg", "-y", "-i", video, "-i", audio,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "1",
             dst])
    return p.returncode == 0, p.stderr
