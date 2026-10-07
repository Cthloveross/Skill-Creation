#!/usr/bin/env python3
"""JSON stdin -> timed dubbing artifacts and JSON stdout.
Requires only stdlib directly; Kokoro/numpy are imported only for the optional backend.
"""
import json, os, re, sys, shutil, subprocess, tempfile, wave
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0
LANG_NAMES = {
    "english":"en", "american english":"en", "japanese":"ja", "french":"fr",
    "german":"de", "spanish":"es", "italian":"it", "portuguese":"pt",
    "korean":"ko", "chinese":"zh", "mandarin":"zh", "russian":"ru",
    "arabic":"ar", "hindi":"hi", "dutch":"nl", "polish":"pl", "turkish":"tr"
}
KOKORO_LANG = {"en":"a", "ja":"j", "zh":"z", "es":"e", "fr":"f", "hi":"h", "it":"i", "pt":"p"}
KOKORO_VOICE = {"en":"af_heart", "ja":"jf_alpha"}

class DubError(RuntimeError): pass

def run(args, text=False):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise DubError("command failed: %s\n%s" % (" ".join(map(str,args)), p.stderr[-1800:]))
    return p.stdout if text else p.stdout

def require_tool(name):
    if not shutil.which(name): raise DubError("required executable not found on PATH: " + name)

def probe(path, selector=None):
    cmd=["ffprobe","-v","error","-print_format","json","-show_format","-show_streams"]
    if selector: cmd += ["-select_streams", selector]
    cmd.append(str(path))
    try: return json.loads(run(cmd, True))
    except Exception as e: raise DubError("cannot probe %s: %s" % (path,e))

def media_duration(path, selector=None):
    d=probe(path, selector)
    streams=d.get("streams", [])
    for s in streams:
        try:
            if s.get("duration") not in (None,"N/A"): return float(s["duration"])
        except ValueError: pass
    try: return float(d["format"]["duration"])
    except Exception: raise DubError("duration unavailable for " + str(path))

def audio_props(path):
    d=probe(path, "a:0"); ss=d.get("streams",[])
    if not ss: raise DubError("no audio stream in " + str(path))
    s=ss[0]
    return int(s.get("sample_rate",0)), int(s.get("channels",0))

def parse_time(value):
    m=re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m: raise DubError("invalid SRT timecode: " + value)
    h,mi,se,ms=map(int,m.groups())
    if mi>=60 or se>=60: raise DubError("invalid SRT timecode: " + value)
    return h*3600+mi*60+se+ms/1000.0

def parse_srt(path):
    try: raw=Path(path).read_text(encoding="utf-8-sig").replace("\r\n","\n").replace("\r","\n")
    except OSError as e: raise DubError("cannot read SRT %s: %s"%(path,e))
    cues=[]
    for block in re.split(r"\n[ \t]*\n", raw.strip()):
        lines=[x.strip() for x in block.split("\n")]
        ti=next((i for i,x in enumerate(lines) if "-->" in x), None)
        if ti is None: continue
        parts=lines[ti].split("-->")
        if len(parts)!=2: raise DubError("malformed SRT timing line: "+lines[ti])
        start,end=parse_time(parts[0]),parse_time(parts[1].split()[0])
        text="\n".join(x for x in lines[ti+1:] if x).strip()
        if not text: raise DubError("SRT cue has empty text in " + str(path))
        if end<=start: raise DubError("SRT cue end is not after start in " + str(path))
        cues.append({"start":start,"end":end,"text":text})
    if not cues: raise DubError("no usable SRT cues in " + str(path))
    return cues

def matching_text(cues, idx, window, label):
    # Prefer a cue overlapping the timing window; ordinal matching is the fallback
    scored=[]
    for n,c in enumerate(cues):
        overlap=max(0.0,min(c["end"],window["end"])-max(c["start"],window["start"]))
        scored.append((overlap, -abs((c["start"]+c["end"])-(window["start"]+window["end"])), n))
    best=max(scored)
    if best[0]>0: return cues[best[2]]["text"]
    if idx<len(cues): return cues[idx]["text"]
    raise DubError("cannot match %s text to timing segment %d" % (label,idx))

def normalize_language(raw):
    v=raw.strip().lower().replace("_","-")
    if v in LANG_NAMES: return LANG_NAMES[v]
    if re.fullmatch(r"[a-z]{2}",v): return v
    # Allow locale declarations while reporting their standardized base language.
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}",v): return v[:2]
    raise DubError("target language must be an ISO 639-1 code or recognized name: " + raw.strip())

def write_pcm16(path, samples, sample_rate):
    import numpy as np
    x=np.asarray(samples,dtype=np.float32)
    if x.ndim==2:
        # Kokoro normally returns a 1-D mono waveform; safely downmix either layout.
        x=x.mean(axis=0 if x.shape[0] <= 8 else 1)
    x=np.clip(x.reshape(-1),-1.0,1.0)
    pcm=(x*32767.0).astype("<i2").tobytes()
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sample_rate)); w.writeframes(pcm)

def synth_kokoro(text, lang, output, voice=None):
    if lang not in KOKORO_LANG:
        raise DubError("Kokoro language mapping is unavailable for ISO language " + lang)
    try:
        import numpy as np
        from kokoro import KPipeline
        pipe=KPipeline(lang_code=KOKORO_LANG[lang])
        use_voice=voice or KOKORO_VOICE.get(lang, "af_heart")
        pieces=[]
        for item in pipe(text, voice=use_voice):
            # Current Kokoro returns (graphemes, phonemes, audio).
            pieces.append(np.asarray(item[-1], dtype=np.float32).reshape(-1))
        if not pieces: raise DubError("Kokoro returned no audio")
        write_pcm16(output, np.concatenate(pieces), 24000)
    except DubError: raise
    except Exception as e: raise DubError("Kokoro synthesis failed: " + str(e))

def synth_espeak(text, lang, output):
    exe=shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe: raise DubError("neither espeak-ng nor espeak is installed")
    run([exe,"-v",lang,"-w",str(output),text])
    if not Path(output).exists() or media_duration(output)<=0: raise DubError("espeak produced no usable audio")

def synth(text, lang, output, backend, voice):
    errors=[]
    choices=[backend] if backend!="auto" else ["kokoro","espeak"]
    for choice in choices:
        try:
            if choice=="kokoro": synth_kokoro(text,lang,output,voice)
            elif choice=="espeak": synth_espeak(text,lang,output)
            else: raise DubError("unknown tts_backend: "+choice)
            return choice
        except Exception as e:
            errors.append(choice+": "+str(e))
            if Path(output).exists(): Path(output).unlink()
    raise DubError("no TTS backend could synthesize this segment; " + " | ".join(errors))

def ff_duration(path): return media_duration(path, "a:0")

def render_segment(raw, rendered, raw_dur, window_dur):
    # atempo is requested only for overlong clips at <= 1.5x compression.
    if raw_dur <= window_dur:
        control="pad_silence"; filt="aresample=48000,apad,atrim=duration=%.9f" % window_dur
    elif raw_dur/window_dur <= 1.5:
        control="rate_adjust"; filt="aresample=48000,atempo=%.9f,apad,atrim=duration=%.9f" % (raw_dur/window_dur,window_dur)
    else:
        control="trim"; filt="aresample=48000,atrim=duration=%.9f" % window_dur
    run(["ffmpeg","-y","-v","error","-i",str(raw),"-af",filt,"-ar",str(RATE),"-ac","1","-c:a","pcm_s16le",str(rendered)])
    return control

def loudnorm_measure(src):
    # ffmpeg writes the print_format JSON to stderr, which is intentionally captured.
    p=subprocess.run(["ffmpeg","-v","info","-i",str(src),"-af",
        "loudnorm=I=-23:TP=-2:LRA=7:print_format=json","-f","null","-"], stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise DubError("loudnorm measurement failed: "+p.stderr[-1200:])
    matches=re.findall(r"\{\s*\"input_i\".*?\}",p.stderr,re.S)
    if not matches: raise DubError("ffmpeg loudnorm did not return measurement JSON")
    try: return json.loads(matches[-1])
    except Exception as e: raise DubError("cannot parse loudnorm measurement: "+str(e))

def normalize_loudness(src, dst):
    m=loudnorm_measure(src)
    needed=["input_i","input_lra","input_tp","input_thresh","target_offset"]
    if any(k not in m for k in needed): raise DubError("incomplete loudnorm measurement")
    filt=("loudnorm=I=-23:TP=-2:LRA=7:measured_I={input_i}:measured_LRA={input_lra}:"
          "measured_TP={input_tp}:measured_thresh={input_thresh}:offset={target_offset}:linear=true:print_format=summary").format(**m)
    run(["ffmpeg","-y","-v","error","-i",str(src),"-af",filt,"-ar",str(RATE),"-ac","1","-c:a","pcm_s16le",str(dst)])

def final_lufs(video):
    p=subprocess.run(["ffmpeg","-v","info","-i",str(video),"-map","0:a:0","-af","ebur128=peak=true","-f","null","-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise DubError("final ebur128 measurement failed: "+p.stderr[-1200:])
    vals=re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS",p.stderr)
    if not vals: raise DubError("could not locate integrated LUFS in ebur128 output")
    v=vals[-1]
    if v.lower()=="-inf": raise DubError("final audio has no measurable loudness")
    return float(v)

def main(cfg):
    for x in ("ffmpeg","ffprobe"): require_tool(x)
    required=["input_video","segments_srt","source_srt","reference_target_srt","target_language_file"]
    for k in required:
        if not cfg.get(k): raise DubError("missing required JSON field: "+k)
        if not Path(cfg[k]).is_file(): raise DubError("required input is not a file: "+str(cfg[k]))
    out=Path(cfg.get("output_dir","/outputs")); out.mkdir(parents=True,exist_ok=True)
    segout=out/"tts_segments"; segout.mkdir(parents=True,exist_ok=True)
    target=normalize_language(Path(cfg["target_language_file"]).read_text(encoding="utf-8-sig"))
    source=normalize_language(str(cfg.get("source_language","en")))
    windows=parse_srt(cfg["segments_srt"]); source_cues=parse_srt(cfg["source_srt"]); target_cues=parse_srt(cfg["reference_target_srt"])
    original=media_duration(cfg["input_video"],"v:0")
    if original<=0: raise DubError("input has no positive video duration")
    for w in windows:
        if w["start"] < 0 or w["end"] > original+0.010: raise DubError("speech window lies outside input video duration")
    backend=cfg.get("tts_backend","auto"); voice=cfg.get("kokoro_voice")
    if backend not in ("auto","kokoro","espeak"): raise DubError("tts_backend must be auto, kokoro, or espeak")
    temp=Path(tempfile.mkdtemp(prefix="dubbing-",dir=str(out)))
    reports=[]; used=[]
    try:
        for i,w in enumerate(windows):
            st=matching_text(source_cues,i,w,"source")
            tt=matching_text(target_cues,i,w,"reference target")
            raw=temp/("raw-%d.wav"%i); timed=temp/("timed-%d.wav"%i); final=segout/("seg_%d.wav"%i)
            used.append(synth(tt,target,raw,backend,voice))
            raw_dur=ff_duration(raw); win=w["end"]-w["start"]
            control=render_segment(raw,timed,raw_dur,win)
            normalize_loudness(timed,final)
            # Rendered clip is explicitly padded/trimmed to the full timing window.
            placed_start=w["start"]; placed_end=w["end"]
            reports.append({"window_start_sec":round(w["start"],6),"window_end_sec":round(w["end"],6),
                "placed_start_sec":round(placed_start,6),"placed_end_sec":round(placed_end,6),
                "source_text":st,"target_text":tt,"window_duration_sec":round(win,6),
                "tts_duration_sec":round(raw_dur,6),"drift_sec":round(placed_end-w["end"],6),"duration_control":control})
        timeline=temp/"timeline.wav"
        inputs=["ffmpeg","-y","-v","error","-f","lavfi","-i","anullsrc=r=48000:cl=mono"]
        for i in range(len(windows)): inputs += ["-i",str(segout/("seg_%d.wav"%i))]
        labels=[]
        for i,w in enumerate(windows):
            # S-suffix delay is in samples and avoids millisecond rounding.
            samples=round(w["start"]*RATE); labels.append("[d%d]"%i)
            # Build a separate graph clause below.
        clauses=["[%d:a]adelay=%dS:all=1[d%d]"%(i+1,round(w["start"]*RATE),i) for i,w in enumerate(windows)]
        clauses.append("[0:a]"+"".join(labels)+"amix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f[a]"%(len(windows)+1,original))
        inputs += ["-filter_complex",";".join(clauses),"-map","[a]","-t","%.9f"%original,"-ar",str(RATE),"-ac","1","-c:a","pcm_s16le",str(timeline)]
        run(inputs)
        normalized=temp/"final-normalized.wav"; normalize_loudness(timeline,normalized)
        dubbed=out/"dubbed.mp4"
        run(["ffmpeg","-y","-v","error","-i",str(cfg["input_video"]),"-i",str(normalized),"-map","0:v?","-map","1:a:0","-c:v","copy","-c:a","aac","-ar",str(RATE),"-ac","1","-shortest","-movflags","+faststart",str(dubbed)])
        sr,ch=audio_props(dubbed)
        if (sr,ch)!=(RATE,1): raise DubError("final mux did not produce 48000 Hz mono audio")
        newdur=media_duration(dubbed,"v:0"); lufs=final_lufs(dubbed)
        report={"source_language":source,"target_language":target,"audio_sample_rate_hz":RATE,"audio_channels":1,
          "original_duration_sec":round(original,6),"new_duration_sec":round(newdur,6),"measured_lufs":lufs,"speech_segments":reports}
        report_path=out/"report.json"; report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return {"ok":True,"output_dir":str(out),"video":str(dubbed),"report":str(report_path),"tts_backend_used":sorted(set(used))}
    finally:
        shutil.rmtree(temp,ignore_errors=True)

if __name__=="__main__":
    try:
        cfg=json.load(sys.stdin)
        if not isinstance(cfg,dict): raise DubError("stdin JSON must be an object")
        print(json.dumps(main(cfg),ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok":False,"error":str(e)}))
        sys.exit(1)
