"""Applied, page-preserving PDF anonymization.

stdin JSON: {"inputs":["/source.pdf"], "output_dir":"/out",
 "targets_by_input":{"/source.pdf":[{"text":"exact text",
 "scope":"before_references|pages|all", "pages":[0]}]},
 "report_path":"/optional/audit.json"}
stdout: {"status":"ok|error", "jobs":[...]}. Requires PyMuPDF (fitz).
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from typing import Any
try:
    import fitz
except Exception as exc:
    fitz = None
    FITZ_ERROR = str(exc)
else:
    FITZ_ERROR = ""

REF_RE = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(?:references|bibliography)\s*$")
EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
ARXIV_RE = re.compile(r"(?i)\barxiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?\b")
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:a-z0-9]+")
NAME_RE = re.compile(r"\b([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,3})\b")
AFF_RE = re.compile(r"(?i)\b(?:university|universit[eé]|institute|institution|department|school of|college|laboratory|lab(?:oratory)?|centre|center|research group|inc\.|llc|ltd\.|corporation|gmbh)\b")
ACK_RE = re.compile(r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)")
ACK_NAME_RE = re.compile(r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published|appearing|presented)\s+(?:at|in)\b|\b(?:proceedings of|copyright .*?(?:association|conference|society))\b")

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def boundary(texts: list[str]) -> tuple[int | None, int | None]:
    for i, text in enumerate(texts):
        m = REF_RE.search(text)
        if m:
            return i, m.start()
    return None, None

def body_text(texts: list[str], ref_page: int | None, offset: int | None) -> str:
    if ref_page is None:
        return "\n".join(texts)
    return "\n".join(texts[:ref_page] + [texts[ref_page][:offset or 0]])

def discover(texts: list[str], ref_page: int | None, offset: int | None) -> list[str]:
    """Return exact textual targets; no region- or page-area redaction is used."""
    before = body_text(texts, ref_page, offset)
    first = texts[0] if texts else ""
    abstract = re.search(r"(?im)^\s*abstract\b", first)
    zone = first[:abstract.start()] if abstract else first[:2500]
    lines = [norm(x) for x in zone.splitlines() if norm(x)]
    stop = {"Abstract", "Introduction", "Proceedings", "University", "Department", "Institute", "School", "Laboratory", "College", "Corresponding"}
    found: set[str] = set()
    for line in lines:
        for name in NAME_RE.findall(line):
            if len(name) >= 5 and not any(x in stop for x in name.split()) and (len(line) <= 180 or line.count(",") >= 1):
                found.add(name)
        if AFF_RE.search(line) and len(line) <= 250:
            found.add(line)
        if len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            found.add(line)
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(m.group(0) for m in pattern.finditer(before))
    ack = ACK_RE.search(before)
    if ack:
        for name in ACK_NAME_RE.findall(ack.group(1)):
            name = re.sub(r"\s+and\s+", " and ", name).strip()
            if len(name) >= 5:
                found.add(name)
    for raw in before.splitlines():
        line = norm(raw)
        if line and len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            found.add(line)
    return sorted(found, key=lambda s: (-len(s), s.casefold()))

def parse_manual(value: Any) -> list[dict[str, Any]]:
    if value is None: return []
    if not isinstance(value, list): raise ValueError("targets_by_input values must be arrays")
    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each target requires nonempty text")
        scope = item.get("scope", "before_references")
        if scope not in {"before_references", "pages", "all"}: raise ValueError("invalid target scope")
        result.append({"text": item["text"], "scope": scope, "pages": item.get("pages"), "origin": "manual"})
    return result

def pages_for(t: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    if t["scope"] == "all": return list(range(count))
    if t["scope"] == "before_references": return list(range(count if ref_page is None else ref_page + 1))
    raw = t.get("pages")
    if not isinstance(raw, list) or not raw: raise ValueError("pages scope needs nonempty pages")
    if any(not isinstance(p, int) or isinstance(p, bool) or p < 0 or p >= count for p in raw): raise ValueError("invalid selected page")
    return list(dict.fromkeys(raw))

def ref_y(doc: Any, page_no: int | None, text: str) -> float | None:
    if page_no is None: return None
    m = REF_RE.search(text)
    if not m: return None
    hits = doc[page_no].search_for(m.group(0).strip())
    return min((r.y0 for r in hits), default=None)

def search(page: Any, text: str) -> list[Any]:
    hits = list(page.search_for(text))
    if hits or " " not in text: return hits
    # Exact phrase may be split into PDF spans. This fallback only touches literal
    # multiword components of a reviewed/discovered target.
    parts = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ'’.-]{2,}", text)
    if len(parts) >= 2:
        for part in parts: hits.extend(page.search_for(part))
    return hits

def clean_metadata(doc: Any) -> list[str]:
    meta = dict(doc.metadata or {})
    changed = []
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        if meta.get(key): changed.append(key)
        meta[key] = ""
    doc.set_metadata(meta)
    try: doc.set_xml_metadata("")
    except Exception: pass
    return changed

def output_before_refs(doc: Any, ref_page: int | None) -> str:
    texts = [p.get_text("text") for p in doc]
    _, offset = boundary(texts)
    return body_text(texts, ref_page, offset)

def process(source_text: str, out_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_text)
    if not source.is_file(): raise ValueError(f"input file does not exist: {source}")
    output = out_dir / source.name
    if source.resolve() == output.resolve(): raise ValueError("output must not overwrite source")
    doc = fitz.open(str(source)); temporary = None
    try:
        count = doc.page_count
        if count < 1: raise ValueError("input has no pages")
        texts = [p.get_text("text") for p in doc]
        ref_page, offset = boundary(texts)
        heading_y = ref_y(doc, ref_page, texts[ref_page] if ref_page is not None else "")
        targets = [{"text": x, "scope": "before_references", "pages": None, "origin": "automatic"} for x in discover(texts, ref_page, offset)] + manual
        unique, seen = [], set()
        for t in targets:
            key = (t["text"], t["scope"], tuple(t.get("pages") or []))
            if key not in seen: seen.add(key); unique.append(t)
        rectangles: dict[int, list[Any]] = {}; audit = []
        for t in unique:
            n = 0
            for page_no in pages_for(t, count, ref_page):
                for rect in search(doc[page_no], t["text"]):
                    # Never let automatic/default targets cross into References on
                    # the mixed heading page.
                    if t["scope"] == "before_references" and page_no == ref_page and heading_y is not None and rect.y1 > heading_y + .5:
                        continue
                    rectangles.setdefault(page_no, []).append(rect); n += 1
            audit.append({"text": t["text"], "scope": t["scope"], "origin": t["origin"], "rectangles": n})
        for page_no, rects in rectangles.items():
            page, used = doc[page_no], set()
            for rect in rects:
                key = tuple(round(x, 3) for x in (rect.x0, rect.y0, rect.x1, rect.y1))
                if key not in used:
                    used.add(key); page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
        metadata = clean_metadata(doc)
        out_dir.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close(); os.replace(temporary, output); temporary = None
        saved = fitz.open(str(output))
        try:
            if saved.page_count != count: raise RuntimeError("saved page count changed")
            remaining_text = output_before_refs(saved, ref_page)
        finally: saved.close()
        residual = [a["text"] for a in audit if a["rectangles"] and re.search(re.escape(a["text"]), remaining_text, re.I)]
        return {"input": str(source), "output": str(output), "readable": True, "original_page_count": count, "output_page_count": count, "page_count_matches": True, "references_page_zero_based": ref_page, "metadata_cleared": metadata, "targets": audit, "unmatched_manual_targets": [a["text"] for a in audit if a["origin"] == "manual" and not a["rectangles"]], "residual_targets_before_references": residual}
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
        if not doc.is_closed: doc.close()

def main() -> int:
    try:
        if fitz is None: raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        request = json.load(sys.stdin)
        if not isinstance(request, dict): raise ValueError("stdin JSON must be an object")
        inputs, output_dir = request.get("inputs"), request.get("output_dir")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) and x for x in inputs): raise ValueError("inputs must be a nonempty path array")
        if not isinstance(output_dir, str) or not output_dir: raise ValueError("output_dir must be a nonempty path")
        mapping = request.get("targets_by_input", {})
        if not isinstance(mapping, dict): raise ValueError("targets_by_input must be an object")
        jobs = []
        for source in inputs:
            try: jobs.append(process(source, Path(output_dir), parse_manual(mapping.get(source))))
            except Exception as exc: jobs.append({"input": source, "status": "error", "error": str(exc)})
        result = {"status": "ok" if all("error" not in j for j in jobs) else "error", "jobs": jobs}
        report = request.get("report_path")
        if report is not None:
            if not isinstance(report, str) or not report: raise ValueError("report_path must be a nonempty path")
            p = Path(report); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            result["report_path"] = str(p)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0 if result["status"] == "ok" else 2
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)})); return 2
if __name__ == "__main__": sys.exit(main())
