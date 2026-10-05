#!/usr/bin/env python3
"""Build a normalized, timing-locked dub from externally synthesized WAVs."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TC = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")

def run(args, capture=True):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)

def need_bins():
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            raise RuntimeError(name + " is not on PATH")

def sec(parts):
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000.0

def parse_srt(path, require_time=True):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [x.strip() for x in block.splitlines()]
        ti = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if ti is None:
            raise ValueError("SRT cue lacks timing: " + str(path))
        match = TC.match(lines[ti])
        if require_time and not match:
            raise ValueError("invalid SRT time range: " + lines[ti])
        text = " ".join(x for x in lines[ti + 1:] if x).strip()
        if not text:
            raise ValueError("empty subtitle text in " + str(path))
        cue = {"text": text}
        if match:
            cue.update(start=sec(match.groups()[:4]), end=sec(match.groups()[4:]))
            if cue["end"] <= cue["start"]:
                raise ValueError("nonpositive subtitle window")
        cues.append(cue)
    return cues

def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    value = float(json.loads(p.stdout)["format"]["duration"])
    if value <= 0:
        raise ValueError("nonpositive duration for " + str(path))
    return value

def atempo_chain(speed):
    # atempo permits 0.5..2.0. Factor it into valid stages without changing requested speed.
    factors = []
    while speed > 2.0:
        factors.append(2.0); speed /= 2.0
    while speed < 0.5:
        factors.append(0.5); speed /= 0.5
    factors.append(speed)
    return ",".join("atempo=%.12f" % x for x in factors)

def loudnorm_measure(path):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
             "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    chunks = re.findall(r"\{\s*\"input_i\".*?\}", p.stderr, flags=re.S)
    if not chunks:
        raise RuntimeError("could not parse loudnorm measurement")
    return json.loads(chunks[-1])

def ebur128(path):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    vals = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d*)?|inf))\s*LUFS", p.stderr, flags=re.I)
    if not vals or vals[-1].lower() == "-inf":
        raise RuntimeError("could not measure finite integrated LUFS")
    return float(vals[-1])

def raw_files(cfg, count):
    if cfg.get("raw_wavs"):
        result = [Path(x) for x in cfg["raw_wavs"]]
    else:
        d = Path(cfg["raw_wav_dir"])
        result = [d / ("raw_%d.wav" % i) for i in range(count)]
    if len(result) != count or any(not x.is_file() for x in result):
        raise ValueError("raw WAV files must exist and exactly match SRT cue count")
    return result

def main(c):
    need_bins()
    required = ("video", "segments_srt", "source_srt", "target_srt", "source_language", "target_language", "output_dir")
    for key in required:
        if not c.get(key): raise ValueError("missing " + key)
    windows, source, target = parse_srt(c["segments_srt"]), parse_srt(c["source_srt"]), parse_srt(c["target_srt"])
    if not (len(windows) == len(source) == len(target)):
        raise ValueError("segments, source, and reference target SRT cue counts must match")
    raws = raw_files(c, len(windows))
    video_duration = probe_duration(c["video"])
    out = Path(c["output_dir"]); out.mkdir(parents=True, exist_ok=True)
    segment_out = out / "tts_segments"; segment_out.mkdir(exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dub-build-"))
    try:
        adjusted = []
        reports = []
        for i, (window, src, tgt, raw) in enumerate(zip(windows, source, target, raws)):
            if window["end"] > video_duration + .05:
                raise ValueError("speech window exceeds video duration")
            raw_duration = probe_duration(raw)
            duration = window["end"] - window["start"]
            # atempo is speed: raw duration divided by desired duration.
            filt = atempo_chain(raw_duration / duration) + ",aresample=48000,apad,atrim=duration=%.9f" % duration
            adj = temp / ("adjusted_%d.wav" % i)
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", filt,
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(adj)])
            adjusted.append(adj)
            reports.append({"window_start_sec": window["start"], "window_end_sec": window["end"],
                            "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                            "source_text": src["text"], "target_text": tgt["text"],
                            "window_duration_sec": duration, "tts_duration_sec": raw_duration,
                            "drift_sec": 0.0, "duration_control": "rate_adjust"})
        # Delay each exact-duration clip onto a common silent timeline then mix it.
        args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for a in adjusted: args += ["-i", str(a)]
        chains = []
        labels = []
        for i, (a, win) in enumerate(zip(adjusted, windows)):
            label = "s%d" % i; labels.append("[%s]" % label)
            chains.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" % (i, round(win["start"] * 1000), video_duration, label))
        chains.append("%samix=inputs=%d:duration=longest,atrim=duration=%.9f,aresample=48000[m]" % ("".join(labels), len(labels), video_duration))
        premix = temp / "premix.wav"
        args += ["-filter_complex", ";".join(chains), "-map", "[m]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(premix)]
        run(args)
        measured = loudnorm_measure(premix)
        fields = ["measured_I", "measured_LRA", "measured_TP", "measured_thresh", "offset"]
        params = ":".join("%s=%s" % (k, measured[k]) for k in fields)
        finalwav = temp / "final_mix.wav"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(premix), "-af",
             "loudnorm=I=-23:LRA=7:TP=-2:%s:linear=true" % params, "-ar", "48000", "-ac", "1",
             "-c:a", "pcm_s24le", str(finalwav)])
        # Export window WAVs from final-gain audio, not unnormalized intermediates.
        for i, win in enumerate(windows):
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(finalwav), "-af",
                 "atrim=start=%.9f:end=%.9f,asetpts=PTS-STARTPTS" % (win["start"], win["end"]),
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(segment_out / ("seg_%d.wav" % i))])
        dubbed = out / "dubbed.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(c["video"]), "-i", str(finalwav),
             "-map", "0:v?", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
             "-ar", "48000", "-ac", "1", "-t", "%.9f" % video_duration, str(dubbed)])
        delivered_lufs = ebur128(dubbed)
        report = {"source_language": str(c["source_language"]).strip(), "target_language": str(c["target_language"]).strip(),
                  "audio_sample_rate_hz": 48000, "audio_channels": 1,
                  "original_duration_sec": video_duration, "new_duration_sec": probe_duration(dubbed),
                  "measured_lufs": delivered_lufs, "speech_segments": reports}
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(out / "report.json"), "segment_dir": str(segment_out), "measured_lufs": delivered_lufs}
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
