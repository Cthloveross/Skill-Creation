#!/usr/bin/env python3
"""End-to-end speaker diarization + subtitle pipeline.

Stdin  : optional JSON {"input":...,"out_rttm":...,"out_ass":...,"out_report":...}
Stdout : JSON status {"ok":bool, "num_speakers":int, "total_speech_sec":float,
                      "audio_duration_sec":float, "notes":str}

Run `--probe` to only report which backends are importable.

Components are discovered at runtime; nothing about the recording is hardcoded.
Statistics are derived from the produced RTTM/audio.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formats  # noqa: E402


def log(msg):
    print(f"[pipeline] {msg}", file=sys.stderr, flush=True)


def _can_import(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def probe():
    mods = ["torch", "torchaudio", "numpy", "sklearn", "soundfile",
            "speechbrain", "pyannote.audio", "faster_whisper", "whisper",
            "webrtcvad"]
    report = {m: _can_import(m) for m in mods}
    report["ffmpeg"] = _which("ffmpeg")
    report["ffprobe"] = _which("ffprobe")
    return report


def _which(exe):
    from shutil import which
    return which(exe) is not None


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def ffprobe_duration(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            text=True).strip()
        return float(out)
    except Exception:
        return None


def extract_audio(src, wav):
    subprocess.check_call(
        ["ffmpeg", "-y", "-i", src, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", wav],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_wav(wav, sr=16000):
    import numpy as np
    try:
        import soundfile as sf
        data, file_sr = sf.read(wav, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data.astype("float32"), file_sr
    except Exception:
        import wave
        with wave.open(wav, "rb") as w:
            file_sr = w.getframerate()
            n = w.getnframes()
            raw = w.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
        return data, file_sr


# ---------------------------------------------------------------------------
# VAD -> list of (start_sec, end_sec)
# ---------------------------------------------------------------------------

def vad_silero(wav_path):
    import torch
    model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                  trust_repo=True)
    (get_speech_timestamps, _, read_audio, _, _) = utils
    wav = read_audio(wav_path, sampling_rate=16000)
    ts = get_speech_timestamps(wav, model, sampling_rate=16000)
    return [(t["start"] / 16000.0, t["end"] / 16000.0) for t in ts]


def vad_webrtc(data, sr):
    import webrtcvad
    import numpy as np
    vad = webrtcvad.Vad(2)
    frame_ms = 30
    fl = int(sr * frame_ms / 1000)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2").tobytes()
    segs = []
    cur = None
    for i in range(0, len(data) - fl, fl):
        frame = pcm[i * 2:(i + fl) * 2]
        if len(frame) < fl * 2:
            break
        try:
            speech = vad.is_speech(frame, sr)
        except Exception:
            speech = False
        t = i / sr
        if speech and cur is None:
            cur = t
        elif not speech and cur is not None:
            segs.append((cur, t))
            cur = None
    if cur is not None:
        segs.append((cur, len(data) / sr))
    return _merge_close(segs, gap=0.3)


def vad_energy(data, sr):
    """Last-resort energy/pause segmentation. Never returns a single all-audio
    segment unless the whole signal is one contiguous voiced region."""
    import numpy as np
    win = int(0.03 * sr)
    if win <= 0:
        return []
    n = len(data) // win
    energies = np.array([
        float(np.sqrt(np.mean(data[i * win:(i + 1) * win] ** 2) + 1e-12))
        for i in range(n)])
    if n == 0:
        return []
    thr = max(np.percentile(energies, 30) * 1.5, energies.mean() * 0.5)
    speech = energies > thr
    segs = []
    cur = None
    for i, s in enumerate(speech):
        t = i * win / sr
        if s and cur is None:
            cur = t
        elif not s and cur is not None:
            segs.append((cur, t))
            cur = None
    if cur is not None:
        segs.append((cur, n * win / sr))
    return _merge_close(segs, gap=0.4)


def _merge_close(segs, gap=0.3, minlen=0.1):
    segs = sorted(segs)
    out = []
    for s, e in segs:
        if e - s < minlen:
            continue
        if out and s - out[-1][1] <= gap:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def run_vad(wav_path, data, sr, used):
    for name, fn in (("silero-vad", lambda: vad_silero(wav_path)),
                     ("webrtcvad", lambda: vad_webrtc(data, sr)),
                     ("energy-vad", lambda: vad_energy(data, sr))):
        try:
            segs = fn()
            if segs:
                used["vad"] = name
                return segs
        except Exception as exc:  # pragma: no cover
            log(f"VAD {name} failed: {exc}")
    used["vad"] = "none"
    return []


# ---------------------------------------------------------------------------
# Speaker embeddings + clustering
# ---------------------------------------------------------------------------

def embed_segments(data, sr, segs, used):
    """Return (labels list parallel to segs). Short segments inherit the
    nearest embedded segment's label."""
    import numpy as np
    try:
        import torch
        from speechbrain.pretrained import EncoderClassifier
    except Exception:
        try:
            import torch
            from speechbrain.inference import EncoderClassifier
        except Exception as exc:
            log(f"speechbrain unavailable: {exc}")
            return None
    try:
        clf = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=os.path.join(os.path.expanduser("~"),
                                 ".cache", "ecapa"))
    except Exception as exc:
        log(f"ECAPA load failed: {exc}")
        return None
    used["embedding"] = "speechbrain/spkrec-ecapa-voxceleb"

    min_emb = 0.5
    embs = []
    emb_idx = []
    for i, (s, e) in enumerate(segs):
        if e - s < min_emb:
            continue
        a = int(s * sr)
        b = int(e * sr)
        clip = data[a:b]
        if len(clip) < int(0.2 * sr):
            continue
        try:
            import torch
            t = torch.tensor(clip).float().unsqueeze(0)
            with torch.no_grad():
                v = clf.encode_batch(t).squeeze().cpu().numpy().reshape(-1)
            embs.append(v)
            emb_idx.append(i)
        except Exception as exc:
            log(f"embed seg {i} failed: {exc}")
    if not embs:
        return None
    X = np.vstack(embs).astype("float64")
    # l2 normalize for cosine
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    labels_sub = cluster(X, used)
    # map back to all segments
    labels = [None] * len(segs)
    for k, i in enumerate(emb_idx):
        labels[i] = int(labels_sub[k])
    # assign short/unembedded segs to nearest embedded seg in time
    for i, (s, e) in enumerate(segs):
        if labels[i] is not None:
            continue
        mid = (s + e) / 2
        best = None
        bestd = 1e18
        for j in emb_idx:
            m2 = (segs[j][0] + segs[j][1]) / 2
            d = abs(mid - m2)
            if d < bestd:
                bestd = d
                best = labels[j]
        labels[i] = best if best is not None else 0
    return labels


def cluster(X, used):
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    thr = float(os.environ.get("DIAR_THRESHOLD", "0.70"))
    if X.shape[0] == 1:
        used["clustering"] = "single-segment"
        return np.array([0])
    try:
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=thr,
            metric="cosine", linkage="average")
        labels = model.fit_predict(X)
    except TypeError:
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=thr,
            affinity="cosine", linkage="average")
        labels = model.fit_predict(X)
    used["clustering"] = f"agglomerative(cosine,avg,thr={thr})"
    return labels


# ---------------------------------------------------------------------------
# Optional pyannote full pipeline
# ---------------------------------------------------------------------------

def try_pyannote(wav_path, used):
    try:
        from pyannote.audio import Pipeline
    except Exception:
        return None
    token = os.environ.get("HF_TOKEN") or os.environ.get(
        "HUGGINGFACE_TOKEN")
    for model_id in ("pyannote/speaker-diarization-3.1",
                     "pyannote/speaker-diarization"):
        try:
            pipe = Pipeline.from_pretrained(model_id, use_auth_token=token)
            diar = pipe(wav_path)
            segs = []
            lab_map = {}
            for turn, _, spk in diar.itertracks(yield_label=True):
                if spk not in lab_map:
                    lab_map[spk] = len(lab_map)
                segs.append((turn.start, turn.end, lab_map[spk]))
            if segs:
                used["diarization"] = f"pyannote:{model_id}"
                return segs
        except Exception as exc:
            log(f"pyannote {model_id} failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# ASR
# ---------------------------------------------------------------------------

def transcribe(wav_path, used):
    """Return list of word dicts {start,end,word} if possible, else segment
    dicts. Also returns a flag whether word-level timing is present."""
    model_size = os.environ.get("WHISPER_MODEL", "small")
    # faster-whisper
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = m.transcribe(wav_path, word_timestamps=True)
        words = []
        seg_texts = []
        for seg in segments:
            seg_texts.append((seg.start, seg.end, seg.text))
            if seg.words:
                for w in seg.words:
                    if w.start is None:
                        continue
                    words.append({"start": w.start, "end": w.end,
                                  "word": w.word})
        used["asr"] = f"faster-whisper:{model_size}"
        if words:
            return words, True
        return [{"start": s, "end": e, "word": t} for s, e, t in seg_texts], False
    except Exception as exc:
        log(f"faster-whisper failed: {exc}")
    # openai-whisper
    try:
        import whisper
        m = whisper.load_model(model_size)
        r = m.transcribe(wav_path, word_timestamps=True)
        words = []
        seg_texts = []
        for seg in r.get("segments", []):
            seg_texts.append((seg["start"], seg["end"], seg["text"]))
            for w in seg.get("words", []) or []:
                words.append({"start": w["start"], "end": w["end"],
                              "word": w["word"]})
        used["asr"] = f"openai-whisper:{model_size}"
        if words:
            return words, True
        return [{"start": s, "end": e, "word": t} for s, e, t in seg_texts], False
    except Exception as exc:
        log(f"openai-whisper failed: {exc}")
    used["asr"] = "none"
    return [], False


def assign_text(diar_segs, words, word_level):
    """diar_segs: (start,end,label_int). words: list of {start,end,word}.
    Returns dict seg_index -> text."""
    texts = {i: [] for i in range(len(diar_segs))}
    for w in words:
        ws, we = w.get("start"), w.get("end")
        if ws is None:
            continue
        mid = (ws + we) / 2 if we is not None else ws
        # find segment containing midpoint; else max-overlap
        placed = False
        for i, (s, e, _l) in enumerate(diar_segs):
            if s <= mid <= e:
                texts[i].append(w["word"])
                placed = True
                break
        if not placed:
            best, bestov = None, 0.0
            for i, (s, e, _l) in enumerate(diar_segs):
                ov = min(e, we if we is not None else ws) - max(s, ws)
                if ov > bestov:
                    bestov = ov
                    best = i
            if best is not None and bestov > 0:
                texts[best].append(w["word"])
    return {i: " ".join(x).strip() for i, x in texts.items()}


# ---------------------------------------------------------------------------
# Segment post-processing
# ---------------------------------------------------------------------------

def finalize_segments(labeled):
    """labeled: list (start,end,label_int). Merge adjacent same-label and
    drop sub-threshold tiny segments."""
    min_seg = float(os.environ.get("MIN_SEG_SEC", "0.20"))
    labeled = sorted(labeled)
    merged = []
    for s, e, l in labeled:
        if merged and merged[-1][2] == l and s - merged[-1][1] <= 0.4:
            merged[-1] = (merged[-1][0], e, l)
        else:
            merged.append((s, e, l))
    merged = [(s, e, l) for s, e, l in merged if e - s >= min_seg]
    return merged


def remap_labels(labeled):
    """Relabel by first appearance -> contiguous 0..k."""
    order = {}
    for _s, _e, l in labeled:
        if l not in order:
            order[l] = len(order)
    out = [(s, e, order[l]) for s, e, l in labeled]
    return out, len(order)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "--probe" in sys.argv:
        print(json.dumps(probe(), indent=2))
        return

    cfg = {}
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    if raw.strip():
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}

    src = cfg.get("input", "/root/input.mp4")
    out_rttm = cfg.get("out_rttm", "/root/diarization.rttm")
    out_ass = cfg.get("out_ass", "/root/subtitles.ass")
    out_report = cfg.get("out_report", "/root/report.json")
    wav = cfg.get("wav", "/tmp/diar_audio.wav")

    used = {}
    steps = []
    libs = set()
    cmds = {"python3"}
    notes = []

    # 1. audio extraction
    extract_audio(src, wav)
    used["audio_extraction"] = "ffmpeg (16kHz mono pcm_s16le wav)"
    cmds.add("ffmpeg")
    cmds.add("ffprobe")
    steps.append("audio_extraction")
    duration = ffprobe_duration(src) or ffprobe_duration(wav) or 0.0

    data, sr = load_wav(wav)
    libs.add("numpy")

    # 2+3. diarization: try pyannote full pipeline, else custom
    diar_segs = try_pyannote(wav, used)
    if diar_segs is not None:
        libs.add("pyannote.audio")
        steps.append("diarization")
    else:
        segs = run_vad(wav, data, sr, used)
        if segs:
            steps.append("voice_activity_detection")
            if used.get("vad") == "silero-vad":
                libs.add("torch")
            if used.get("vad") == "webrtcvad":
                libs.add("webrtcvad")
        labels = None
        if segs:
            labels = embed_segments(data, sr, segs, used)
        if labels is not None:
            libs.add("speechbrain")
            libs.add("scikit-learn")
            libs.add("torch")
            diar_segs = [(s, e, labels[i]) for i, (s, e) in enumerate(segs)]
            used["diarization"] = "custom VAD+ECAPA+agglomerative"
            steps.append("speaker_embedding")
            steps.append("clustering")
        elif segs:
            # no embeddings: fall back to pause-separated single-speaker turns
            diar_segs = [(s, e, 0) for s, e in segs]
            used["diarization"] = "VAD-only (single speaker, no embedding model)"
            notes.append("No speaker-embedding model available; emitted "
                         "VAD turns as one speaker.")
        else:
            diar_segs = []
            notes.append("No speech detected / no VAD backend available.")

    diar_segs = finalize_segments(diar_segs)
    diar_segs, num_spk = remap_labels(diar_segs)

    # 4. ASR
    words, word_level = transcribe(wav, used)
    if used.get("asr") != "none":
        steps.append("transcription")
        if used["asr"].startswith("faster-whisper"):
            libs.add("faster-whisper")
        else:
            libs.add("openai-whisper")
    else:
        notes.append("No ASR backend available; subtitles may be empty.")

    seg_text = assign_text(diar_segs, words, word_level)

    # 5. write artifacts
    rttm_segments = [(s, e, f"spk{l:02d}") for s, e, l in diar_segs]
    formats.write_rttm(out_rttm, rttm_segments, file_id="input")
    steps.append("rttm_generation")

    cues = []
    for i, (s, e, l) in enumerate(diar_segs):
        txt = seg_text.get(i, "")
        cues.append((s, e, f"SPEAKER_{l:02d}", txt))
    formats.write_ass(out_ass, cues)
    steps.append("subtitle_generation")

    total_speech = sum(e - s for s, e, _l in diar_segs)
    report = {
        "num_speakers_pred": num_spk,
        "total_speech_time_sec": round(total_speech, 3),
        "audio_duration_sec": round(duration, 3),
        "steps_completed": steps,
        "commands_used": sorted(cmds),
        "libraries_used": sorted(libs),
        "tools_used": used,
        "notes": " ".join(notes) if notes else
                 "Diarization + ASR completed; stats derived from RTTM.",
    }
    with open(out_report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    steps.append("report_generation")

    print(json.dumps({
        "ok": True,
        "num_speakers": num_spk,
        "total_speech_sec": round(total_speech, 3),
        "audio_duration_sec": round(duration, 3),
        "segments": len(diar_segs),
        "notes": report["notes"],
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
