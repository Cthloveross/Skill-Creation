#!/usr/bin/env python3
"""Apply exact-string PDF redactions and validate resulting PDFs.

stdin schema:
{"documents":[{"input":"source.pdf", "output":"redacted.pdf",
 "auto_discover":true, "clear_metadata":true,
 "targets":[{"text":"exact string", "scope":"before_references|pages|all",
             "pages":[1], "regions":[{"page":1,"rect":[0,0,100,30]}],
             "required":true}]}]}

stdout is a JSON report. Every annotation originates from page.search_for(text).
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

REF_RE = re.compile(r"^\s*(?:\d+\.?\s+)?(?:references|bibliography)\s*$", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
ARXIV_RE = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)
AFFIL_RE = re.compile(r"\b(university|universit[a-z]*|institute|institution|department|school|laboratory|laboratories|college|centre|center|research lab|inc\.|ltd\.|corporation|company|gmbh|academy|hospital)\b", re.I)
CLUE_RE = re.compile(r"\b(?:accepted|acceptance|proceedings|conference|published|copyright|camera[ -]?ready)\b", re.I)
PERSON_RE = re.compile(r"\b(?:[A-Z][A-Za-z'’\-]+|[A-Z]\.)(?:\s+(?:[A-Z][A-Za-z'’\-]+|[A-Z]\.)){1,3}\b")
WORD_RE = re.compile(r"\b[\w]+(?:[’'\-][\w]+)*\b", re.UNICODE)


def reference_boundary(doc):
    for index, page in enumerate(doc):
        for line in page.get_text("text").splitlines():
            heading = line.strip()
            if REF_RE.match(heading):
                hits = page.search_for(heading)
                return (index, float(hits[0].y0) if hits else None, heading)
    return None


def rect_intersects(a, b):
    return not (a.x1 <= b.x0 or b.x1 <= a.x0 or a.y1 <= b.y0 or b.y1 <= a.y0)


def validate_target(target):
    if not isinstance(target, dict) or not isinstance(target.get("text"), str) or not target["text"].strip():
        raise ValueError("each target requires nonempty string text")
    if target.get("scope", "before_references") not in ("before_references", "pages", "all"):
        raise ValueError("scope must be before_references, pages, or all")
    pages = target.get("pages")
    if pages is not None and (not isinstance(pages, list) or not all(isinstance(p, int) and p > 0 for p in pages)):
        raise ValueError("pages must be positive one-based integers")
    if target.get("scope") == "pages" and not pages:
        raise ValueError("scope pages requires pages")
    regions = target.get("regions")
    if regions is not None:
        if not isinstance(regions, list):
            raise ValueError("regions must be an array")
        for item in regions:
            if not isinstance(item, dict) or not isinstance(item.get("page"), int):
                raise ValueError("each region needs integer page")
            rect = item.get("rect")
            if not isinstance(rect, list) or len(rect) != 4 or not all(isinstance(v, (int, float)) for v in rect):
                raise ValueError("region rect must be [x0,y0,x1,y1]")


def eligible(page_index, rect, target, boundary):
    scope = target.get("scope", "before_references")
    pno = page_index + 1
    if scope == "before_references":
        if boundary is None:
            return False
        bpage, by, _ = boundary
        if page_index > bpage or (page_index == bpage and (by is None or rect.y1 > by)):
            return False
    pages = target.get("pages")
    if pages is not None and pno not in pages:
        return False
    regions = target.get("regions")
    if regions and not any(r["page"] == pno and rect_intersects(rect, fitz.Rect(r["rect"])) for r in regions):
        return False
    return True


def find_hits(doc, target, boundary):
    return [(pno, fitz.Rect(rect)) for pno, page in enumerate(doc)
            for rect in page.search_for(target["text"])
            if eligible(pno, rect, target, boundary)]


def add_candidate(items, text, scope, **extra):
    text = (text or "").strip()
    if len(text) >= 3:
        value = {"text": text, "scope": scope, "required": False, "automatic": True}
        value.update(extra)
        items.append(value)


def metadata_names(metadata):
    author = (metadata.get("author") or "").strip()
    if not author or author.casefold() in {"anonymous", "unknown", "none"}:
        return []
    values = [author]
    values.extend(x.strip() for x in re.split(r"\s*(?:;|\band\b)\s*", author, flags=re.I))
    return values


def auto_targets(doc, boundary):
    """Conservative discovery of exact runtime strings; it never uses area deletion."""
    items = []
    default_scope = "before_references" if boundary is not None else "all"
    texts = [page.get_text("text") for page in doc]
    for text in texts:
        for regex in (EMAIL_RE, ARXIV_RE, DOI_RE):
            for m in regex.finditer(text):
                add_candidate(items, m.group(0), default_scope)

    # Title material contains the most reliable affiliation and likely byline strings.
    first_lines = [line.strip() for line in texts[0].splitlines() if line.strip()] if texts else []
    abstract_at = next((i for i, line in enumerate(first_lines) if line.casefold().startswith("abstract")), len(first_lines))
    title_material = first_lines[:abstract_at]
    for line in title_material:
        if AFFIL_RE.search(line):
            add_candidate(items, line, default_scope)
        if CLUE_RE.search(line):
            add_candidate(items, line, default_scope)
    # Ignore the first two lines, normally paper title, to avoid treating title words as people.
    for line in title_material[2:]:
        if AFFIL_RE.search(line) or "@" in line:
            continue
        for name in PERSON_RE.findall(line):
            add_candidate(items, name, default_scope)

    for name in metadata_names(doc.metadata or {}):
        add_candidate(items, name, default_scope)

    # Explicitly examine only acknowledgement thank-you prose for proper-name candidates.
    full_pre = "\n".join(texts)
    if boundary is not None:
        cut_page, _, _ = boundary
        full_pre = "\n".join(texts[:cut_page + 1])
    ack = re.search(r"(?is)\backnowledg(?:e)?ments?\b(.*?)(?=\n\s*(?:\d+\.?\s*)?(?:references|bibliography|appendix)\b|\Z)", full_pre)
    if ack:
        for clause in re.finditer(r"(?:thank(?:s)?|grateful to|indebted to)\s+([^.;:]{1,240})", ack.group(1), re.I):
            for name in PERSON_RE.findall(clause.group(1)):
                add_candidate(items, name, default_scope)

    for text in texts:
        for line in text.splitlines():
            if CLUE_RE.search(line):
                add_candidate(items, line.strip(), default_scope)

    # If a concrete direct identifier is repeated in a References-page running header/footer,
    # add an exact-hit-only target for that narrow header/footer match, not the bibliography.
    direct_texts = {x["text"] for x in items if EMAIL_RE.fullmatch(x["text"]) or ARXIV_RE.fullmatch(x["text"]) or x["text"] in metadata_names(doc.metadata or {})}
    for value in sorted(direct_texts):
        regions = []
        for pno, page in enumerate(doc, 1):
            for rect in page.search_for(value):
                if rect.y0 < 72 or rect.y1 > page.rect.height - 72:
                    regions.append({"page": pno, "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]})
        if regions:
            add_candidate(items, value, "all", regions=regions)

    unique, seen = [], set()
    for item in items:
        key = (item["text"], item.get("scope"), tuple(item.get("pages") or []),
               json.dumps(item.get("regions") or [], sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def clear_identity_metadata(doc):
    meta = dict(doc.metadata or {})
    for key in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate", "trapped"):
        if key in meta:
            meta[key] = ""
    doc.set_metadata(meta)
    try:
        doc.del_xml_metadata()
    except (AttributeError, RuntimeError):
        pass


def identity_metadata(doc):
    meta = doc.metadata or {}
    keys = ("author", "creator", "title", "subject", "keywords")
    return {key: meta.get(key) for key in keys if str(meta.get(key) or "").strip()}


def normalized_words(text):
    return [x.casefold() for x in WORD_RE.findall(text)]


def missing_non_target_words(before, after, targets):
    ignored = set()
    for target in targets:
        ignored.update(normalized_words(target["text"]))
    a = Counter(x for x in normalized_words(before) if x not in ignored)
    b = Counter(x for x in normalized_words(after) if x not in ignored)
    return sum((a - b).values())


def process(spec):
    if not isinstance(spec, dict):
        raise ValueError("each document must be an object")
    source, output = spec.get("input"), spec.get("output")
    if not isinstance(source, str) or not Path(source).is_file():
        raise FileNotFoundError("input PDF does not exist: " + str(source))
    if not isinstance(output, str) or not output:
        raise ValueError("output must be a nonempty path")
    doc = fitz.open(source)
    temp_name = None
    try:
        boundary = reference_boundary(doc)
        manual = spec.get("targets", [])
        if not isinstance(manual, list):
            raise ValueError("targets must be an array")
        targets = (auto_targets(doc, boundary) if spec.get("auto_discover", False) else []) + manual
        if not targets:
            raise ValueError("supply targets or set auto_discover true")
        for target in targets:
            validate_target(target)
        if boundary is None:
            for target in manual:
                if target.get("scope", "before_references") == "before_references":
                    raise ValueError("no References heading found; manual target needs pages, regions, or scope all")

        original_text = "\n".join(page.get_text("text") for page in doc)
        hits_by_target = [find_hits(doc, target, boundary) for target in targets]
        for target, hits in zip(targets, hits_by_target):
            if target.get("required", True) and not hits:
                raise ValueError("required target has no eligible exact match: " + repr(target["text"]))
        for hits in hits_by_target:
            for page_index, rect in hits:
                doc[page_index].add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        for page in doc:
            page.apply_redactions()
        clear_meta = spec.get("clear_metadata", True)
        if clear_meta:
            clear_identity_metadata(doc)

        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".redaction-", suffix=".pdf", dir=str(out_path.parent))
        os.close(fd)
        doc.save(temp_name, garbage=4, deflate=True)
    finally:
        doc.close()

    try:
        result, original = fitz.open(temp_name), fitz.open(source)
        try:
            if result.page_count != original.page_count:
                raise ValueError("validation failed: page count changed")
            remaining = []
            for target, old_hits in zip(targets, hits_by_target):
                for page_index, old_rect in old_hits:
                    if any(rect_intersects(old_rect, now) for now in result[page_index].search_for(target["text"])):
                        remaining.append({"text": target["text"], "page": page_index + 1})
            if remaining:
                raise ValueError("validation failed: selected targets remain: " + json.dumps(remaining, ensure_ascii=False))
            if clear_meta and identity_metadata(result):
                raise ValueError("validation failed: identity metadata remains")
            lost = missing_non_target_words("\n".join(p.get_text("text") for p in original),
                                            "\n".join(p.get_text("text") for p in result), targets)
            if lost > 50:
                raise ValueError("validation failed: %d non-target words disappeared (limit 50)" % lost)
            unmatched = [target["text"] for target, hits in zip(targets, hits_by_target)
                         if target.get("automatic") and not hits]
            report = {"input": source, "output": output, "page_count": result.page_count,
                      "reference_boundary": None if boundary is None else {"page": boundary[0] + 1, "y": boundary[1], "heading": boundary[2]},
                      "redactions": [{"text": target["text"], "matches_redacted": len(hits)} for target, hits in zip(targets, hits_by_target)],
                      "unmatched_automatic_candidates": unmatched,
                      "non_target_words_missing": lost, "metadata_cleared": bool(clear_meta), "valid": True}
        finally:
            original.close()
            result.close()
        os.replace(temp_name, output)
        temp_name = None
        return report
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main():
    config = json.load(sys.stdin)
    docs = config.get("documents") if isinstance(config, dict) else None
    if not isinstance(docs, list) or not docs:
        raise ValueError("input must contain nonempty documents array")
    reports = [process(spec) for spec in docs]
    print(json.dumps({"documents": reports, "valid": all(x["valid"] for x in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
