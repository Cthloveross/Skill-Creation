#!/usr/bin/env python3
"""JSON-stdin video diarization entrypoint; writes RTTM, ASS, and report JSON."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import wave
from collections import defaultdict
from pathlib import Path


def run(command, label, used_commands):
    """Run a command, recording only commands which succeeded."""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        raise RuntimeError(f"{label} failed: {detail}")
    used_commands.append(command[0])
    return result.stdout


def duration_of(path, used_commands):
    output = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)], "ffprobe", used_commands)
    duration = float(output.strip())
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("input has no finite positive duration")
    return duration


def extract_audio(video, wav_path, used_commands):
    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(wav_path)],
        "audio extraction", used_commands)


def merge_intervals(intervals, gap=0.22, minimum=0.18):
    out = []
    for start, end in sorted(intervals):
        start, end = max(0.0, float(start)), float(end)
        if end <= start:
            continue
        if out and start <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return [(a, b) for a, b in out if b - a >= minimum]


def energy_vad(wav_path, audio_duration):
    """Conservative adaptive 30 ms RMS VAD, returning speech rather than all audio."""
    with wave.open(str(wav_path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise RuntimeError("extracted WAV is not 16-bit mono PCM")
        rate = handle.getframerate()
        payload = handle.readframes(handle.getnframes())
    frame_samples = max(1, int(rate * 0.03))
    import array
    samples = array.array("h")
    samples.frombytes(payload)
    if sys.byteorder != "little":
        samples.byteswap()
    rms = []
    for i in range(0, len(samples), frame_samples):
        part = samples[i:i + frame_samples]
        if not part:
            continue
        rms.append(math.sqrt(sum(x * x for x in part) / len(part)))
    if not rms:
        return []
    ordered = sorted(rms)
    def q(f):
        return ordered[min(len(ordered) - 1, int(f * (len(ordered) - 1)))]
    # The noise floor and upper-energy distribution are measured from this recording.
    threshold = max(25.0, q(0.15) * 2.4, q(0.90) * 0.075)
    active = [x >= threshold for x in rms]
    # Fill short inactive holes and discard isolated active flickers.
    hole = max(1, round(0.18 / 0.03))
    for i in range(len(active)):
        if not active[i]:
            left = any(active[max(0, i - hole):i])
            right = any(active[i + 1:min(len(active), i + hole + 1)])
            if left and right:
                active[i] = True
    intervals, begin = [], None
    for i, is_active in enumerate(active + [False]):
        if is_active and begin is None:
            begin = i * 0.03
        elif not is_active and begin is not None:
            intervals.append((begin, min(audio_duration, i * 0.03)))
            begin = None
    return merge_intervals(intervals)


def diarize_pyannote(wav_path, model_name, notes, libraries):
    try:
        from pyannote.audio import Pipeline
        libraries.append("pyannote.audio")
    except Exception as exc:
        notes.append(f"pyannote.audio unavailable: {type(exc).__name__}")
        return None
    try:
        token = os.environ.get("HF_TOKEN")
        try:
            pipeline = Pipeline.from_pretrained(model_name, token=token)
        except TypeError:
            pipeline = Pipeline.from_pretrained(model_name, use_auth_token=token)
        annotation = pipeline(str(wav_path))
        raw = []
        for turn, _, label in annotation.itertracks(yield_label=True):
            if turn.end > turn.start:
                raw.append((float(turn.start), float(turn.end), str(label)))
        if not raw:
            raise RuntimeError("pipeline returned no positive speech turns")
        return raw, f"pyannote.audio Pipeline({model_name})"
    except Exception as exc:
        notes.append(f"pyannote diarization did not complete: {type(exc).__name__}: {exc}")
        return None


def cluster_embeddings(vectors, notes):
    """Use recording-specific linkage gap selection; returns zero-based cluster IDs."""
    if len(vectors) == 1:
        return [0], "single speech interval"
    try:
        import numpy as np
        from scipy.cluster.hierarchy import linkage, fcluster
        matrix = np.asarray(vectors, dtype=float)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-12)
        linkage_matrix = linkage(matrix, method="average", metric="cosine")
        distances = linkage_matrix[:, 2]
        # Cut only at a pronounced observed merge-distance discontinuity. Otherwise
        # retaining one cluster avoids inventing speakers from weak evidence.
        gaps = [distances[i + 1] - distances[i] for i in range(len(distances) - 1)]
        if not gaps or max(gaps) <= max(0.025, statistics.median(distances) * 0.65):
            return [0] * len(vectors), "no pronounced embedding linkage gap"
        cut_index = max(range(len(gaps)), key=lambda i: gaps[i])
        threshold = (distances[cut_index] + distances[cut_index + 1]) / 2.0
        labels = fcluster(linkage_matrix, t=float(threshold), criterion="distance")
        return [int(x) - 1 for x in labels], f"average cosine linkage; data-derived cut {threshold:.4f}"
    except Exception as exc:
        notes.append(f"embedding clustering failed: {type(exc).__name__}: {exc}")
        return [0] * len(vectors), "clustering unavailable; one cluster"


def diarize_speechbrain(wav_path, speech, notes, libraries):
    if not speech:
        return None
    try:
        import torch
        import torchaudio
        from speechbrain.inference.speaker import EncoderClassifier
        libraries.extend(["speechbrain", "torch", "torchaudio"])
    except Exception as exc:
        notes.append(f"SpeechBrain unavailable: {type(exc).__name__}")
        return None
    try:
        classifier = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")
        signal, sr = torchaudio.load(str(wav_path))
        if sr != 16000:
            raise RuntimeError(f"unexpected extracted sample rate {sr}")
        vectors = []
        # Keep VAD timing but supply short turns with neighboring acoustic context.
        for start, end in speech:
            center = (start + end) / 2.0
            a = max(0.0, min(start, center - 0.85))
            b = min(signal.shape[1] / sr, max(end, center + 0.85))
            chunk = signal[:, int(a * sr):max(int(b * sr), int(a * sr) + 1)]
            with torch.no_grad():
                emb = classifier.encode_batch(chunk).squeeze().detach().cpu().tolist()
            vectors.append(emb)
        labels, selection = cluster_embeddings(vectors, notes)
        return [(a, b, f"cluster_{c}") for (a, b), c in zip(speech, labels)], "speechbrain ECAPA; " + selection
    except Exception as exc:
        notes.append(f"SpeechBrain diarization did not complete: {type(exc).__name__}: {exc}")
        return None


def normalize_labels(raw_turns):
    first_seen, mapping, turns = [], {}, []
    for start, end, raw in sorted(raw_turns, key=lambda x: (x[0], x[1], x[2])):
        if raw not in mapping:
            mapping[raw] = f"spk{len(first_seen):02d}"
            first_seen.append(raw)
        turns.append((max(0.0, start), end, mapping[raw]))
    return [(a, b, s) for a, b, s in turns if b > a]


def transcribe(wav_path, model_name, notes, libraries):
    try:
        from faster_whisper import WhisperModel
        libraries.append("faster-whisper")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(wav_path), vad_filter=False)
        result = [(float(x.start), float(x.end), x.text.strip()) for x in segments if x.text.strip() and x.end > x.start]
        if not result:
            raise RuntimeError("ASR returned no nonempty segments")
        return result, f"faster-whisper {model_name} (cpu int8)"
    except ImportError:
        pass
    except Exception as exc:
        notes.append(f"faster-whisper did not complete: {type(exc).__name__}: {exc}")
    try:
        import whisper
        libraries.append("openai-whisper")
        model = whisper.load_model(model_name)
        answer = model.transcribe(str(wav_path), fp16=False, verbose=False)
        result = [(float(x["start"]), float(x["end"]), x["text"].strip()) for x in answer.get("segments", [])
                  if x.get("text", "").strip() and float(x["end"]) > float(x["start"])]
        if not result:
            raise RuntimeError("ASR returned no nonempty segments")
        return result, f"openai-whisper {model_name} (cpu fp32)"
    except Exception as exc:
        raise RuntimeError("no usable ASR backend; install faster-whisper or openai-whisper: " + str(exc))


def overlap(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def text_for_turns(turns, asr_segments):
    assigned = defaultdict(list)
    for start, end, text in asr_segments:
        candidates = [(overlap(start, end, a, b), index) for index, (a, b, _s) in enumerate(turns)]
        score, index = max(candidates, default=(0.0, None))
        if index is not None and score > 0:
            assigned[index].append(text)
    return {i: " ".join(parts).strip() for i, parts in assigned.items()}


def ass_time(value):
    # Round to centiseconds, carry correctly, and avoid an invalid 60-second field.
    cs = max(0, int(round(value * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cc = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def ass_safe(text):
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N").strip()


def write_rttm(path, file_id, turns):
    with open(path, "w", encoding="utf-8") as out:
        for start, end, speaker in turns:
            out.write(f"SPEAKER {file_id} 1 {start:.6f} {end-start:.6f} <NA> <NA> {speaker} <NA> <NA>\n")


def write_ass(path, turns, turn_text):
    header = """[Script Info]\nScriptType: v4.00+\nTitle: Diarized subtitles\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,30,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    with open(path, "w", encoding="utf-8") as out:
        out.write(header)
        for i, (start, end, speaker) in enumerate(turns):
            text = turn_text.get(i, "")
            if not text:
                continue
            label = "SPEAKER_" + speaker[3:]
            cue_end = max(end, start + 0.01)
            out.write(f"Dialogue: 0,{ass_time(start)},{ass_time(cue_end)},Default,,0,0,0,,{label}: {ass_safe(text)}\n")


def parse_rttm(path):
    turns = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 10 or fields[0] != "SPEAKER":
            raise RuntimeError("RTTM line is not a ten-field SPEAKER record")
        start, duration = float(fields[3]), float(fields[4])
        if start < 0 or duration <= 0 or not math.isfinite(start + duration):
            raise RuntimeError("RTTM timing is invalid")
        turns.append((start, duration, fields[7]))
    if not turns:
        raise RuntimeError("RTTM contains no speech turns")
    return turns


def validate(rttm_path, ass_path, report_path):
    turns = parse_rttm(rttm_path)
    speaker_count = len({x[2] for x in turns})
    total = sum(x[1] for x in turns)
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    for key in ("num_speakers_pred", "total_speech_time_sec", "audio_duration_sec", "steps_completed", "commands_used", "libraries_used", "tools_used", "notes"):
        if key not in report:
            raise RuntimeError(f"report missing required key {key}")
    if report["num_speakers_pred"] != speaker_count or abs(report["total_speech_time_sec"] - total) > 1e-5:
        raise RuntimeError("report summary does not match RTTM")
    for line in Path(ass_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            if len(fields) != 10 or not re.match(r"^SPEAKER_\d\d: ", fields[9]):
                raise RuntimeError("ASS dialogue lacks required speaker prefix")


def main(config):
    video = Path(config.get("input_video", "/root/input.mp4"))
    rttm_path = Path(config.get("rttm_output", "/root/diarization.rttm"))
    ass_path = Path(config.get("ass_output", "/root/subtitles.ass"))
    report_path = Path(config.get("report_output", "/root/report.json"))
    file_id = str(config.get("file_id", video.stem or "input"))
    asr_model = str(config.get("asr_model", "base"))
    pyannote_model = str(config.get("pyannote_model", "pyannote/speaker-diarization-3.1"))
    if not video.is_file():
        raise RuntimeError(f"input video is absent: {video}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    for path in (rttm_path, ass_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    used_commands, libraries, notes = [], [], []
    audio_duration = duration_of(video, used_commands)
    with tempfile.TemporaryDirectory(prefix="diarized-video-") as temporary:
        wav_path = Path(temporary) / "audio_16k_mono.wav"
        extract_audio(video, wav_path, used_commands)
        speech = energy_vad(wav_path, audio_duration)
        if not speech:
            raise RuntimeError("adaptive VAD found no speech; refusing an all-duration fallback")
        result = diarize_pyannote(wav_path, pyannote_model, notes, libraries)
        if result is None:
            result = diarize_speechbrain(wav_path, speech, notes, libraries)
        if result is None:
            raw_turns = [(a, b, "fallback_single_speaker") for a, b in speech]
            diarization_tool = "adaptive energy VAD with one documented fallback speaker"
            notes.append("No usable speaker embedding/diarization model completed; speaker identity is fallback single-speaker over VAD speech intervals only.")
        else:
            raw_turns, diarization_tool = result
        turns = normalize_labels(raw_turns)
        if not turns:
            raise RuntimeError("diarization returned no valid turns")
        transcript, asr_tool = transcribe(wav_path, asr_model, notes, libraries)
    turn_text = text_for_turns(turns, transcript)
    write_rttm(rttm_path, file_id, turns)
    write_ass(ass_path, turns, turn_text)
    rttm_turns = parse_rttm(rttm_path)
    report = {
        "num_speakers_pred": len({x[2] for x in rttm_turns}),
        "total_speech_time_sec": round(sum(x[1] for x in rttm_turns), 6),
        "audio_duration_sec": round(audio_duration, 6),
        "steps_completed": ["audio_extraction", "speech_activity_detection", "diarization", "transcription", "subtitle_generation", "artifact_validation"],
        "commands_used": list(dict.fromkeys(used_commands + ["python3"])),
        "libraries_used": list(dict.fromkeys(libraries)),
        "tools_used": {
            "audio_extraction": "ffmpeg PCM s16le, 16 kHz, mono",
            "speech_activity_detection": "adaptive RMS energy VAD on extracted WAV",
            "diarization": diarization_tool,
            "transcription": asr_tool,
            "subtitle_alignment": "maximum positive temporal overlap of ASR segments to diarization turns"
        },
        "notes": " ".join(notes) if notes else "All selected components completed without recorded fallback."
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validate(rttm_path, ass_path, report_path)
    return {"ok": True, "rttm": str(rttm_path), "ass": str(ass_path), "report": str(report_path),
            "num_speakers_pred": report["num_speakers_pred"], "total_speech_time_sec": report["total_speech_time_sec"]}


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise RuntimeError("stdin must contain a JSON object")
        print(json.dumps(main(config), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stdout)
        sys.exit(1)
