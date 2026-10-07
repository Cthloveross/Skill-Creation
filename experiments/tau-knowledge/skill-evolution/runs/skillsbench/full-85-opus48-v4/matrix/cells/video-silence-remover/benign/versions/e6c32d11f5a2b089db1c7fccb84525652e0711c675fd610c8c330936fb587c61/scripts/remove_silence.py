#!/usr/bin/env python3
"""Remove the non-teaching opening and long pauses from a teaching video.

Input : JSON on stdin (or defaults). Keys: input, output_dir, min_pause,
        pause_margin, min_opening, preset.
Output: JSON on stdout with the written report, output paths, diagnostics and
        warnings. Also writes <output_dir>/compressed_video.mp4 and
        <output_dir>/compression_report.json.

The serialized removed/keep interval list is the single source of truth: both
audio and video are rebuilt from the identical keep list in one ffmpeg pass so
the streams stay aligned. Top-level report math is derived from the actual
measured media durations so original == compressed + removed exactly.
"""
import sys, os, json, subprocess, tempfile, math


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False)


def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path])
    try:
        return float(json.loads(r.stdout.decode())["format"]["duration"])
    except Exception:
        r2 = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=duration", "-of",
                  "default=nw=1:nk=1", path])
        try:
            return float(r2.stdout.decode().strip())
        except Exception:
            return 0.0


def has_audio(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path])
    return bool(r.stdout.decode().strip())


def load_audio(path, sr=16000):
    r = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
             "-ar", str(sr), "-f", "s16le", "-"])
    raw = r.stdout
    try:
        import numpy as np
        a = np.frombuffer(raw, dtype='<i2').astype('float32') / 32768.0
        return a, sr, np
    except Exception:
        import array
        a = array.array('h')
        a.frombytes(raw[:len(raw) - (len(raw) % 2)])
        return a, sr, None


def frame_energy_db(samples, sr, np, frame_sec=0.05):
    fl = max(1, int(sr * frame_sec))
    if np is not None:
        n = len(samples) // fl
        if n == 0:
            return [], frame_sec
        s = samples[:n * fl].reshape(n, fl)
        rms = (np.sqrt(np.mean(s * s, axis=1) + 1e-12))
        db = 20.0 * np.log10(rms + 1e-10)
        return db, fl / sr
    else:
        n = len(samples) // fl
        db = []
        for i in range(n):
            seg = samples[i * fl:(i + 1) * fl]
            ss = 0.0
            for v in seg:
                x = v / 32768.0
                ss += x * x
            rms = math.sqrt(ss / fl + 1e-12)
            db.append(20.0 * math.log10(rms + 1e-10))
        return db, fl / sr


def percentile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = int(q * (len(sorted_vals) - 1))
    return sorted_vals[idx]


def speech_mask(db, np):
    if np is not None and hasattr(db, 'size'):
        if db.size == 0:
            return [], 0.0
        noise = float(np.percentile(db, 20))
        peak = float(np.percentile(db, 95))
        thr = max(noise + 0.4 * (peak - noise), noise + 6.0)
        return (db > thr).tolist(), thr
    else:
        if not db:
            return [], 0.0
        s = sorted(db)
        noise = percentile(s, 0.20)
        peak = percentile(s, 0.95)
        thr = max(noise + 0.4 * (peak - noise), noise + 6.0)
        return [x > thr for x in db], thr


def prefix_sum(mask):
    pref = [0] * (len(mask) + 1)
    for i, v in enumerate(mask):
        pref[i + 1] = pref[i] + (1 if v else 0)
    return pref


def detect_audio_onset(mask, dt, win=4.0, frac=0.3, confirm=6.0):
    n = len(mask)
    if n == 0:
        return 0.0
    pref = prefix_sum(mask)
    w = max(1, int(win / dt))
    c = max(1, int(confirm / dt))

    def f(i, length):
        j = min(n, i + length)
        if j <= i:
            return 0.0
        return (pref[j] - pref[i]) / (j - i)

    for i in range(n):
        if f(i, w) >= frac and f(i, c) >= frac:
            return i * dt
    return 0.0


def find_silent_runs(mask, dt, min_dur):
    runs = []
    n = len(mask)
    i = 0
    while i < n:
        if not mask[i]:
            j = i
            while j < n and not mask[j]:
                j += 1
            start = i * dt
            end = j * dt
            if end - start >= min_dur:
                runs.append([start, end])
            i = j
        else:
            i += 1
    return runs


def load_visual_onset(path, fps=2.0, w=64, h=36, win=2.0):
    try:
        import numpy as np
    except Exception:
        return None, None
    r = run(["ffmpeg", "-v", "error", "-i", path, "-vf",
             f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"])
    raw = r.stdout
    fsize = w * h
    nframes = len(raw) // fsize
    if nframes < 3:
        return None, None
    arr = np.frombuffer(raw[:nframes * fsize], dtype='uint8').astype('float32')
    arr = arr.reshape(nframes, fsize)
    diff = np.abs(np.diff(arr, axis=0)).mean(axis=1)
    dt = 1.0 / fps
    vals = diff
    base = float(np.percentile(vals, 20))
    peak = float(np.percentile(vals, 90))
    thr = max(base + 0.3 * (peak - base), base + 1.0)
    wlen = max(1, int(win / dt))
    onset = 0.0
    for i in range(len(vals) - wlen + 1):
        if bool((vals[i:i + wlen] > thr).all()):
            onset = (i + 1) * dt
            break
    return onset, thr


def merge_intervals(ivs):
    ivs = sorted([list(x) for x in ivs if x[1] > x[0]])
    out = []
    for s, e in ivs:
        if out and s <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def complement(removed, duration):
    keep = []
    cur = 0.0
    for s, e in removed:
        s = max(0.0, min(s, duration))
        e = max(0.0, min(e, duration))
        if s > cur + 1e-4:
            keep.append([cur, s])
        cur = max(cur, e)
    if duration - cur > 1e-4:
        keep.append([cur, duration])
    return [k for k in keep if k[1] - k[0] > 0.05]


def build_video(input_path, keep, output_path, preset):
    expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep)
    graph = (f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[outv];"
             f"[0:a]aselect='{expr}',asetpts=N/SR/TB[outa]")
    fd, script = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(graph)
    cmd = ["ffmpeg", "-y", "-i", input_path,
           "-filter_complex_script", script,
           "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", preset, "-crf", "23",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", output_path]
    r = run(cmd)
    try:
        os.remove(script)
    except OSError:
        pass
    return r


def build_video_no_audio(input_path, keep, output_path, preset):
    expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep)
    graph = f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[outv]"
    fd, script = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(graph)
    cmd = ["ffmpeg", "-y", "-i", input_path,
           "-filter_complex_script", script, "-map", "[outv]",
           "-c:v", "libx264", "-preset", preset, "-crf", "23",
           "-pix_fmt", "yuv420p", output_path]
    r = run(cmd)
    try:
        os.remove(script)
    except OSError:
        pass
    return r


def main():
    try:
        data = sys.stdin.read()
        cfg = json.loads(data) if data.strip() else {}
    except Exception:
        cfg = {}

    warnings = []
    inp = cfg.get("input")
    if not inp:
        for cand in ("data/input_video.mp4", "/root/data/input_video.mp4"):
            if os.path.exists(cand):
                inp = cand
                break
    if not inp or not os.path.exists(inp):
        print(json.dumps({"error": f"input video not found: {inp}"}))
        return 1

    out_dir = cfg.get("output_dir", ".")
    os.makedirs(out_dir, exist_ok=True)
    out_video = os.path.join(out_dir, "compressed_video.mp4")
    out_report = os.path.join(out_dir, "compression_report.json")

    min_pause = float(cfg.get("min_pause", 2.0))
    margin = float(cfg.get("pause_margin", 0.15))
    min_opening = float(cfg.get("min_opening", 1.5))
    preset = cfg.get("preset", "veryfast")

    duration = ffprobe_duration(inp)
    if duration <= 0:
        print(json.dumps({"error": "could not probe input duration"}))
        return 1

    audio_present = has_audio(inp)
    audio_onset = 0.0
    speech_thr = None
    silent_runs = []
    if audio_present:
        samples, sr, np = load_audio(inp)
        db, dt = frame_energy_db(samples, sr, np)
        mask, speech_thr = speech_mask(db, np)
        audio_onset = detect_audio_onset(mask, dt)
        silent_runs = find_silent_runs(mask, dt, min_pause)
    else:
        warnings.append("no audio stream: pause detection skipped")

    visual_onset, visual_thr = load_visual_onset(inp)
    if visual_onset is None:
        warnings.append("visual signal unavailable (no numpy or too few frames)")

    # ---- opening decision ----
    opening_end = audio_onset
    if visual_onset is not None:
        # static-with-noise opening: extend to motion onset when the video is
        # clearly static well past the audio onset.
        if visual_onset > opening_end + 1.0 and visual_onset < 0.4 * duration:
            opening_end = visual_onset
        # if audio gave nothing but there is a clear static prefix, use motion.
        if opening_end < min_opening and 0 < visual_onset < 0.4 * duration:
            opening_end = visual_onset
    # safety clamp: never remove an implausibly large prefix.
    if opening_end > 0.4 * duration:
        fallback = audio_onset if 0 < audio_onset < 0.4 * duration else 0.0
        warnings.append(
            f"opening onset {opening_end:.2f}s exceeded 40% of duration; "
            f"clamped to {fallback:.2f}s")
        opening_end = fallback
    if opening_end < min_opening:
        opening_end = 0.0

    content_start = opening_end

    # ---- removed intervals ----
    removed = []
    if opening_end > 0:
        removed.append([0.0, opening_end])
    for s, e in silent_runs:
        s2 = max(s, content_start)
        if e - s2 < min_pause:
            continue
        s3 = s2 + margin
        e3 = e - margin
        if e3 - s3 >= max(min_pause - 2 * margin, 0.5):
            removed.append([s3, e3])
    removed = merge_intervals(removed)
    removed = [[round(s, 3), round(e, 3)] for s, e in removed]

    keep = complement(removed, duration)
    if not keep:
        warnings.append("keep list empty; keeping entire timeline")
        keep = [[0.0, duration]]
        removed = []

    # ---- build output ----
    if audio_present:
        r = build_video(inp, keep, out_video, preset)
    else:
        r = build_video_no_audio(inp, keep, out_video, preset)
    if r.returncode != 0 or not os.path.exists(out_video):
        print(json.dumps({
            "error": "ffmpeg failed",
            "stderr": r.stderr.decode(errors="replace")[-2000:],
            "keep": keep, "removed": removed}))
        return 1

    # ---- measure and report ----
    compressed = ffprobe_duration(out_video)
    original = round(duration, 3)
    compressed_r = round(compressed, 3)
    removed_total = round(original - compressed_r, 3)
    pct = round((removed_total / original * 100.0) if original > 0 else 0.0, 3)

    segments = [{"start": round(s, 3), "end": round(e, 3),
                 "duration": round(e - s, 3)} for s, e in removed]

    report = {
        "original_duration_seconds": original,
        "compressed_duration_seconds": compressed_r,
        "removed_duration_seconds": removed_total,
        "compression_percentage": pct,
        "segments_removed": segments,
    }
    with open(out_report, "w") as fh:
        json.dump(report, fh, indent=2)

    print(json.dumps({
        "report": report,
        "output_video": os.path.abspath(out_video),
        "report_path": os.path.abspath(out_report),
        "diagnostics": {
            "audio_present": audio_present,
            "audio_onset": round(audio_onset, 3),
            "visual_onset": (round(visual_onset, 3)
                             if visual_onset is not None else None),
            "speech_threshold_db": (round(speech_thr, 3)
                                    if speech_thr is not None else None),
            "opening_end": round(opening_end, 3),
            "removed_intervals": removed,
            "keep_intervals": [[round(s, 3), round(e, 3)] for s, e in keep],
        },
        "warnings": warnings,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
