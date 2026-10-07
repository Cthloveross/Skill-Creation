"""Create true-redacted blind-review PDF copies.

Reads JSON from stdin:
{"inputs":["/path/in.pdf"], "output_dir":"/path/out",
 "targets_by_input": {"/path/in.pdf":[{"text":"Reviewed name","scope":"before_references"}]},
 "report_path":"/optional/audit.json"}
Writes a JSON status object to stdout.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    fitz = None
    FITZ_ERROR = str(exc)
else:
    FITZ_ERROR = ""

REF_RE = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(?:references|bibliography)\s*$")
EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
ARXIV_RE = re.compile(r"(?i)\barxiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?\b")
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:a-z0-9]+")
NAME_RE = re.compile(r"\b([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){1,3})\b")
AFFILIATION_RE = re.compile(
    r"(?i)\b(?:university|universit[eé]|institute|institution|department|school of|"
    r"college|laboratory|lab(?:oratory)?|centre|center|research group|inc\.|llc|ltd\.|"
    r"corporation|gmbh)\b"
)
ACK_RE = re.compile(
    r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)"
)
ACK_NAME_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def reference_boundary(texts: list[str]) -> tuple[int | None, int | None]:
    for page_no, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return page_no, match.start()
    return None, None


def pre_reference_text(texts: list[str], ref_page: int | None, ref_offset: int | None) -> str:
    if ref_page is None:
        return "\n".join(texts)
    return "\n".join(texts[:ref_page] + [texts[ref_page][:ref_offset or 0]])


def title_targets(first_page: str) -> set[str]:
    """Return exact byline/affiliation candidates from text preceding Abstract."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [normal(line) for line in zone.splitlines() if normal(line)]
    stop = {"Abstract", "Introduction", "Proceedings", "University", "Department",
            "Institute", "School", "Laboratory", "College", "Corresponding"}
    found: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            if (len(candidate) >= 5 and not any(word in stop for word in candidate.split())
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        # A short title-page correspondence/contribution or publication line can
        # identify an author or a public version of this paper.
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return found


def metadata_author_targets(doc: Any) -> set[str]:
    """Turn plausible Author metadata names into exact text search candidates."""
    raw = normal(str((doc.metadata or {}).get("author") or ""))
    if not raw or raw.casefold() in {"anonymous", "anon", "none"}:
        return set()
    found = {raw}
    for piece in re.split(r"\s*(?:;|\||\band\b)\s*", raw, flags=re.I):
        piece = normal(piece)
        if len(piece) >= 5 and NAME_RE.fullmatch(piece):
            found.add(piece)
    return found


def automatic_targets(doc: Any, texts: list[str], ref_page: int | None,
                      ref_offset: int | None) -> list[str]:
    prefix = pre_reference_text(texts, ref_page, ref_offset)
    found = title_targets(texts[0] if texts else "")
    found.update(metadata_author_targets(doc))
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(prefix))
    acknowledgement = ACK_RE.search(prefix)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)
    for raw_line in prefix.splitlines():
        line = normal(raw_line)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda value: (-len(value), value.casefold()))


def manual_targets(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("targets_by_input values must be arrays")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each target requires nonempty text")
        scope = item.get("scope", "before_references")
        if scope not in {"before_references", "all", "pages"}:
            raise ValueError("target scope must be before_references, all, or pages")
        value: dict[str, Any] = {"text": item["text"], "scope": scope, "origin": "manual"}
        if "pages" in item:
            value["pages"] = item["pages"]
        result.append(value)
    return result


def selected_pages(target: dict[str, Any], page_count: int, ref_page: int | None) -> list[int]:
    scope = target["scope"]
    if scope == "all":
        return list(range(page_count))
    if scope == "before_references":
        return list(range(page_count if ref_page is None else ref_page + 1))
    pages = target.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages scope requires a nonempty pages array")
    unique: list[int] = []
    for page in pages:
        if not isinstance(page, int) or isinstance(page, bool) or page < 0 or page >= page_count:
            raise ValueError("selected page is outside the document")
        if page not in unique:
            unique.append(page)
    return unique


def references_y(doc: Any, ref_page: int | None, page_text: str) -> float | None:
    if ref_page is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    boxes = doc[ref_page].search_for(match.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def redact_one(source_text: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_text)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    doc = fitz.open(str(source))
    try:
        original_count = doc.page_count
        if original_count < 1:
            raise ValueError(f"input has no pages: {source}")
        texts = [page.get_text("text") for page in doc]
        ref_page, ref_offset = reference_boundary(texts)
        ref_y = references_y(doc, ref_page, texts[ref_page]) if ref_page is not None else None
        targets = ([{"text": text, "scope": "before_references", "origin": "automatic"}
                    for text in automatic_targets(doc, texts, ref_page, ref_offset)] + manual)

        # Deduplicate while retaining different scopes, since an explicit manual
        # all-pages target intentionally differs from an automatic pre-ref target.
        unique: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in targets:
            key = (target["text"], target["scope"], tuple(target.get("pages", [])))
            if key not in seen:
                seen.add(key)
                unique.append(target)

        rectangles: dict[int, list[Any]] = {}
        audit: list[dict[str, Any]] = []
        for target in unique:
            matches = 0
            for page_no in selected_pages(target, original_count, ref_page):
                page = doc[page_no]
                for box in page.search_for(target["text"]):
                    # Never let an automatic/pre-reference search enter a
                    # bibliography beginning on the same physical page.
                    if (target["scope"] == "before_references" and page_no == ref_page
                            and ref_y is not None and box.y1 > ref_y + 0.5):
                        continue
                    rectangles.setdefault(page_no, []).append(box)
                    matches += 1
            audit.append({"text": target["text"], "scope": target["scope"],
                          "origin": target["origin"], "rectangles": matches})

        for page_no, boxes in rectangles.items():
            page = doc[page_no]
            for box in boxes:
                page.add_redact_annot(box, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()

        # Clear standard metadata without altering any page content. XMP may retain
        # duplicate author values, so clear it as well when supported by PyMuPDF.
        metadata = dict(doc.metadata or {})
        cleared: list[str] = []
        for key in ("author", "creator", "producer", "title", "subject", "keywords"):
            if metadata.get(key):
                cleared.append(key)
            metadata[key] = ""
        doc.set_metadata(metadata)
        xmp_cleared = False
        if hasattr(doc, "set_xml_metadata"):
            doc.set_xml_metadata("")
            xmp_cleared = True

        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / source.name
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)

        delivered = fitz.open(str(output))
        try:
            delivered_count = delivered.page_count
            readable = delivered_count > 0
        finally:
            delivered.close()
        if delivered_count != original_count:
            raise RuntimeError("output page count differs from input")
        return {
            "input": str(source), "output": str(output), "readable": readable,
            "original_page_count": original_count, "output_page_count": delivered_count,
            "page_count_matches": delivered_count == original_count,
            "references_page_zero_based": ref_page, "metadata_cleared": cleared,
            "xmp_cleared": xmp_cleared, "targets": audit,
            "unmatched_manual_targets": [x["text"] for x in audit
                                         if x["origin"] == "manual" and x["rectangles"] == 0],
            "unmatched_automatic_candidates": [x["text"] for x in audit
                                               if x["origin"] == "automatic" and x["rectangles"] == 0],
        }
    finally:
        if not doc.is_closed:
            doc.close()


def main() -> int:
    try:
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        inputs = request.get("inputs")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) and x for x in inputs):
            raise ValueError("inputs must be a nonempty array of paths")
        out = request.get("output_dir")
        if not isinstance(out, str) or not out:
            raise ValueError("output_dir must be a nonempty path")
        supplied = request.get("targets_by_input", {})
        if not isinstance(supplied, dict):
            raise ValueError("targets_by_input must be an object")
        jobs = [redact_one(source, Path(out), manual_targets(supplied.get(source))) for source in inputs]
        payload: dict[str, Any] = {"status": "ok", "jobs": jobs}
        report = request.get("report_path")
        if report is not None:
            if not isinstance(report, str) or not report:
                raise ValueError("report_path must be a nonempty path")
            report_path = Path(report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload["report_path"] = str(report_path)
        emit(payload)
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
