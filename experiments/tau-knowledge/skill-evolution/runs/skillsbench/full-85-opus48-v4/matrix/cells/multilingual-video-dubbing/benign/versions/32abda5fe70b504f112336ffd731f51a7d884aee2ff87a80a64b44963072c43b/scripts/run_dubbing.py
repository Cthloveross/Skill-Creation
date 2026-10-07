#!/usr/bin/env python3
"""End-to-end multilingual dubbing entrypoint.

Reads a JSON config from stdin (all keys optional; defaults match the task),
produces /outputs/tts_segments/seg_*.wav, /outputs/dubbed.mp4,
/outputs/report.json, and prints a JSON summary to stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import audio_utils as A  # noqa: E402
import srt_utils as S  # noqa: E402
import tts_engine as T  # noqa: E402

DEFAULTS = {
    "input_video": "/root/input.mp4",
    "segments_srt": "/root/segments.srt",
    "source_text_srt": "/root/source_text.srt",
    "target_language_txt": "/root/target_language.txt",
    "reference_target_srt": "/root/reference_target_text.srt",
    "output_dir": "/outputs",
    "also_output_dir": "/output",
    "source_language": None,
    "target_lufs": -23.0,
    "min_tempo": 0.75,
    "max_tempo": 1.5,
}

SR = 48000


def r4(x):
    return None if x is None else round(float(x), 4)


def detect_source_lang(text, override):
    if override:
        return override
    try:
        from langdetect import detect
        code = detect(text)
        return code.split("-")[0]
    except Exception:
        return "en"


def fit_segment(raw_wav, raw_sr, window_dur, out_seg, cfg):
    """Return (control, tts_dur_raw, seg_dur, warnings). Writes out_seg (48k mono)."""
    warn = []
    tmp_mono = out_seg + ".mono.wav"
    ok, err = A.to_mono48(raw_wav, tmp_mono)
    if not ok:
        raise RuntimeError("mono48 failed: %s" % err)
    arr, _ = A.read_wav(tmp_mono)
    raw_dur = len(arr) / float(SR)
    if raw_dur <= 0:
        raise RuntimeError("empty TTS audio")
    ratio = raw_dur / window_dur if window_dur > 0 else 1.0
    lo, hi = cfg["min_tempo"], cfg["max_tempo"]
    factor = min(max(ratio, lo), hi)
    tmp_t = out_seg + ".tempo.wav"
    ok, err = A.atempo48(tmp_mono, tmp_t, factor)
    if not ok:
        warn.append("atempo failed, using raw: %s" % err)
        tmp_t = tmp_mono
    sig, _ = A.read_wav(tmp_t)
    cur = len(sig) / float(SR)
    target_len = int(round(window_dur * SR))
    if len(sig) < target_len:
        control = "pad_silence"
        sig = np.concatenate([sig, np.zeros(target_len - len(sig), dtype=np.float32)])
    elif len(sig) > target_len:
        control = "trim"
        sig = sig[:target_len]
    else:
        control = "rate_adjust"
    # if tempo change itself produced the fit, call it rate_adjust
    if abs(factor - 1.0) > 1e-6 and abs(cur - window_dur) <= 0.02:
        control = "rate_adjust"
    A.write_wav(out_seg, sig, SR)
    for p in (tmp_mono, tmp_t):
        try:
            if p != out_seg and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    seg_dur = len(sig) / float(SR)
    return control, raw_dur, seg_dur, warn


def compute_mos(seg_path):
    try:
        import torch
        try:
            import librosa
            wave, _ = librosa.load(seg_path, sr=16000, mono=True)
        except Exception:
            arr, sr = A.read_wav(seg_path)
            # naive resample to 16k
            idx = (np.arange(int(len(arr) * 16000 / sr)) * sr / 16000).astype(int)
            idx = idx[idx < len(arr)]
            wave = arr[idx]
        predictor = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong",
                                   trust_repo=True)
        import numpy as _np
        with torch.no_grad():
            score = predictor(torch.from_numpy(_np.asarray(wave, dtype=_np.float32)).unsqueeze(0), 16000)
        return float(score.item())
    except Exception:
        return None


def main():
    try:
        cfg = dict(DEFAULTS)
        raw = sys.stdin.read().strip()
        if raw:
            cfg.update(json.loads(raw))
    except Exception as e:
        print(json.dumps({"error": "bad config json: %s" % e}))
        return 2

    warnings = []
    for key in ("input_video", "segments_srt", "reference_target_srt",
                "target_language_txt"):
        if not os.path.exists(cfg[key]):
            print(json.dumps({"error": "missing input: %s" % cfg[key]}))
            return 2

    out_dir = cfg["output_dir"]
    seg_dir = os.path.join(out_dir, "tts_segments")
    os.makedirs(seg_dir, exist_ok=True)

    target_lang = S.read_text(cfg["target_language_txt"]).strip().split()[0].lower()
    windows = [w for w in S.parse_srt(cfg["segments_srt"]) if w["start"] is not None]
    ref = S.parse_srt(cfg["reference_target_srt"])
    src = S.parse_srt(cfg["source_text_srt"]) if os.path.exists(cfg["source_text_srt"]) else []

    src_all = " ".join(s["text"] for s in src) if src else ""
    source_lang = detect_source_lang(src_all, cfg["source_language"])

    orig_dur = A.media_duration(cfg["input_video"]) or 0.0
    engine_used = None
    segments_report = []

    # full-length audio canvas
    canvas = np.zeros(int(round(orig_dur * SR)) if orig_dur > 0 else 0, dtype=np.float32)

    for i, w in enumerate(windows):
        wstart, wend = w["start"], w["end"] if w["end"] is not None else w["start"]
        wdur = max(wend - wstart, 0.001)
        tgt_text = ref[i]["text"] if i < len(ref) else (ref[-1]["text"] if ref else "")
        src_text = src[i]["text"] if i < len(src) else ""
        seg_path = os.path.join(seg_dir, "seg_%d.wav" % i)
        raw_path = os.path.join(seg_dir, "_raw_%d.wav" % i)
        control = "rate_adjust"
        tts_dur = wdur
        seg_dur = wdur
        if not tgt_text:
            warnings.append("segment %d has no target text" % i)
            A.write_wav(seg_path, np.zeros(int(round(wdur * SR)), dtype=np.float32), SR)
        else:
            try:
                _, raw_sr, engine_used = T.synthesize(tgt_text, target_lang, raw_path)
                control, tts_dur, seg_dur, w2 = fit_segment(
                    raw_path, raw_sr, wdur, seg_path, cfg)
                warnings.extend(w2)
            except Exception as e:
                warnings.append("TTS failed for segment %d: %s" % (i, e))
                A.write_wav(seg_path, np.zeros(int(round(wdur * SR)), dtype=np.float32), SR)
            finally:
                if os.path.exists(raw_path):
                    try:
                        os.remove(raw_path)
                    except Exception:
                        pass

        # normalize the standalone segment to target LUFS (BS.1770-4)
        after = A.normalize_file_to_lufs(seg_path, cfg["target_lufs"])
        if after is None:
            warnings.append("could not measure LUFS for seg_%d (ffmpeg?)" % i)

        # place into canvas
        sig, _ = A.read_wav(seg_path)
        start_idx = int(round(wstart * SR))
        if len(canvas) < start_idx + len(sig):
            canvas = np.concatenate([canvas, np.zeros(start_idx + len(sig) - len(canvas), dtype=np.float32)])
        canvas[start_idx:start_idx + len(sig)] += sig

        placed_start = wstart
        placed_end = wstart + seg_dur
        drift = placed_end - wend
        segments_report.append({
            "window_start_sec": r4(wstart),
            "window_end_sec": r4(wend),
            "placed_start_sec": r4(placed_start),
            "placed_end_sec": r4(placed_end),
            "source_text": src_text,
            "target_text": tgt_text,
            "window_duration_sec": r4(wdur),
            "tts_duration_sec": r4(tts_dur),
            "drift_sec": r4(drift),
            "duration_control": control,
        })

    # build + normalize full track
    full_path = os.path.join(out_dir, "_full_audio.wav")
    if len(canvas) == 0:
        canvas = np.zeros(SR, dtype=np.float32)
    A.write_wav(full_path, canvas, SR)
    A.normalize_file_to_lufs(full_path, cfg["target_lufs"])

    dubbed = os.path.join(out_dir, "dubbed.mp4")
    ok, err = A.mux(cfg["input_video"], full_path, dubbed)
    if not ok:
        warnings.append("mux failed: %s" % err[-400:])

    # closed-loop loudness correction on the final MP4
    measured = A.measure_lufs(dubbed) if os.path.exists(dubbed) else None
    for _ in range(3):
        if measured is None:
            break
        delta = cfg["target_lufs"] - measured
        if abs(delta) <= 0.3:
            break
        arr, sr = A.read_wav(full_path)
        A.write_wav(full_path, A.apply_gain_db(arr, delta), sr)
        ok, err = A.mux(cfg["input_video"], full_path, dubbed)
        if not ok:
            warnings.append("remux failed: %s" % err[-400:])
            break
        measured = A.measure_lufs(dubbed)

    new_dur = A.media_duration(dubbed) if os.path.exists(dubbed) else None

    report = {
        "source_language": source_lang,
        "target_language": target_lang,
        "audio_sample_rate_hz": SR,
        "audio_channels": 1,
        "original_duration_sec": r4(orig_dur),
        "new_duration_sec": r4(new_dur),
        "measured_lufs": r4(measured),
        "speech_segments": segments_report,
    }
    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass

    # mirror outputs if requested
    also = cfg.get("also_output_dir")
    if also and also != out_dir:
        try:
            import shutil
            dst_seg = os.path.join(also, "tts_segments")
            os.makedirs(dst_seg, exist_ok=True)
            for fn in os.listdir(seg_dir):
                shutil.copy2(os.path.join(seg_dir, fn), os.path.join(dst_seg, fn))
            if os.path.exists(dubbed):
                shutil.copy2(dubbed, os.path.join(also, "dubbed.mp4"))
            shutil.copy2(report_path, os.path.join(also, "report.json"))
        except Exception as e:
            warnings.append("mirror to %s failed: %s" % (also, e))

    mos = compute_mos(os.path.join(seg_dir, "seg_0.wav")) if segments_report else None

    print(json.dumps({
        "report_path": report_path,
        "report": report,
        "measured_lufs": r4(measured),
        "mos": mos,
        "engine": engine_used,
        "warnings": warnings,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
