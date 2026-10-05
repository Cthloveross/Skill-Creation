#!/usr/bin/env python3
"""Create validated blind-review PDFs using true, exact-match PDF redactions.

stdin schema:
{"documents":[{"input":"source.pdf", "output":"redacted.pdf",
 "auto_discover":true, "clear_metadata":true,
 "targets":[{"text":"exact string", "scope":"before_references|pages|all",
             "pages":[1], "regions":[{"page":1,"rect":[0,0,100,30]}],
             "required":true}]}]}

Every annotation is derived from page.search_for(text). Regions only filter those
matches; this program never uses a supplied region as a redaction rectangle.
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
AFFILIATION = re.compile(
    r"\b(?:university|universit[a-z]*|institute|institution|department|school|"
    r"laboratory|laboratories|college|centre|center|research lab|inc\.|ltd\.|"
    r"corporation|company|gmbh|academy|hospital)\b", re.I)
VENUE = re.compile(r"\b(?:accepted|acceptance|proceedings|conference|published|copyright|camera[ -]?ready)\b", re.I)
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


def intersects(left, right):
    return not (left.x1 <= right.x0 or right.x1 <= left.x0 or
                left.y1 <= right.y0 or right.y1 <= left.y0)


def validate_target(target):
    if not isinstance(target, dict) or not isinstance(target.get("text"), str) or not target["text"].strip():
        raise ValueError("each target requires nonempty string text")
    scope = target.get("scope", "before_references")
    if scope not in {"before_references", "pages", "all"}:
        raise ValueError("scope must be before_references, pages, or all")
    pages = target.get("pages")
    if pages is not None and (not isinstance(pages, list) or not all(isinstance(p, int) and p > 0 for p in pages)):
        raise ValueError("pages must be an array of positive one-based integers")
    if scope == "pages" and not pages:
        raise ValueError("scope pages requires pages")
    regions = target.get("regions")
    if regions is not None:
        if not isinstance(regions, list):
            raise ValueError("regions must be an array")
        for region in regions:
            rect = region.get("rect") if isinstance(region, dict) else None
            if not isinstance(region, dict) or not isinstance(region.get("page"), int):
                raise ValueError("each region needs integer page")
            if not isinstance(rect, list) or len(rect) != 4 or not all(isinstance(x, (int, float)) for x in rect):
                raise ValueError("each region rect must be [x0,y0,x1,y1]")


def is_eligible(page_index, rect, target, boundary):
    page_number = page_index + 1
    if target.get("scope", "before_references") == "before_references" and boundary is not None:
        bpage, by, _ = boundary
        if page_index > bpage or (page_index == bpage and (by is None or rect.y1 > by)):
            return False
    # Without a detected References heading, before_references means all pages;
    # the caller must manually inspect that uncommon case.
    pages = target.get("pages")
    if pages is not None and page_number not in pages:
        return False
    regions = target.get("regions")
    if regions and not any(region["page"] == page_number and
                           intersects(rect, fitz.Rect(region["rect"])) for region in regions):
        return False
    return True


def find_hits(doc, target, boundary):
    found = []
    for pno, page in enumerate(doc):
        for rect in page.search_for(target["text"]):
            rect = fitz.Rect(rect)
            if is_eligible(pno, rect, target, boundary):
                found.append((pno, rect))
    return found


def add(items, text, scope="before_references", **kwargs):
    text = (text or "").strip()
    if len(text) >= 3:
        value = {"text": text, "scope": scope, "required": False, "automatic": True}
        value.update(kwargs)
        items.append(value)


def metadata_author_values(doc):
    author = str((doc.metadata or {}).get("author") or "").strip()
    if not author or author.casefold() in {"anonymous", "unknown", "none"}:
        return []
    return [author] + [x.strip() for x in re.split(r"\s*(?:;|\band\b)\s*", author, flags=re.I) if x.strip()]


def title_material(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    abstract = next((i for i, line in enumerate(lines) if re.match(r"^abstract\b", line, re.I)), len(lines))
    return lines[:abstract]


def automatic_targets(doc, boundary):
    """Find concrete target strings while retaining bibliography-specific strings."""
    targets = []
    texts = [page.get_text("text") for page in doc]

    # Identifier occurrences before References are presumptively the submitted
    # paper's identity leaks. Reference-page occurrences are deliberately excluded.
    for text in texts:
        for pattern in (EMAIL, ARXIV, DOI):
            for match in pattern.finditer(text):
                add(targets, match.group(0))

    first = title_material(texts[0]) if texts else []
    for line in first:
        if AFFILIATION.search(line):
            add(targets, line)
        if VENUE.search(line):
            add(targets, line)

    # Byline candidates are constrained to title material and lines that look
    # like names rather than affiliations, emails, or normal sentence prose.
    for line in first[1:]:
        if AFFILIATION.search(line) or "@" in line or VENUE.search(line):
            continue
        names = NAME.findall(line)
        alpha_words = re.findall(r"[A-Za-z]+", line)
        if names and len(alpha_words) <= 14:
            for name in names:
                add(targets, name)

    for name in metadata_author_values(doc):
        add(targets, name)

    pre_reference = "\n".join(texts)
    if boundary is not None:
        pre_reference = "\n".join(texts[:boundary[0] + 1])
    acknowledgement = re.search(
        r"(?is)\backnowledg(?:e)?ments?\b(.*?)(?=\n\s*(?:\d+\.?\s*)?(?:references|bibliography|appendix)\b|\Z)",
        pre_reference,
    )
    if acknowledgement:
        for thanked in re.finditer(r"(?:thank(?:s)?|grateful to|indebted to)\s+([^.;:]{1,240})",
                                   acknowledgement.group(1), re.I):
            for name in NAME.findall(thanked.group(1)):
                add(targets, name)

    # Venue/acceptance lines outside References may be publicly searchable.
    for text in texts:
        for line in text.splitlines():
            if VENUE.search(line):
                add(targets, line)

    # Preserve bibliographic occurrences, but remove the same direct identifier
    # when it repeats as a running header/footer on later pages.
    direct = {x["text"] for x in targets if EMAIL.fullmatch(x["text"]) or ARXIV.fullmatch(x["text"])}
    direct.update(metadata_author_values(doc))
    for value in sorted(direct):
        regions = []
        for pno, page in enumerate(doc, 1):
            for rect in page.search_for(value):
                if rect.y0 < 72 or rect.y1 > page.rect.height - 72:
                    regions.append({"page": pno, "rect": [float(rect.x0), float(rect.y0),
                                                             float(rect.x1), float(rect.y1)]})
        if regions:
            add(targets, value, "all", regions=regions)

    unique, seen = [], set()
    for target in targets:
        key = (target["text"], target.get("scope"), tuple(target.get("pages") or ()),
               json.dumps(target.get("regions") or [], sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


def clear_metadata(doc):
    # Empty standard document information and remove XMP; output software may add
    # a generic producer, which does not identify an author.
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except (AttributeError, RuntimeError):
        pass


def identity_metadata(doc):
    metadata = doc.metadata or {}
    return {key: str(metadata.get(key) or "") for key in
            ("author", "title", "subject", "keywords", "creator")
            if str(metadata.get(key) or "").strip()}


def tokens(text):
    return [x.casefold() for x in WORDS.findall(text)]


def non_target_words_lost(before, after, targets):
    ignored = set()
    for target in targets:
        ignored.update(tokens(target["text"]))
    prior = Counter(x for x in tokens(before) if x not in ignored)
    later = Counter(x for x in tokens(after) if x not in ignored)
    return sum((prior - later).values())


def process(spec):
    if not isinstance(spec, dict):
        raise ValueError("each document must be an object")
    source, destination = spec.get("input"), spec.get("output")
    if not isinstance(source, str) or not Path(source).is_file():
        raise FileNotFoundError("input PDF does not exist: " + str(source))
    if not isinstance(destination, str) or not destination:
        raise ValueError("output must be a nonempty path")

    document = fitz.open(source)
    temp_name = None
    try:
        boundary = reference_boundary(document)
        supplied = spec.get("targets", [])
        if not isinstance(supplied, list):
            raise ValueError("targets must be an array")
        targets = (automatic_targets(document, boundary) if spec.get("auto_discover", False) else []) + supplied
        for target in targets:
            validate_target(target)
        original_text = "\n".join(page.get_text("text") for page in document)
        hit_lists = [find_hits(document, target, boundary) for target in targets]
        for target, hits in zip(targets, hit_lists):
            if target.get("required", True) and not hits:
                raise ValueError("required target has no eligible exact match: " + repr(target["text"]))

        for hits in hit_lists:
            for page_number, rect in hits:
                document[page_number].add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        for page in document:
            page.apply_redactions()
        metadata_was_cleared = bool(spec.get("clear_metadata", True))
        if metadata_was_cleared:
            clear_metadata(document)

        out_path = Path(destination)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=".redaction-", suffix=".pdf", dir=str(out_path.parent))
        os.close(descriptor)
        document.save(temp_name, garbage=4, deflate=True)
    finally:
        document.close()

    try:
        result, original = fitz.open(temp_name), fitz.open(source)
        try:
            if result.page_count != original.page_count:
                raise ValueError("validation failed: page count changed")
            remaining = []
            for target, hits in zip(targets, hit_lists):
                for page_number, old_rect in hits:
                    if any(intersects(old_rect, now) for now in result[page_number].search_for(target["text"])):
                        remaining.append({"text": target["text"], "page": page_number + 1})
            if remaining:
                raise ValueError("validation failed: selected targets remain: " + json.dumps(remaining, ensure_ascii=False))
            if metadata_was_cleared and identity_metadata(result):
                raise ValueError("validation failed: identifying document metadata remains")
            lost = non_target_words_lost("\n".join(p.get_text("text") for p in original),
                                          "\n".join(p.get_text("text") for p in result), targets)
            if lost > 50:
                raise ValueError("validation failed: %d non-target words disappeared (limit 50)" % lost)
            report = {
                "input": source, "output": destination, "page_count": result.page_count,
                "reference_boundary": None if boundary is None else
                    {"page": boundary[0] + 1, "y": boundary[1], "heading": boundary[2]},
                "redactions": [{"text": target["text"], "matches_redacted": len(hits)}
                               for target, hits in zip(targets, hit_lists)],
                "unmatched_automatic_candidates": [target["text"] for target, hits in zip(targets, hit_lists)
                                                     if target.get("automatic") and not hits],
                "non_target_words_missing": lost,
                "metadata_cleared": metadata_was_cleared,
                "warnings": (["no searchable automatic or manual targets; inspect image-only or already-anonymous source manually"]
                             if not targets else []),
                "valid": True,
            }
        finally:
            original.close()
            result.close()
        os.replace(temp_name, destination)
        temp_name = None
        return report
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main():
    config = json.load(sys.stdin)
    documents = config.get("documents") if isinstance(config, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ValueError("input must contain a nonempty documents array")
    reports = [process(spec) for spec in documents]
    print(json.dumps({"documents": reports, "valid": all(x["valid"] for x in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
