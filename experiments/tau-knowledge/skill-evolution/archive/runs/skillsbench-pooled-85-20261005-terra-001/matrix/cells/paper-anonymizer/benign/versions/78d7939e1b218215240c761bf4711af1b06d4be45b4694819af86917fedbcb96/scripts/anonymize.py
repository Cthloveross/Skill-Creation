#!/usr/bin/env python3
"""Applied, exact-match PDF anonymization.

stdin schema:
{"documents":[{"input":"source.pdf","output":"redacted.pdf",
 "auto_discover":true,"clear_metadata":true,"targets":[target]}]}

A target is {"text":str,"scope":"before_references|pages|all",
"pages":[one-based page], "regions":[{"page":n,"rect":[x0,y0,x1,y1]}],
"required":bool}. Regions filter text-search hits only; they are never redacted
as arbitrary rectangles.
"""
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

REF = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references|bibliography)\s*$", re.I)
EMAIL = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
ARXIV = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.I)
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)
AFFILIATION = re.compile(r"\b(?:university|universit[a-z]*|institute|institution|department|school|laborator(?:y|ies)|college|centre|center|research\s+lab|inc\.|ltd\.|corporation|company|gmbh|academy|hospital)\b", re.I)
VENUE = re.compile(r"\b(?:accepted|acceptance|camera[ -]?ready|copyright|published\s+in|proceedings\s+of)\b", re.I)
NAME = re.compile(r"\b(?:[A-Z][A-Za-z'’\-]+|[A-Z]\.)(?:\s+(?:[A-Z][A-Za-z'’\-]+|[A-Z]\.)){1,3}\b")
WORDS = re.compile(r"\b[\w]+(?:[’'\-][\w]+)*\b", re.UNICODE)


def reference_boundary(doc):
    for pno, page in enumerate(doc):
        for raw in page.get_text("text").splitlines():
            heading = raw.strip()
            if REF.match(heading):
                boxes = page.search_for(heading)
                return (pno, float(boxes[0].y0) if boxes else None, heading)
    return None


def intersects(a, b):
    return not (a.x1 <= b.x0 or b.x1 <= a.x0 or a.y1 <= b.y0 or b.y1 <= a.y0)


def validate_target(target):
    if not isinstance(target, dict) or not isinstance(target.get("text"), str) or not target["text"].strip():
        raise ValueError("each target requires a nonempty text string")
    if target.get("scope", "before_references") not in {"before_references", "pages", "all"}:
        raise ValueError("target scope must be before_references, pages, or all")
    pages = target.get("pages")
    if pages is not None and (not isinstance(pages, list) or not all(isinstance(p, int) and p > 0 for p in pages)):
        raise ValueError("target pages must be positive one-based integers")
    if target.get("scope") == "pages" and not pages:
        raise ValueError("scope pages requires pages")
    regions = target.get("regions")
    if regions is not None:
        if not isinstance(regions, list):
            raise ValueError("regions must be an array")
        for item in regions:
            rect = item.get("rect") if isinstance(item, dict) else None
            if not isinstance(item, dict) or not isinstance(item.get("page"), int):
                raise ValueError("each region needs an integer page")
            if not isinstance(rect, list) or len(rect) != 4 or not all(isinstance(x, (int, float)) for x in rect):
                raise ValueError("each region rect must be [x0,y0,x1,y1]")


def eligible(pno, rect, target, boundary):
    if target.get("scope", "before_references") == "before_references" and boundary:
        bp, by, _ = boundary
        if pno > bp or (pno == bp and (by is None or rect.y1 > by)):
            return False
    pages = target.get("pages")
    if pages is not None and pno + 1 not in pages:
        return False
    regions = target.get("regions")
    return not regions or any(r["page"] == pno + 1 and intersects(rect, fitz.Rect(r["rect"])) for r in regions)


def find_hits(doc, target, boundary):
    found = []
    for pno, page in enumerate(doc):
        for rect in page.search_for(target["text"]):
            rect = fitz.Rect(rect)
            if eligible(pno, rect, target, boundary):
                found.append((pno, rect))
    return found


def add(items, text, scope="before_references", **extra):
    text = (text or "").strip()
    if len(text) >= 3:
        item = {"text": text, "scope": scope, "required": False, "automatic": True}
        item.update(extra)
        items.append(item)


def title_lines(first_page_text):
    lines = [x.strip() for x in first_page_text.splitlines() if x.strip()]
    stop = next((n for n, x in enumerate(lines) if re.match(r"^abstract\b", x, re.I)), len(lines))
    return lines[:stop]


def metadata_names(doc):
    value = str((doc.metadata or {}).get("author") or "").strip()
    if not value or value.casefold() in {"anonymous", "unknown", "none"}:
        return []
    parts = [x.strip() for x in re.split(r"\s*(?:;|,|\band\b)\s*", value, flags=re.I) if x.strip()]
    return [value] + parts


def author_like_line(line):
    """Return full-name substrings only for a compact, title-page byline-like line."""
    if "@" in line or AFFILIATION.search(line) or VENUE.search(line):
        return []
    compact = re.sub(r"[*†‡0-9]", "", line).strip()
    alpha = re.findall(r"[A-Za-z]+", compact)
    if not alpha or len(alpha) > 12:
        return []
    names = NAME.findall(compact)
    # A comma/and separated line of capitalized name phrases is a conventional byline.
    parts = [p.strip() for p in re.split(r"\s*(?:,|;|\band\b)\s*", compact, flags=re.I) if p.strip()]
    if len(parts) >= 2 and all(NAME.fullmatch(p) for p in parts):
        return names
    # One compact two-to-four-token proper-name line beneath the title is also common.
    if len(parts) == 1 and NAME.fullmatch(compact):
        return names
    return []


def automatic_targets(doc, boundary):
    targets = []
    page_text = [page.get_text("text") for page in doc]
    # Exact direct identifiers are only eligible before References.
    for text in page_text:
        for pattern in (EMAIL, ARXIV, DOI):
            for match in pattern.finditer(text):
                add(targets, match.group(0))
    first = title_lines(page_text[0]) if page_text else []
    for line in first:
        if AFFILIATION.search(line) or VENUE.search(line):
            add(targets, line)
    for name in metadata_names(doc):
        add(targets, name)
    for line in first[1:]:  # never mistake the first/title line for a byline
        for name in author_like_line(line):
            add(targets, name)
    # Acknowledgements need review, but recognizable thank-you names are safe candidates.
    before = "\n".join(page_text[:boundary[0] + 1] if boundary else page_text)
    ack = re.search(r"(?is)\backnowledg(?:e)?ments?\b(.*?)(?=\n\s*(?:\d+\.?\s*)?(?:references|bibliography|appendix)\b|\Z)", before)
    if ack:
        for phrase in re.finditer(r"(?:thank(?:s)?|grateful\s+to|indebted\s+to)\s+([^.;:]{1,240})", ack.group(1), re.I):
            for name in NAME.findall(phrase.group(1)):
                add(targets, name)
    # Venue/acceptance leaks in title material and running headers/footers.
    for pno, page in enumerate(doc, 1):
        for line in page.get_text("text").splitlines():
            line = line.strip()
            if not line or not VENUE.search(line):
                continue
            regions = []
            for rect in page.search_for(line):
                if pno == 1 or rect.y0 < 72 or rect.y1 > page.rect.height - 72:
                    regions.append({"page": pno, "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]})
            if regions:
                add(targets, line, "all", regions=regions)
    # Direct identifiers/names can occur in running headers even on reference pages.
    direct = {x["text"] for x in targets if EMAIL.fullmatch(x["text"]) or ARXIV.fullmatch(x["text"])}
    direct.update(metadata_names(doc))
    for text in direct:
        regions = []
        for pno, page in enumerate(doc, 1):
            for rect in page.search_for(text):
                if rect.y0 < 72 or rect.y1 > page.rect.height - 72:
                    regions.append({"page": pno, "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]})
        if regions:
            add(targets, text, "all", regions=regions)
    unique, seen = [], set()
    for target in targets:
        key = (target["text"], target.get("scope"), tuple(target.get("pages") or ()), json.dumps(target.get("regions") or [], sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


def clear_metadata(doc):
    metadata = dict(doc.metadata or {})
    for key in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate", "trapped"):
        if key in metadata:
            metadata[key] = ""
    doc.set_metadata(metadata)
    try:
        doc.del_xml_metadata()
    except (AttributeError, RuntimeError):
        pass


def remaining_metadata(doc):
    meta = doc.metadata or {}
    return {k: str(meta.get(k) or "") for k in ("author", "title", "subject", "keywords", "creator") if str(meta.get(k) or "").strip()}


def tokens(text):
    return [x.casefold() for x in WORDS.findall(text)]


def non_target_loss(before, after, targets):
    ignored = set()
    for target in targets:
        ignored.update(tokens(target["text"]))
    old = Counter(x for x in tokens(before) if x not in ignored)
    new = Counter(x for x in tokens(after) if x not in ignored)
    return sum((old - new).values())


def process(spec):
    if not isinstance(spec, dict):
        raise ValueError("each document must be an object")
    source, destination = spec.get("input"), spec.get("output")
    if not isinstance(source, str) or not Path(source).is_file():
        raise FileNotFoundError("input PDF does not exist: " + str(source))
    if not isinstance(destination, str) or not destination:
        raise ValueError("output must be a nonempty path")
    doc = fitz.open(source)
    temporary = None
    try:
        boundary = reference_boundary(doc)
        supplied = spec.get("targets", [])
        if not isinstance(supplied, list):
            raise ValueError("targets must be an array")
        targets = (automatic_targets(doc, boundary) if spec.get("auto_discover", False) else []) + supplied
        for target in targets:
            validate_target(target)
        hits = [find_hits(doc, target, boundary) for target in targets]
        for target, matches in zip(targets, hits):
            if target.get("required", True) and not matches:
                raise ValueError("required target has no eligible exact match: " + repr(target["text"]))
        original_text = "\n".join(page.get_text("text") for page in doc)
        for matches in hits:
            for pno, rect in matches:
                doc[pno].add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        for page in doc:
            page.apply_redactions()
        metadata_cleared = bool(spec.get("clear_metadata", True))
        if metadata_cleared:
            clear_metadata(doc)
        out = Path(destination)
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".redaction-", suffix=".pdf", dir=str(out.parent))
        os.close(fd)
        doc.save(temporary, garbage=4, deflate=True)
    finally:
        doc.close()
    try:
        result, original = fitz.open(temporary), fitz.open(source)
        try:
            if result.page_count != original.page_count:
                raise ValueError("validation failed: page count changed")
            still_present = []
            for target, matches in zip(targets, hits):
                for pno, old_rect in matches:
                    if any(intersects(old_rect, now) for now in result[pno].search_for(target["text"])):
                        still_present.append({"text": target["text"], "page": pno + 1})
            if still_present:
                raise ValueError("validation failed: selected targets remain: " + json.dumps(still_present, ensure_ascii=False))
            if metadata_cleared and remaining_metadata(result):
                raise ValueError("validation failed: identity-bearing metadata remains")
            lost = non_target_loss(original_text, "\n".join(page.get_text("text") for page in result), targets)
            if lost > 50:
                raise ValueError("validation failed: %d non-target words disappeared (limit 50)" % lost)
            report = {"input": source, "output": destination, "page_count": result.page_count,
                      "reference_boundary": None if not boundary else {"page": boundary[0] + 1, "y": boundary[1], "heading": boundary[2]},
                      "redactions": [{"text": t["text"], "matches_redacted": len(h)} for t, h in zip(targets, hits)],
                      "unmatched_automatic_candidates": [t["text"] for t, h in zip(targets, hits) if t.get("automatic") and not h],
                      "non_target_words_missing": lost, "metadata_cleared": metadata_cleared,
                      "warnings": [] if targets else ["No searchable targets found; inspect image-only and already-anonymous material manually."], "valid": True}
        finally:
            result.close()
            original.close()
        os.replace(temporary, destination)
        temporary = None
        return report
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    request = json.load(sys.stdin)
    documents = request.get("documents") if isinstance(request, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ValueError("input must contain a nonempty documents array")
    reports = [process(doc) for doc in documents]
    print(json.dumps({"documents": reports, "valid": all(x["valid"] for x in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
