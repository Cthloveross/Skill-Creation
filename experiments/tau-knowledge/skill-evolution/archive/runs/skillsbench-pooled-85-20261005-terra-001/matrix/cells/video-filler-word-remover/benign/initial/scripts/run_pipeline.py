#!/usr/bin/env python3
"""Run word-timed ASR, filler detection, annotations writing, and clip rendering.

Reads the schema documented in SKILL.md from stdin and emits a JSON run report.
No network use is implemented; model availability is a runtime prerequisite.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from detect_fillers import DEFAULT_FILLERS, detect


def fail(message, code=2):
    json.dump({"ok": False, "error": message}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    raise SystemExit(code)


def run_checked(command):
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    if completed.returncode:
        detail = completed.stderr.strip()[-2000:]
        raise RuntimeError("command failed (%s): %s" % (" ".join(command[:2]), detail))
    return completed.stdout


def probe(path):
    raw = run_checked(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                       "-of", "json", str(path)])
    data = json.loads(raw)
    duration = float(data.get("format", {}).get("duration", "nan"))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("input has no finite positive container duration")
    streams = data.get("streams", [])
    kinds = {stream.get("codec_type") for stream in streams}
    return duration, kinds, streams


def transcribe_faster_whisper(source, model_spec):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper package is unavailable") from exc
    model = WhisperModel(model_spec, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(source), word_timestamps=True, vad_filter=False)
    tokens = []
    for segment in segments:
        words = getattr(segment, "words", None)
        if words is None:
            raise RuntimeError("faster-whisper returned a segment without word timestamps")
        for word in words:
            tokens.append({"text": word.word, "start": word.start, "end": word.end})
    return tokens


def transcribe_whisper(source, model_spec):
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError("openai-whisper package is unavailable") from exc
    model = whisper.load_model(model_spec)
    result = model.transcribe(str(source), word_timestamps=True, fp16=False, verbose=False)
    tokens = []
    for segment in result.get("segments", []):
        words = segment.get("words")
        if words is None:
            raise RuntimeError("whisper returned a segment without word timestamps")
        for word in words:
            tokens.append({"text": word.get("word"), "start": word.get("start"),
                           "end": word.get("end")})
    return tokens


def obtain_tokens(source, backend, model_spec):
    if backend not in ("faster-whisper", "whisper", "auto"):
        raise ValueError("backend must be faster-whisper, whisper, or auto")
    choices = [backend] if backend != "auto" else ["faster-whisper", "whisper"]
    errors = []
    for choice in choices:
        try:
            if choice == "faster-whisper":
                return transcribe_faster_whisper(source, model_spec), choice
            return transcribe_whisper(source, model_spec), choice
        except Exception as exc:
            errors.append("%s: %s" % (choice, exc))
    raise RuntimeError("no requested ASR backend succeeded; " + " | ".join(errors))


def write_annotations(path, detections):
    # Required external schema deliberately contains only the requested keys.
    payload = [{"word": item["word"], "timestamp": item["timestamp"]} for item in detections]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n")
    # Validate the exact serialized artifact, not an in-memory approximation.
    with path.open(encoding="utf-8") as handle:
        reread = json.load(handle)
    if not isinstance(reread, list) or len(reread) != len(payload):
        raise RuntimeError("annotations serialization failed validation")
    for expected, actual in zip(payload, reread):
        if set(actual) != {"word", "timestamp"} or actual["word"] != expected["word"]:
            raise RuntimeError("annotations has invalid element schema")
        stamp = actual["timestamp"]
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            raise RuntimeError("annotations timestamp is invalid")
    return payload


def normalized_intervals(detections, duration, padding):
    intervals = []
    for item in detections:
        start = max(0.0, item["timestamp"] - padding)
        end = min(duration, item["end"] + padding)
        if not (math.isfinite(start) and math.isfinite(end) and end > start):
            raise RuntimeError("detection cannot form a valid in-bounds clip interval")
        intervals.append((start, end, item["word"]))
    intervals.sort(key=lambda row: (row[0], row[1], row[2]))
    return intervals


def render(source, output, intervals):
    if not intervals:
        raise RuntimeError("cannot render a filler-only video with zero detections")
    clauses = []
    joins = []
    for i, (start, end, _word) in enumerate(intervals):
        # Both source streams receive exactly the same trim boundaries and reset timestamps.
        clauses.append("[0:v]trim=start=%.9f:end=%.9f,setpts=PTS-STARTPTS[v%d]" % (start, end, i))
        clauses.append("[0:a]atrim=start=%.9f:end=%.9f,asetpts=PTS-STARTPTS[a%d]" % (start, end, i))
        joins.append("[v%d][a%d]" % (i, i))
    graph = ";".join(clauses + ["%sconcat=n=%d:v=1:a=1[vout][aout]" % ("".join(joins), len(intervals))])
    output.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-filter_complex", graph,
                 "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac",
                 "-movflags", "+faststart", str(output)])


def parse_request():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("stdin must contain a JSON object")
    source = Path(request.get("input", "/root/input.mp4"))
    annotations = Path(request.get("annotations", "/root/annotations.json"))
    output = Path(request.get("output", "/root/output.mp4"))
    if not source.is_file():
        raise ValueError("input video does not exist: %s" % source)
    model = request.get("model") or os.environ.get("ASR_MODEL")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required (or set ASR_MODEL) and must name a locally available ASR model")
    backend = request.get("backend", "auto")
    fillers = request.get("fillers", DEFAULT_FILLERS)
    padding = request.get("clip_padding", 0.0)
    if isinstance(padding, bool) or not isinstance(padding, (int, float)) or not math.isfinite(float(padding)) or padding < 0:
        raise ValueError("clip_padding must be a finite nonnegative number")
    return source, annotations, output, model, backend, fillers, float(padding)


def main():
    source, annotations_path, output_path, model, backend, fillers, padding = parse_request()
    duration, kinds, _streams = probe(source)
    if "audio" not in kinds or "video" not in kinds:
        raise RuntimeError("input must contain both audio and video streams")
    tokens, actual_backend = obtain_tokens(source, backend, model)
    detections = detect(tokens, fillers)
    annotation_payload = write_annotations(annotations_path, detections)
    if not detections:
        raise RuntimeError("ASR produced no declared filler detections; annotations was written as []")
    intervals = normalized_intervals(detections, duration, padding)
    render(source, output_path, intervals)
    out_duration, out_kinds, _out_streams = probe(output_path)
    if "audio" not in out_kinds or "video" not in out_kinds:
        raise RuntimeError("rendered output is missing audio or video")
    if not math.isfinite(out_duration) or out_duration < 0:
        raise RuntimeError("rendered output has invalid duration")
    json.dump({"ok": True, "backend": actual_backend, "input_duration": duration,
               "detections": len(annotation_payload), "annotations": str(annotations_path),
               "output": str(output_path), "output_duration": out_duration}, sys.stdout,
              ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
