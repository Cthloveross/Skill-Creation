#!/usr/bin/env python3
"""JSON stdin/stdout web-essay-to-MP3 pipeline; uses only Python stdlib plus ffmpeg."""
import os, sys, json, re, html as htmlmod, hashlib, tempfile, shutil, subprocess, time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from urllib.error import URLError, HTTPError

UA = "web-essay-audiobook/1.0 (+respectful retrieval)"

class Failure(Exception):
    def __init__(self, kind, msg): self.kind, self.msg = kind, msg


def http_bytes(url, headers=None, tries=3):
    headers = dict(headers or {}); headers.setdefault("User-Agent", UA)
    last = None
    for n in range(tries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=25) as r: return r.read(), dict(r.headers)
        except (URLError, HTTPError, TimeoutError, OSError) as e:
            last = e
            if n + 1 < tries: time.sleep(1.2 * (n + 1))
    raise Failure("network_request_failed", "%s: %s" % (url, last))

def http_post(url, body, headers, tries=3):
    last = None
    for n in range(tries):
        try:
            h = dict(headers); h.setdefault("User-Agent", UA)
            req = Request(url, data=body, headers=h, method="POST")
            with urlopen(req, timeout=60) as r: return r.read()
        except (URLError, HTTPError, TimeoutError, OSError) as e:
            last = e
            if n + 1 < tries: time.sleep(1.5 * (n + 1))
    raise Failure("tts_request_failed", "%s: %s" % (url, last))

def decode_page(data, headers=None):
    hinted = (headers or {}).get("Content-Type", "")
    m = re.search(r"charset=([^; ]+)", hinted, re.I)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "windows-1252", "latin-1"]:
        try: return data.decode(enc)
        except (UnicodeDecodeError, LookupError): pass
    return data.decode("utf-8", "replace")

def norm(s):
    s = htmlmod.unescape(s).replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[^a-z0-9]+", "", s.lower())

class LinkParser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.href = None; self.buf = []; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a": self.href = dict(attrs).get("href"); self.buf = []
    def handle_data(self, data):
        if self.href: self.buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((" ".join(self.buf).strip(), self.href)); self.href = None; self.buf = []

def find_urls(index_html, index_url, titles):
    p = LinkParser(); p.feed(index_html)
    result = []
    for title in titles:
        target = norm(title); match = None
        for label, href in p.links:
            # Exact normalized text prevents a substring match to a similarly named essay.
            if norm(label) == target and href:
                match = urljoin(index_url, href); break
        if not match:
            raise Failure("essay_not_found", "Title not found in publisher index: %r" % title)
        result.append({"title": title, "url": match})
    return result

class ProseParser(HTMLParser):
    """Collect body blocks while retaining whether their text was only a link."""
    BREAKS = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "hr", "pre"}
    SKIP = {"script", "style", "noscript", "svg", "head", "title"}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.body = False; self.skip = 0; self.link = 0
        self.buf = []; self.nonlink = 0; self.blocks = []; self.br = 0
    def flush(self):
        text = re.sub(r"[ \t\r\f\v]+", " ", "".join(self.buf))
        text = re.sub(r" *\n *", " ", text).strip()
        if text: self.blocks.append((text, self.nonlink))
        self.buf = []; self.nonlink = 0; self.br = 0
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "body": self.body = True
        if tag in self.SKIP: self.skip += 1
        if self.body and not self.skip and tag in self.BREAKS: self.flush()
        if self.body and not self.skip and tag == "br":
            self.br += 1
            if self.br >= 2: self.flush()
            else: self.buf.append("\n")
        if tag == "a": self.link += 1
    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a": self.link = max(0, self.link - 1)
        if self.body and not self.skip and tag in self.BREAKS: self.flush()
        if tag in self.SKIP: self.skip = max(0, self.skip - 1)
        if tag == "body": self.flush(); self.body = False
    def handle_data(self, data):
        if self.body and not self.skip:
            self.buf.append(data)
            if not self.link: self.nonlink += len(data.strip())

def extract_prose(page_html, requested_title):
    p = ProseParser(); p.feed(page_html); p.flush()
    blocks = p.blocks
    key = norm(requested_title)
    start = 0
    for i, (text, _) in enumerate(blocks):
        t = norm(text)
        if key and (t == key or (key in t and len(t) <= len(key) + 40)):
            start = i; break
    kept = []
    chrome = re.compile(r"^(home|rss|subscribe|privacy policy|copyright|all rights reserved)$", re.I)
    for text, nonlink in blocks[start:]:
        text = re.sub(r"\s+", " ", text).strip()
        # A standalone navigation link has no non-link text; inline linked prose remains.
        if not text or not re.search(r"[A-Za-z0-9]", text) or nonlink == 0: continue
        if chrome.match(text): continue
        kept.append(text)
    prose = "\n\n".join(kept).strip()
    if len(prose) < 120:
        raise Failure("content_extraction_failed", "Too little main prose extracted for %r" % requested_title)
    return prose

def split_chunks(text, limit):
    # First preserve paragraphs, then sentences, finally words; no text is discarded.
    units = []
    for para in re.split(r"\n\s*\n+", text):
        para = para.strip()
        if not para: continue
        if len(para) <= limit: units.append(para); continue
        sentences = re.split(r"(?<=[.!?])\s+", para)
        units.extend(x.strip() for x in sentences if x.strip())
    out, cur = [], ""
    for unit in units:
        if len(unit) > limit:
            words = re.findall(r"\S+", unit)
            for word in words:
                if cur and len(cur) + 1 + len(word) > limit: out.append(cur); cur = ""
                if len(word) > limit:
                    if cur: out.append(cur); cur = ""
                    out.extend(word[i:i+limit] for i in range(0, len(word), limit))
                else: cur = (cur + " " + word).strip()
            continue
        if cur and len(cur) + 1 + len(unit) > limit: out.append(cur); cur = unit
        else: cur = (cur + " " + unit).strip()
    if cur: out.append(cur)
    return out

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode: raise Failure("media_processing_failed", "%s\n%s" % (" ".join(cmd), p.stderr[-1200:]))
    return p.stdout

def choose_engine(kind):
    if kind in ("auto", "openai") and os.environ.get("OPENAI_API_KEY"): return "openai"
    if kind in ("auto", "elevenlabs") and os.environ.get("ELEVENLABS_API_KEY"): return "elevenlabs"
    if kind in ("auto", "local"): return "local"
    raise Failure("tts_credentials_missing", "Requested TTS provider has no usable runtime credential")

def local_synth(text, path):
    for exe in ("espeak-ng", "espeak"):
        if shutil.which(exe): run([exe, "-v", "en", "-w", path, text]); return
    if shutil.which("pico2wave"):
        run(["pico2wave", "-l", "en-US", "-w", path, text]); return
    code = "import pyttsx3,sys;e=pyttsx3.init();e.save_to_file(sys.argv[1],sys.argv[2]);e.runAndWait()"
    try: run([sys.executable, "-c", code, text, path]); return
    except Failure: pass
    raise Failure("local_tts_unavailable", "No supported local TTS engine (espeak-ng/espeak/pico2wave/pyttsx3) is available")

def eleven_voice(key):
    configured = os.environ.get("ELEVENLABS_VOICE_ID")
    if configured: return configured
    raw, _ = http_bytes("https://api.elevenlabs.io/v1/voices", {"xi-api-key": key})
    voices = json.loads(raw.decode("utf-8")).get("voices", [])
    if not voices: raise Failure("tts_request_failed", "ElevenLabs returned no voices; set ELEVENLABS_VOICE_ID")
    return voices[0]["voice_id"]

def remote_synth(engine, text, path, voice, model):
    if engine == "openai":
        key = os.environ["OPENAI_API_KEY"]
        obj = {"model": model or "gpt-4o-mini-tts", "voice": voice or "alloy", "input": text, "response_format": "mp3"}
        raw = http_post("https://api.openai.com/v1/audio/speech", json.dumps(obj).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    else:
        key = os.environ["ELEVENLABS_API_KEY"]; vid = eleven_voice(key)
        obj = {"text": text, "model_id": model or "eleven_multilingual_v2"}
        raw = http_post("https://api.elevenlabs.io/v1/text-to-speech/" + vid, json.dumps(obj).encode(), {"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with open(path, "wb") as f: f.write(raw)

def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path])
    info = json.loads(out); dur = float(info.get("format", {}).get("duration", 0) or 0)
    if not any(x.get("codec_type") == "audio" for x in info.get("streams", [])) or dur <= 0: raise Failure("validation_failed", "Output has no decodable audio duration")
    return dur

def main(cfg):
    output = cfg.get("output_path")
    if not isinstance(output, str) or not os.path.isabs(output): raise Failure("invalid_input", "output_path must be an absolute path")
    provider = cfg.get("tts_provider", "auto")
    if provider not in ("auto", "openai", "elevenlabs", "local"): raise Failure("invalid_input", "Unknown tts_provider")
    limit = int(cfg.get("max_chars", 3500)); limit = max(500, min(4000, limit))
    sources = cfg.get("sources")
    if sources is None:
        titles = cfg.get("titles")
        if not isinstance(titles, list) or not titles or not all(isinstance(x, str) and x.strip() for x in titles): raise Failure("invalid_input", "titles must be a nonempty list of strings")
        index = cfg.get("index_url", "https://paulgraham.com/articles.html")
        try:
            raw, hdr = http_bytes(index); sources = find_urls(decode_page(raw, hdr), index, titles)
        except Failure as e:
            raise Failure("source_retrieval_failed", "Cannot retrieve/search the publisher index. Supply actual source HTML/URLs or restore network access. " + e.msg)
    if not isinstance(sources, list) or not sources: raise Failure("invalid_input", "sources must be a nonempty ordered list")
    essays = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("title"), str): raise Failure("invalid_input", "Each source needs a title and url or html")
        page = source.get("html")
        url = source.get("url")
        if not isinstance(page, str):
            if not isinstance(url, str): raise Failure("invalid_input", "Source %r lacks html/url" % source["title"])
            try:
                raw, hdr = http_bytes(url); page = decode_page(raw, hdr)
            except Failure as e: raise Failure("source_retrieval_failed", "Cannot retrieve %s: %s" % (url, e.msg))
        prose = extract_prose(page, source["title"])
        essays.append({"title": source["title"], "url": url, "prose": prose})
    engine = choose_engine(provider)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    work = tempfile.mkdtemp(prefix="audiobook-", dir=os.path.dirname(output))
    try:
        records, wavs = [], []
        for si, essay in enumerate(essays):
            chunks = split_chunks(essay["prose"], limit)
            if not chunks: raise Failure("content_extraction_failed", "No chunks for " + essay["title"])
            for ci, text in enumerate(chunks):
                rawpath = os.path.join(work, "raw-%04d-%04d.%s" % (si, ci, "wav" if engine == "local" else "mp3"))
                try:
                    if engine == "local": local_synth(text, rawpath)
                    else: remote_synth(engine, text, rawpath, cfg.get("voice"), cfg.get("model"))
                except Failure:
                    if provider == "auto" and engine != "local": engine = "local"; rawpath = os.path.splitext(rawpath)[0] + ".wav"; local_synth(text, rawpath)
                    else: raise
                wav = os.path.join(work, "part-%04d-%04d.wav" % (si, ci))
                run(["ffmpeg", "-y", "-v", "error", "-i", rawpath, "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", wav])
                wavs.append(wav); records.append({"source_index": si, "chunk_index": ci, "characters": len(text), "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
        if [ (r["source_index"], r["chunk_index"]) for r in records ] != sorted((r["source_index"], r["chunk_index"]) for r in records): raise Failure("validation_failed", "Chunk order is not monotonic")
        listing = os.path.join(work, "concat.txt")
        with open(listing, "w", encoding="utf-8") as f:
            for w in wavs: f.write("file '%s'\n" % w.replace("'", "'\\''"))
        candidate = os.path.join(work, "final.mp3")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-vn", "-c:a", "libmp3lame", "-q:a", "3", candidate])
        duration = probe(candidate)
        run(["ffmpeg", "-v", "error", "-i", candidate, "-f", "null", "-"])
        if duration < float(cfg.get("min_duration_seconds", 1)): raise Failure("validation_failed", "Final audio duration is too short")
        manifest = {"output_path": output, "duration_seconds": duration, "engine": engine, "sources": [{"index": i, "title": x["title"], "url": x["url"], "extracted_text_sha256": hashlib.sha256(x["prose"].encode()).hexdigest(), "paragraph_count": len(x["prose"].split("\n\n"))} for i, x in enumerate(essays)], "chunks": records}
        os.replace(candidate, output)
        manifest_path = output + ".manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f: json.dump(manifest, f, ensure_ascii=False, indent=2)
        return {"ok": True, "output_path": output, "manifest_path": manifest_path, "duration_seconds": duration, "engine": engine, "sources": len(essays), "chunks": len(records)}
    finally: shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    try:
        cfg = json.load(sys.stdin); print(json.dumps(main(cfg), ensure_ascii=False))
    except Failure as e: print(json.dumps({"ok": False, "error": e.kind, "message": e.msg}, ensure_ascii=False))
    except Exception as e: print(json.dumps({"ok": False, "error": "unexpected_error", "message": str(e)}, ensure_ascii=False))
