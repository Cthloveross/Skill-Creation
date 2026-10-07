#!/usr/bin/env python3
"""JSON stdin {video, report} -> JSON validation result."""
import json, subprocess, sys
from pathlib import Path

def probe(video):
    p=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",video],capture_output=True,text=True)
    if p.returncode: raise ValueError("ffprobe failed: "+p.stderr[-800:])
    return json.loads(p.stdout)

def main(c):
    video,report=Path(c["video"]),Path(c["report"])
    if not video.is_file() or video.stat().st_size==0: raise ValueError("missing or empty video")
    if not report.is_file(): raise ValueError("missing report")
    r=json.loads(report.read_text(encoding="utf-8"))
    required={"source_language","target_language","audio_sample_rate_hz","audio_channels","original_duration_sec","new_duration_sec","measured_lufs","speech_segments"}
    missing=required-set(r)
    if missing: raise ValueError("report missing fields: "+", ".join(sorted(missing)))
    if not isinstance(r["source_language"],str) or len(r["source_language"])!=2: raise ValueError("source_language is not ISO-639-1 shaped")
    if not isinstance(r["target_language"],str) or len(r["target_language"])!=2: raise ValueError("target_language is not ISO-639-1 shaped")
    if r["audio_sample_rate_hz"]!=48000 or r["audio_channels"]!=1: raise ValueError("report does not declare 48 kHz mono")
    if abs(float(r["measured_lufs"])+23.0)>1.0: raise ValueError("final measured_lufs is not within 1 LU of -23")
    if not r["speech_segments"]: raise ValueError("report has no speech segments")
    for i,s in enumerate(r["speech_segments"]):
        fields={"window_start_sec","window_end_sec","placed_start_sec","placed_end_sec","source_text","target_text","window_duration_sec","tts_duration_sec","drift_sec","duration_control"}
        if fields-set(s): raise ValueError("segment %d misses required fields"%i)
        if abs(float(s["placed_start_sec"])-float(s["window_start_sec"]))>0.010001: raise ValueError("segment %d start misaligned"%i)
        if abs(float(s["drift_sec"]))>0.200001: raise ValueError("segment %d excessive drift"%i)
        if s["duration_control"] not in ("rate_adjust","pad_silence","trim"): raise ValueError("segment %d invalid duration_control"%i)
    d=probe(str(video)); audio=[s for s in d["streams"] if s.get("codec_type")=="audio"]; vids=[s for s in d["streams"] if s.get("codec_type")=="video"]
    if not vids: raise ValueError("output has no video stream")
    if not audio: raise ValueError("output has no audio stream")
    if int(audio[0].get("sample_rate",0))!=48000 or int(audio[0].get("channels",0))!=1: raise ValueError("output audio is not 48 kHz mono")
    dur=float(d.get("format",{}).get("duration",0));
    if dur<=0: raise ValueError("output duration is not positive")
    return {"ok":True,"duration_sec":dur,"segments":len(r["speech_segments"])}
if __name__=="__main__":
    try:
        x=json.load(sys.stdin)
        print(json.dumps(main(x)))
    except Exception as e:
        print(json.dumps({"ok":False,"error":str(e)})); sys.exit(1)
