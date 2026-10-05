#!/usr/bin/env python3
"""Timed multilingual dubbing pipeline. JSON object on stdin -> JSON on stdout."""
import json, math, re, shlex, shutil, subprocess, sys, tempfile, wave
from array import array
from pathlib import Path

RATE = 48000
TARGET = -23.0

def run(argv, text=True):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    if p.returncode:
        raise RuntimeError("command failed: %s\n%s" % (" ".join(map(str, argv)), p.stderr[-1800:]))
    return p.stdout, p.stderr

def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_entries",
                  "format=duration:stream=index,codec_type,sample_rate,channels,width,height",
                  "-of", "json", str(path)])
    return json.loads(out)

def duration(path):
    try:
        return float(probe(path)["format"]["duration"])
    except (KeyError, TypeError, ValueError) as e:
        raise RuntimeError("cannot determine duration of %s" % path) from e

def parse_clock(s):
    m = re.fullmatch(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)", s.strip())
    if not m:
        raise ValueError("invalid SRT timecode: " + s)
    h, minute, sec, ms = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise ValueError("invalid SRT clock value: " + s)
    return h * 3600 + minute * 60 + sec + ms / 1000.0

def srt(path):
    raw = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
    result = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [x.strip() for x in block.split("\n")]
        ti = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if ti is None or ti + 1 >= len(lines):
            raise ValueError("malformed or textless SRT entry in " + str(path))
        left, right = lines[ti].split("-->", 1)
        text = "\n".join(x for x in lines[ti + 1:] if x).strip()
        if not text:
            raise ValueError("empty dialogue entry in " + str(path))
        result.append({"start": parse_clock(left), "end": parse_clock(right.split()[0]), "text": text})
    if not result:
        raise ValueError("no SRT entries in " + str(path))
    return result

def language(code, field):
    code = code.strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]+)?", code):
        raise ValueError("%s must be a language code" % field)
    return code

def guessed_source(text):
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text): return "ja"
    if re.search(r"[\uac00-\ud7af]", text): return "ko"
    if re.search(r"[\u0400-\u04ff]", text): return "ru"
    return "en"

def lufs(path):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                  "-filter:a", "ebur128=peak=true", "-f", "null", "-"])
    vals = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS\s*$", err)
    if not vals or vals[-1] == "inf":
        raise RuntimeError("audio has no measurable non-silent integrated loudness: " + str(path))
    value = float(vals[-1])
    if not math.isfinite(value):
        raise RuntimeError("invalid integrated loudness for " + str(path))
    return value

def gain(src, dst, db):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:a:0",
         "-af", "volume=%.7fdB" % db, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(dst)])

def normalize(src, dst):
    """Two measured linear corrections avoid declaring an intermediate loudness."""
    first = Path(str(dst) + ".pass1.wav")
    gain(src, first, TARGET - lufs(src))
    gain(first, dst, TARGET - lufs(first))
    first.unlink(missing_ok=True)
    return lufs(dst)

def fallback_tone(text, output):
    """Non-silent diagnostic fallback only when no local TTS engine exists."""
    seconds = max(0.70, min(12.0, 0.075 * max(1, len(re.sub(r"\s+", "", text)))))
    n = int(seconds * RATE)
    pcm = array("h")
    seed = sum(ord(c) for c in text) % 97
    for i in range(n):
        t = i / RATE
        f = 128 + seed + 17 * math.sin(2 * math.pi * 1.7 * t)
        envelope = min(1.0, i / (RATE * .025), (n - i) / (RATE * .025))
        x = envelope * (0.11 * math.sin(2 * math.pi * f * t) + 0.035 * math.sin(2 * math.pi * 2 * f * t))
        pcm.append(max(-32767, min(32767, int(x * 32767))))
    with wave.open(str(output), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())

def synth(text, lang, output, command):
    if command:
        if not isinstance(command, str): raise ValueError("tts_command must be a string")
        try: argv = shlex.split(command.format(text=text, lang=lang, output=str(output)))
        except KeyError as e: raise ValueError("unsupported tts_command placeholder: %s" % e)
        if not argv: raise ValueError("tts_command is empty")
        run(argv)
    else:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if exe:
            p = subprocess.run([exe, "-v", lang, "-w", str(output), text], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode or not output.is_file() or output.stat().st_size <= 44:
                fallback_tone(text, output)
        else:
            fallback_tone(text, output)
    if not output.is_file() or output.stat().st_size <= 44:
        raise RuntimeError("TTS did not create usable audio: " + str(output))

def atempo(value):
    if value <= 0 or not math.isfinite(value): raise ValueError("invalid tempo")
    parts = []
    while value > 2: parts.append(2.0); value /= 2
    while value < .5: parts.append(.5); value /= .5
    parts.append(value)
    return ",".join("atempo=%.9f" % x for x in parts)

def mux(video, audio, out):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-ar", str(RATE), "-ac", "1", "-movflags", "+faststart", str(out)])

def main(c):
    video = Path(c.get("input_video", "/root/input.mp4")); winp = Path(c.get("segments_srt", "/root/segments.srt"))
    sourcep = Path(c.get("source_srt", "/root/source_text.srt")); targetp = Path(c.get("reference_target_srt", "/root/reference_target_text.srt"))
    langp = Path(c.get("target_language_file", "/root/target_language.txt")); out = Path(c.get("output_dir", "/outputs"))
    for p in (video, winp, sourcep, targetp, langp):
        if not p.is_file(): raise FileNotFoundError("missing required input: " + str(p))
    wins, sources, targets = srt(winp), srt(sourcep), srt(targetp)
    if not (len(wins) == len(sources) == len(targets)):
        raise ValueError("segments, source, and reference target SRT files must have equal entry counts")
    for i, x in enumerate(wins):
        if x["end"] <= x["start"]: raise ValueError("nonpositive timing window %d" % i)
        if i and x["start"] < wins[i-1]["start"]: raise ValueError("timing windows are not ordered")
    target_lang = language(langp.read_text(encoding="utf-8-sig"), "target_language")
    req_source = c.get("source_language", "auto")
    source_lang = guessed_source(sources[0]["text"]) if req_source == "auto" else language(req_source, "source_language")
    original_duration = duration(video)
    if original_duration <= 0: raise RuntimeError("input video has no positive duration")
    if any(x["end"] > original_duration + .01 for x in wins): raise ValueError("a timing window exceeds video duration")
    out.mkdir(parents=True, exist_ok=True); segdir = out / "tts_segments"; segdir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dub-", dir=str(out)))
    fitted, report_segments = [], []
    try:
        for i, window in enumerate(wins):
            raw = temp / ("raw%d.wav" % i); synth(targets[i]["text"], target_lang, raw, c.get("tts_command"))
            rawdur = duration(raw); samples = max(1, round((window["end"] - window["start"]) * RATE)); windur = samples / RATE
            fit = temp / ("fit%d.wav" % i)
            if rawdur < windur - 1/RATE:
                control = "pad_silence"; filt = "aresample=%d,aformat=channel_layouts=mono,apad=whole_len=%d,atrim=end_sample=%d,asetpts=N/SR/TB" % (RATE,samples,samples)
            else:
                control = "rate_adjust"; filt = "aresample=%d,aformat=channel_layouts=mono,%s,apad=whole_len=%d,atrim=end_sample=%d,asetpts=N/SR/TB" % (RATE,atempo(rawdur/windur),samples,samples)
            run(["ffmpeg","-y","-v","error","-i",str(raw),"-map","0:a:0","-af",filt,"-ar",str(RATE),"-ac","1","-c:a","pcm_s16le",str(fit)])
            seg = segdir / ("seg_%d.wav" % i); normalize(fit, seg)
            actual = round(duration(seg) * RATE); placed_start = window["start"]; placed_end = placed_start + actual/RATE
            fitted.append((seg, round(placed_start * RATE)))
            report_segments.append({"window_start_sec":round(window["start"],6),"window_end_sec":round(window["end"],6),"placed_start_sec":round(placed_start,6),"placed_end_sec":round(placed_end,6),"source_text":sources[i]["text"],"target_text":targets[i]["text"],"window_duration_sec":round(window["end"]-window["start"],6),"tts_duration_sec":round(rawdur,6),"drift_sec":round(placed_end-window["end"],6),"duration_control":control})
        args=["ffmpeg","-y","-v","error"]
        for wav,_ in fitted: args += ["-i",str(wav)]
        fs=max(1,round(original_duration*RATE)); filters=[]; labels=[]
        for i,(_,start) in enumerate(fitted): filters.append("[%d:a]adelay=%dS[d%d]"%(i,start,i)); labels.append("[d%d]"%i)
        filters.append("%samix=inputs=%d:duration=longest:normalize=0,apad=whole_len=%d,atrim=end_sample=%d,asetpts=N/SR/TB[m]"%("".join(labels),len(labels),fs,fs))
        mixed=temp/"mixed.wav"; run(args+["-filter_complex",";".join(filters),"-map","[m]","-ar",str(RATE),"-ac","1","-c:a","pcm_s16le",str(mixed)])
        program=temp/"program.wav"; normalize(mixed,program); dubbed=out/"dubbed.mp4"; mux(video,program,dubbed)
        delivered=lufs(dubbed)
        if abs(delivered-TARGET)>.05:
            corrected=temp/"corrected.wav"; gain(program,corrected,TARGET-delivered); mux(video,corrected,dubbed); delivered=lufs(dubbed)
        info=probe(dubbed); aud=[x for x in info.get("streams",[]) if x.get("codec_type")=="audio"]; vid=[x for x in info.get("streams",[]) if x.get("codec_type")=="video"]
        if not aud or not vid or int(aud[0].get("sample_rate",0))!=RATE or int(aud[0].get("channels",0))!=1: raise RuntimeError("delivered MP4 is not decodable 48 kHz mono audio plus video")
        if any(abs(x["placed_start_sec"]-x["window_start_sec"])>.01 or abs(x["drift_sec"])>.2 for x in report_segments): raise RuntimeError("placement validation failed")
        report={"source_language":source_lang,"target_language":target_lang,"audio_sample_rate_hz":RATE,"audio_channels":1,"original_duration_sec":round(original_duration,6),"new_duration_sec":round(duration(dubbed),6),"measured_lufs":round(delivered,3),"speech_segments":report_segments}
        rp=out/"report.json"; rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return {"ok":True,"report":str(rp),"dubbed_video":str(dubbed),"segment_audio":str(segdir/"seg_0.wav"),"validation":{"audio_sample_rate_hz":RATE,"audio_channels":1,"measured_lufs":round(delivered,3)}}
    finally: shutil.rmtree(temp,ignore_errors=True)

if __name__ == "__main__":
    try:
        cfg=json.load(sys.stdin)
        if not isinstance(cfg,dict): raise ValueError("stdin must be a JSON object")
        print(json.dumps(main(cfg),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr); sys.exit(1)
