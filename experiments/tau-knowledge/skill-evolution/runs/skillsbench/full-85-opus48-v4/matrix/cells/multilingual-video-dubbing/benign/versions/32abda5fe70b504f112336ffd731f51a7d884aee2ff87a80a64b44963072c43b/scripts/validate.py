#!/usr/bin/env python3
"""Validate dubbing outputs against the public requirements.
stdin: {"report_path": "/outputs/report.json"} (defaults shown).
stdout: {"ok": bool, "problems": [...], "checked": {...}}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_utils as A  # noqa: E402


def main():
    cfg = {"report_path": "/outputs/report.json", "target_lufs": -23.0,
           "lufs_tol": 1.5}
    raw = sys.stdin.read().strip()
    if raw:
        cfg.update(json.loads(raw))
    probs = []
    rp = cfg["report_path"]
    out_dir = os.path.dirname(rp)
    if not os.path.exists(rp):
        print(json.dumps({"ok": False, "problems": ["missing report: %s" % rp]}))
        return 0
    rep = json.load(open(rp, encoding="utf-8"))

    seg0 = os.path.join(out_dir, "tts_segments", "seg_0.wav")
    dubbed = os.path.join(out_dir, "dubbed.mp4")
    if not os.path.exists(seg0):
        probs.append("missing %s" % seg0)
    if not os.path.exists(dubbed):
        probs.append("missing %s" % dubbed)

    if os.path.exists(dubbed):
        if not A.has_video_stream(dubbed):
            probs.append("dubbed.mp4 has no video stream")
        sr, ch = A.audio_stream_info(dubbed)
        if sr != 48000:
            probs.append("final sample_rate=%s (want 48000)" % sr)
        if ch != 1:
            probs.append("final channels=%s (want 1)" % ch)

    for k in ("source_language", "target_language", "audio_sample_rate_hz",
              "audio_channels", "original_duration_sec", "new_duration_sec",
              "measured_lufs", "speech_segments"):
        if k not in rep:
            probs.append("report missing field %s" % k)
    if rep.get("audio_sample_rate_hz") != 48000:
        probs.append("report audio_sample_rate_hz != 48000")
    if rep.get("audio_channels") != 1:
        probs.append("report audio_channels != 1")
    for fld in ("source_language", "target_language"):
        v = rep.get(fld)
        if not isinstance(v, str) or not (1 <= len(v) <= 5):
            probs.append("%s not a short language code: %r" % (fld, v))

    ml = rep.get("measured_lufs")
    if ml is None:
        probs.append("measured_lufs is null")
    elif abs(ml - cfg["target_lufs"]) > cfg["lufs_tol"]:
        probs.append("measured_lufs %.2f far from %.1f" % (ml, cfg["target_lufs"]))

    for i, s in enumerate(rep.get("speech_segments", [])):
        if abs((s.get("placed_start_sec") or 0) - (s.get("window_start_sec") or 0)) > 0.01:
            probs.append("seg %d placed_start not within 10ms of window_start" % i)
        if abs(s.get("drift_sec") or 0) > 0.2:
            probs.append("seg %d drift %.3f exceeds 0.2s" % (i, s.get("drift_sec")))
        if s.get("duration_control") not in ("rate_adjust", "pad_silence", "trim"):
            probs.append("seg %d bad duration_control %r" % (i, s.get("duration_control")))
        for f in ("window_duration_sec", "tts_duration_sec"):
            if (s.get(f) or 0) < 0:
                probs.append("seg %d negative %s" % (i, f))

    print(json.dumps({"ok": not probs, "problems": probs,
                      "checked": {"report": rp}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
