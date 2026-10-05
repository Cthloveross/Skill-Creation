#!/usr/bin/env python3
"""Acoustic diarization + turn ASR runner. JSON stdin -> JSON stdout."""
import contextlib, json, math, os, shutil, subprocess, sys
from pathlib import Path

import numpy as np
from validate_outputs import validate

def fail(message):
    raise RuntimeError(message)

def call(args):
    try:
        return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        fail("required executable not found: " + args[0])
    except subprocess.CalledProcessError as exc:
        fail("command failed (%s): %s" % (args[0], exc.stderr[-1000:]))

def extract_wav(video, wav):
    if not shutil.which("ffmpeg"):
        fail("ffmpeg is required to decode the input video")
    call(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
    import wave
    with wave.open(str(wav), "rb") as w:
        if w.getnchannels() != 1 or w.getframerate() != 16000 or w.getsampwidth() != 2:
            fail("ffmpeg extraction did not produce 16 kHz mono PCM WAV")
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        return audio, float(w.getnframes()) / w.getframerate(), w.getframerate()

def vad_regions(audio, sr):
    """Conservative acoustic VAD; returns only observed active intervals."""
    frame = max(1, round(.03 * sr))
    count = len(audio) // frame
    if count < 4:
        fail("audio is too short for acoustic speech detection")
    x = audio[:count * frame].reshape(count, frame)
    db = 20 * np.log10(np.sqrt(np.mean(x * x, axis=1)) + 1e-8)
    low, high = np.percentile(db, [15, 90])
    if high - low < 5:
        fail("acoustic VAD cannot distinguish speech from the recording noise floor")
    threshold = low + .38 * (high - low)
    active = db >= threshold
    # A short hangover preserves consonant onsets/offsets without turning all gaps into speech.
    pad = max(1, round(.12 / .03))
    active = np.convolve(active.astype(np.int32), np.ones(2 * pad + 1, dtype=np.int32), mode="same") > 0
    regions, begin = [], None
    for i, value in enumerate(active):
        if value and begin is None:
            begin = i
        if begin is not None and (not value or i == len(active) - 1):
            end = i if not value else i + 1
            start_s, end_s = begin * frame / sr, min(len(audio) / sr, end * frame / sr)
            if end_s - start_s >= .18:
                regions.append((start_s, end_s))
            begin = None
    if not regions:
        fail("no evidence-backed speech regions found; refusing an all-duration fallback")
    return regions

def atomize(regions, max_turn):
    atoms = []
    for start, end in regions:
        cursor = start
        while cursor < end - 1e-8:
            nxt = min(end, cursor + max_turn)
            atoms.append((cursor, nxt))
            cursor = nxt
    return atoms

def embeddings_for(audio, sr, atoms, work_dir):
    try:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
    except Exception as exc:
        fail("SpeechBrain and torch are required for evidence-based speaker identity: " + str(exc))
    try:
        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(work_dir / "speechbrain_ecapa"),
            run_opts={"device": "cpu"})
    except Exception as exc:
        fail("could not load SpeechBrain ECAPA model (install/cache it or enable its public model download): " + str(exc))
    values = []
    context = int(1.5 * sr)
    for start, end in atoms:
        center = int((start + end) * .5 * sr)
        left, right = center - context // 2, center + context // 2
        chunk = audio[max(0, left):min(len(audio), right)]
        if len(chunk) < context:
            chunk = np.pad(chunk, (max(0, -left), max(0, right - len(audio))))
        try:
            with torch.no_grad():
                vector = classifier.encode_batch(torch.from_numpy(chunk).unsqueeze(0)).squeeze().cpu().numpy()
            values.append(vector.astype(np.float64))
        except Exception as exc:
            fail("speaker embedding extraction failed: " + str(exc))
    matrix = np.vstack(values)
    norm = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norm, 1e-12)

def cluster_embeddings(matrix):
    """Use recording-derived silhouette evidence; return one cluster if no stable split exists."""
    n = len(matrix)
    if n == 1:
        return np.zeros(1, dtype=int), "one VAD window; no supported split"
    try:
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score
    except Exception as exc:
        fail("scikit-learn is required to cluster speaker embeddings: " + str(exc))
    best_labels, best_score, best_k = np.zeros(n, dtype=int), -1.0, 1
    # Cosine geometry is appropriate for normalized ECAPA embeddings.
    for k in range(2, min(8, n - 1) + 1):
        try:
            try:
                labels = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(matrix)
            except TypeError:  # older sklearn
                labels = AgglomerativeClustering(n_clusters=k, affinity="cosine", linkage="average").fit_predict(matrix)
            if len(set(labels)) < 2:
                continue
            score = float(silhouette_score(matrix, labels, metric="cosine"))
            if score > best_score:
                best_labels, best_score, best_k = labels, score, k
        except Exception:
            continue
    # A weak or negative separation is not evidence for splitting a voice.
    if best_score < .12:
        return np.zeros(n, dtype=int), "no stable multi-speaker embedding separation (best silhouette %.3f)" % best_score
    return best_labels, "%d clusters selected by cosine silhouette %.3f" % (best_k, best_score)

def make_turns(atoms, labels):
    # Relabel in first-occurrence order for stable spk00/SPK_00 mapping.
    mapping, next_id, out = {}, 0, []
    for (start, end), raw in zip(atoms, labels):
        raw = int(raw)
        if raw not in mapping:
            mapping[raw] = next_id; next_id += 1
        label = "spk%02d" % mapping[raw]
        if out and out[-1][2] == label and abs(out[-1][1] - start) < 1e-6:
            out[-1] = (out[-1][0], end, label)
        else:
            out.append((start, end, label))
    return out

def load_asr(model_name, language):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        def transcribe(samples):
            segments, _ = model.transcribe(samples, language=language, vad_filter=False, beam_size=5, condition_on_previous_text=False)
            return " ".join(s.text.strip() for s in segments).strip()
        return transcribe, "faster-whisper", "faster-whisper WhisperModel(%s)" % model_name
    except ImportError:
        pass
    except Exception as exc:
        fail("faster-whisper was found but its model could not load: " + str(exc))
    try:
        import whisper
        model = whisper.load_model(model_name)
        def transcribe(samples):
            result = model.transcribe(samples, language=language, fp16=False, condition_on_previous_text=False)
            return str(result.get("text", "")).strip()
        return transcribe, "openai-whisper", "openai-whisper model %s" % model_name
    except ImportError:
        fail("no ASR backend: install/cache faster-whisper or openai-whisper")
    except Exception as exc:
        fail("openai-whisper model could not load: " + str(exc))

def ass_time(seconds, end=False):
    # Quantize output to ASS centiseconds while preserving a positive encoded cue duration.
    cs = int(math.ceil(seconds * 100 - 1e-9) if end else math.floor(seconds * 100 + 1e-9))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, c)

def safe_ass_text(text):
    text = " ".join(text.replace("\n", " ").replace("\r", " ").split())
    return text.replace("{", "(").replace("}", ")")

def run(cfg):
    required = ["input_video", "rttm_path", "subtitles_path", "report_path"]
    if any(not cfg.get(k) for k in required):
        fail("missing required input field(s): " + ", ".join(k for k in required if not cfg.get(k)))
    video = Path(cfg["input_video"])
    if not video.is_file():
        fail("input video does not exist: " + str(video))
    paths = {k: Path(cfg[k]) for k in ["rttm_path", "subtitles_path", "report_path"]}
    for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(cfg.get("work_dir") or (paths["report_path"].parent / ".diarization_work")); work.mkdir(parents=True, exist_ok=True)
    max_turn = float(cfg.get("max_turn_sec", 1.5))
    if max_turn <= 0: fail("max_turn_sec must be positive")
    wav = work / "input_16k_mono.wav"
    audio, duration, sr = extract_wav(video, wav)
    regions = vad_regions(audio, sr)
    atoms = atomize(regions, max_turn)
    matrix = embeddings_for(audio, sr, atoms, work)
    labels, clustering_note = cluster_embeddings(matrix)
    turns = make_turns(atoms, labels)
    transcribe, asr_library, asr_tool = load_asr(str(cfg.get("asr_model", "base")), cfg.get("language"))
    texts, missing = [], 0
    for start, end, _ in turns:
        text = safe_ass_text(transcribe(audio[int(start * sr):int(end * sr)]))
        if not text:
            text, missing = "[untranscribed]", missing + 1
        texts.append(text)
    file_id = str(cfg.get("file_id", "input"))
    with paths["rttm_path"].open("w", encoding="utf-8") as f:
        for start, end, label in turns:
            f.write("SPEAKER %s 1 %.6f %.6f <NA> <NA> %s <NA> <NA>\n" % (file_id, start, end-start, label))
    header = "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    with paths["subtitles_path"].open("w", encoding="utf-8") as f:
        f.write(header)
        for (start, end, label), text in zip(turns, texts):
            st, et = ass_time(start), ass_time(end, True)
            if et <= st: et = ass_time(start + .01, True)
            speaker = "SPEAKER_" + label[3:]
            f.write("Dialogue: 0,%s,%s,Default,,0,0,0,,%s: %s\n" % (st, et, speaker, text))
    speech_time = sum(end - start for start, end, _ in turns)
    libraries = ["numpy", "torch", "speechbrain", "scikit-learn", asr_library]
    notes = "Acoustic VAD regions were diarized before ASR. " + clustering_note + "."
    if missing: notes += " %d acoustically detected turn(s) produced no ASR text and are explicitly marked [untranscribed]." % missing
    report = {"num_speakers_pred": len({x[2] for x in turns}), "total_speech_time_sec": round(speech_time, 6), "audio_duration_sec": round(duration, 6), "steps_completed": ["audio_extraction", "acoustic_speech_detection", "speaker_embedding_clustering", "transcription", "subtitle_generation"], "commands_used": ["ffmpeg", "python3"], "libraries_used": libraries, "tools_used": {"audio_extraction": "ffmpeg 16 kHz mono PCM WAV", "speech_detection": "adaptive acoustic energy VAD", "diarization": "SpeechBrain ECAPA embeddings with cosine agglomerative clustering", "transcription": asr_tool, "subtitle_generation": "ASS centisecond writer"}, "notes": notes}
    paths["report_path"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    check = validate(str(paths["rttm_path"]), str(paths["subtitles_path"]), str(paths["report_path"]))
    if not check["valid"]: fail("post-write artifact validation failed: " + "; ".join(check["errors"]))
    report["steps_completed"].append("artifact_validation")
    paths["report_path"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "outputs": {k: str(v) for k, v in paths.items()}, "validation": check}

def main():
    try:
        cfg = json.load(sys.stdin)
        # Third-party model loaders sometimes print progress; reserve stdout for JSON only.
        with contextlib.redirect_stdout(sys.stderr):
            result = run(cfg)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
