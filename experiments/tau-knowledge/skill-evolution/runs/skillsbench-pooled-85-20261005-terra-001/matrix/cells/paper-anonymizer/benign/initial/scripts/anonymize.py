#!/usr/bin/env python3
"""Apply reviewed exact-string redactions and validate the resulting PDFs.

stdin schema:
{
  "documents": [{
    "input": "source.pdf", "output": "redacted.pdf", "clear_metadata": true,
    "targets": [{"text": "exact target", "scope": "before_references|pages|all",
                 "pages": [1], "regions": [{"page": 1, "rect": [x0,y0,x1,y1]}],
                 "required": true}]
  }]
}
stdout: a JSON validation report.  The script never discovers or guesses names.
"""
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

REF_HEADING_RE = re.compile(r"^\s*(?:\d+\.?\s+)?(?:references|bibliography)\s*$", re.I)
WORD_RE = re.compile(r"\b[\w]+(?:[’'\-][\w]+)*\b", re.UNICODE)


def reference_boundary(doc):
    for index, page in enumerate(doc):
        for line in page.get_text("text").splitlines():
            heading = line.strip()
            if REF_HEADING_RE.match(heading):
                rects = page.search_for(heading)
                if rects:
                    return (index, float(rects[0].y0), heading)
                return (index, None, heading)
    return None


def rect_intersects(a, b):
    return not (a.x1 <= b.x0 or b.x1 <= a.x0 or a.y1 <= b.y0 or b.y1 <= a.y0)


def validate_target(target):
    if not isinstance(target, dict) or not isinstance(target.get("text"), str) or not target["text"].strip():
        raise ValueError("each target requires a nonempty string text")
    scope = target.get("scope", "before_references")
    if scope not in ("before_references", "pages", "all"):
        raise ValueError("target scope must be before_references, pages, or all")
    pages = target.get("pages")
    if pages is not None and (not isinstance(pages, list) or not all(isinstance(p, int) and p > 0 for p in pages)):
        raise ValueError("target pages must be an array of positive one-based integers")
    regions = target.get("regions")
    if regions is not None:
        if not isinstance(regions, list):
            raise ValueError("target regions must be an array")
        for region in regions:
            if not isinstance(region, dict) or not isinstance(region.get("page"), int):
                raise ValueError("each region needs integer page and rect")
            rect = region.get("rect")
            if not isinstance(rect, list) or len(rect) != 4 or not all(isinstance(v, (int, float)) for v in rect):
                raise ValueError("each region rect must be [x0,y0,x1,y1]")


def eligible(page_index, rect, target, boundary):
    """Filter search hits; this never creates a redaction without an exact hit."""
    pno = page_index + 1
    scope = target.get("scope", "before_references")
    if scope == "before_references":
        if boundary is None:
            # Without a known boundary, silent broad coverage risks a bibliography.
            return False
        boundary_page, boundary_y, _ = boundary
        if page_index > boundary_page:
            return False
        if page_index == boundary_page:
            if boundary_y is None or rect.y1 > boundary_y:
                return False
    elif scope == "pages" and not target.get("pages"):
        raise ValueError("scope pages requires a nonempty pages array")
    allowed_pages = target.get("pages")
    if allowed_pages is not None and pno not in allowed_pages:
        return False
    regions = target.get("regions")
    if regions:
        accepted = False
        for region in regions:
            if region["page"] == pno and rect_intersects(rect, fitz.Rect(region["rect"])):
                accepted = True
                break
        if not accepted:
            return False
    return True


def find_selected_hits(doc, target, boundary):
    selected = []
    for page_index, page in enumerate(doc):
        for rect in page.search_for(target["text"]):
            if eligible(page_index, rect, target, boundary):
                selected.append((page_index, fitz.Rect(rect)))
    return selected


def normalized_words(text):
    return [w.casefold() for w in WORD_RE.findall(text)]


def metadata_is_blank(doc):
    meta = doc.metadata or {}
    identity_keys = ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate")
    return {k: meta.get(k) for k in identity_keys if str(meta.get(k) or "").strip()}


def clear_identity_metadata(doc):
    meta = dict(doc.metadata or {})
    for key in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate", "trapped"):
        if key in meta:
            meta[key] = ""
    doc.set_metadata(meta)
    # XMP may duplicate Author or Creator even when document-info fields are blank.
    try:
        doc.del_xml_metadata()
    except AttributeError:
        pass


def validate_preservation(original_text, redacted_text, targets):
    ignored = set()
    for target in targets:
        ignored.update(normalized_words(target["text"]))
    before = Counter(w for w in normalized_words(original_text) if w not in ignored)
    after = Counter(w for w in normalized_words(redacted_text) if w not in ignored)
    missing = sum((before - after).values())
    return missing


def process_document(spec):
    if not isinstance(spec, dict):
        raise ValueError("each documents entry must be an object")
    source = spec.get("input")
    destination = spec.get("output")
    targets = spec.get("targets")
    if not isinstance(source, str) or not Path(source).is_file():
        raise FileNotFoundError("document input does not exist: " + str(source))
    if not isinstance(destination, str) or not destination:
        raise ValueError("document output must be a path string")
    if not isinstance(targets, list) or not targets:
        raise ValueError("document targets must be a nonempty reviewed list")
    for target in targets:
        validate_target(target)

    original = fitz.open(source)
    temporary_name = None
    try:
        boundary = reference_boundary(original)
        # `before_references` is unsafe without a boundary unless the user chose a
        # reviewed explicit page/region selection. The latter still supplies scope context.
        if boundary is None:
            for target in targets:
                if target.get("scope", "before_references") == "before_references" and not target.get("pages") and not target.get("regions"):
                    raise ValueError("no References heading found; use reviewed pages/regions instead of unrestricted before_references")

        original_text = "\n".join(page.get_text("text") for page in original)
        selected_by_target = []
        for target in targets:
            hits = find_selected_hits(original, target, boundary)
            if target.get("required", True) and not hits:
                raise ValueError("required target had no eligible exact match: " + repr(target["text"]))
            selected_by_target.append(hits)

        for hits in selected_by_target:
            for page_index, rect in hits:
                # The rectangle originates exclusively from page.search_for(text).
                original[page_index].add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        for page in original:
            page.apply_redactions()
        if spec.get("clear_metadata", True):
            clear_identity_metadata(original)

        output_path = Path(destination)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".redaction-", suffix=".pdf", dir=str(output_path.parent))
        os.close(fd)
        original.save(temporary_name, garbage=4, deflate=True)
    finally:
        original.close()

    try:
        result = fitz.open(temporary_name)
        try:
            original_check = fitz.open(source)
            try:
                if result.page_count != original_check.page_count:
                    raise ValueError("validation failed: page count changed")
                remaining = []
                # Search output, then compare to the exact original selected rectangles.
                # Unselected reference occurrences are permitted and do not cause failure.
                for target, old_hits in zip(targets, selected_by_target):
                    for page_index, old_rect in old_hits:
                        now = result[page_index].search_for(target["text"])
                        if any(rect_intersects(old_rect, new_rect) for new_rect in now):
                            remaining.append({"text": target["text"], "page": page_index + 1})
                if remaining:
                    raise ValueError("validation failed: selected targets remain: " + json.dumps(remaining, ensure_ascii=False))
                if spec.get("clear_metadata", True):
                    leaked_meta = metadata_is_blank(result)
                    if leaked_meta:
                        raise ValueError("validation failed: identity metadata remains: " + repr(leaked_meta))
                missing_words = validate_preservation(
                    "\n".join(p.get_text("text") for p in original_check),
                    "\n".join(p.get_text("text") for p in result),
                    targets,
                )
                if missing_words > 50:
                    raise ValueError("validation failed: %d non-target words disappeared (limit 50)" % missing_words)
                report = {
                    "input": source,
                    "output": destination,
                    "page_count": result.page_count,
                    "reference_boundary": (None if boundary is None else {"page": boundary[0] + 1, "y": boundary[1], "heading": boundary[2]}),
                    "redactions": [
                        {"text": target["text"], "matches_redacted": len(hits)}
                        for target, hits in zip(targets, selected_by_target)
                    ],
                    "non_target_words_missing": missing_words,
                    "metadata_cleared": bool(spec.get("clear_metadata", True)),
                    "valid": True,
                }
            finally:
                original_check.close()
        finally:
            result.close()
        os.replace(temporary_name, destination)
        temporary_name = None
        return report
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main():
    config = json.load(sys.stdin)
    documents = config.get("documents") if isinstance(config, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ValueError("input JSON must contain a nonempty documents array")
    reports = [process_document(spec) for spec in documents]
    print(json.dumps({"documents": reports, "valid": all(r["valid"] for r in reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
