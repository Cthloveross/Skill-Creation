#!/usr/bin/env python3
"""JSON-stdin entrypoint for word-timed filler annotation and video stitching."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from filler_matching import DEFAULT_FILLERS, coerce_words, find_fillers, padded_merged_intervals


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}), file=sys.stdout)
    raise SystemExit(code)


def command(args: list[str], *, text: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    if completed.returncode != 0:
        detail = completed.stderr[-2000:] if isinstance(completed.stderr, str) else "command failed"
        raise RuntimeError(f"command failed ({' '.join(args[:3])} ...): {detail.strip()}")
    return completed


def probe(path: str) -> dict[str, Any]:
    result = command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("ffprobe did not provide a usable container duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("input has no finite positive duration")
    kinds = {stream.get("codec_type") for stream in data.get("streams", [])}
    return {"duration": duration, "has_audio": "audio" in kinds, "has_video": "video" in kinds, "raw": data}


def extract_audio(video: str, wav: str) -> None:
    command(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav])


def faster_whisper_words(audio: str, model_name: str, language: str | None) -> list[dict[str, Any]]:
    from faster_whisper import WhisperModel  # type: ignore
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    kwargs: dict[str, Any] = {"word_timestamps": True, "vad_filter": False}
    if language:
        kwargs["language"] = language
    segments, _info = model.transcribe(audio, **kwargs)
    output: list[dict[str, Any]] = []
    for segment in segments:
        for word in (getattr(segment, "words", None) or []):
            if word.start is not None and word.end is not None:
                output.append({"word": word.word, "start": word.start, "end": word.end})
    return output


def openai_whisper_words(audio: str, model_name: str, language: str | None) -> list[dict[str, Any]]:
    import whisper  # type: ignore
    model = whisper.load_model(model_name)
    kwargs: dict[str, Any] = {"word_timestamps": True, "verbose": False}
    if language:
        kwargs["language"] = language
    result = model.transcribe(audio, **kwargs)
    output: list[dict[str, Any]] = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []) or []:
            if word.get("start") is not None and word.get("end") is not None:
                output.append({"word": word.get("word", ""), "start": word["start"], "end": word["end"]})
    return output


def transcribe_words(audio: str, backend: str, model: str, language: str | None) -> tuple[list[dict[str, Any]], str]:
    choices = [backend] if backend != "auto" else ["faster-whisper", "whisper"]
    errors: list[str] = []
    for choice in choices:
        try:
            if choice == "faster-whisper":
                values = faster_whisper_words(audio, model, language)
            elif choice == "whisper":
                values = openai_whisper_words(audio, model, language)
            else:
                raise ValueError("backend must be auto, faster-whisper, or whisper")
            words = coerce_words(values)
            if not words:
                raise RuntimeError("backend returned no usable word-level timestamps")
            return words, choice
        except Exception as exc:
            errors.append(f"{choice}: {exc}")
            if backend != "auto":
                break
    raise RuntimeError("No usable word-timestamp ASR backend. " + " | ".join(errors))


def write_annotations(path: str, matches: list[dict[str, Any]]) -> None:
    payload = [{"word": item["word"], "timestamp": item["timestamp"]} for item in matches]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def stitch(source: str, destination: str, intervals: list[tuple[float, float]]) -> None:
    filters: list[str] = []
    inputs: list[str] = []
    for index, (start, end) in enumerate(intervals):
        # Decimal literals are locale-independent and avoid shell interpolation.
        s, e = f"{start:.6f}", f"{end:.6f}"
        filters.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{index}]")
        inputs.extend([f"[v{index}]", f"[a{index}]"])
    filters.append(f"{''.join(inputs)}concat=n={len(intervals)}:v=1:a=1[vout][aout]")
    graph = ";".join(filters)
    command([
        "ffmpeg", "-y", "-v", "error", "-i", source, "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", destination,
    ])


def validate_annotations(path: str, allowed: set[str]) -> int:
    with open(path, encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, list):
        raise RuntimeError("annotations file is not an array")
    prior = -1.0
    for item in values:
        if not isinstance(item, dict) or set(item) != {"word", "timestamp"}:
            raise RuntimeError("annotation does not have exactly word and timestamp")
        timestamp = item["timestamp"]
        if item["word"] not in allowed or not isinstance(timestamp, (int, float)):
            raise RuntimeError("annotation has invalid filler or timestamp type")
        if not math.isfinite(float(timestamp)) or float(timestamp) < 0 or float(timestamp) < prior:
            raise RuntimeError("annotation timestamps are not chronological finite values")
        prior = float(timestamp)
    return len(values)


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin must contain one JSON object")
        annotation_path = str(config["annotations_path"])
        output_path = str(config["output_video"])
        source = str(config.get("input_video", ""))
        if not source:
            raise ValueError("input_video is required")
        if not Path(source).is_file():
            raise ValueError("input_video does not exist or is not a file")
        if not Path(annotation_path).parent.is_dir() or not Path(output_path).parent.is_dir():
            raise ValueError("output parent directory does not exist")
        source_info = probe(source)
        if not source_info["has_audio"] or not source_info["has_video"]:
            raise RuntimeError("input must contain both audio and video streams")
        padding = float(config.get("clip_padding_seconds", 0.12))
        max_gap = float(config.get("max_phrase_gap_seconds", 1.5))
        fillers = config.get("fillers", DEFAULT_FILLERS)
        if not isinstance(fillers, list):
            raise ValueError("fillers must be a JSON array of strings")

        if "words" in config:
            if not isinstance(config["words"], list):
                raise ValueError("words must be a JSON array")
            words = coerce_words(config["words"])
            backend_used = "supplied-word-timestamps"
        else:
            backend = str(config.get("backend", "auto"))
            language_value = config.get("language", "en")
            language = None if language_value is None else str(language_value)
            model = str(config.get("model", "small.en"))
            with tempfile.TemporaryDirectory(prefix="filler_asr_") as tempdir:
                audio = os.path.join(tempdir, "audio_16khz_mono.wav")
                extract_audio(source, audio)
                words, backend_used = transcribe_words(audio, backend, model, language)

        matches = find_fillers(words, fillers, max_gap)
        write_annotations(annotation_path, matches)
        count = validate_annotations(annotation_path, {str(x).casefold().strip() for x in fillers})
        if not matches:
            raise RuntimeError("no filler detections: annotations.json contains []; no nonempty output video can be stitched")
        intervals = padded_merged_intervals(matches, source_info["duration"], padding)
        if not intervals:
            raise RuntimeError("no valid clip intervals after clamping")
        stitch(source, output_path, intervals)
        output_info = probe(output_path)
        if not output_info["has_audio"] or not output_info["has_video"]:
            raise RuntimeError("output is missing an audio or video stream")
        # Ensure the encoded file can actually be decoded, not merely probed.
        command(["ffmpeg", "-v", "error", "-i", output_path, "-f", "null", "-"])
        print(json.dumps({
            "ok": True, "annotations_path": annotation_path, "output_video": output_path,
            "detections": count, "merged_clip_count": len(intervals),
            "input_duration_seconds": source_info["duration"],
            "output_duration_seconds": output_info["duration"], "asr_backend": backend_used,
        }, ensure_ascii=False))
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
