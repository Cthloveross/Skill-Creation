"""Create blind-review PDF copies using only exact text-search redactions.

stdin JSON schema:
{
  "inputs": ["/path/source.pdf", ...],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed text", "scope": "before_references"},
      {"text": "Repeated own ID", "scope": "pages", "pages": [0, 4]},
      {"text": "Unique own ID", "scope": "all"}
    ]
  },
  "report_path": "/optional/audit.json"
}

The output for each input is output_dir / basename(input). stdout is a JSON audit.
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
except Exception as exc:  # pragma: no cover - runtime prerequisite reporting
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
    r"(?i)\b(?:university|universit[eé]|institute|institution|department|"
    r"school of|college|laboratory|lab(?:oratory)?|centre|center|research group|"
    r"inc\.|llc|ltd\.|corporation|gmbh)\b"
)
ACK_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_request() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("stdin JSON must be an object")
    return value


def page_texts(doc: Any) -> list[str]:
    return [page.get_text("text") for page in doc]


def reference_position(texts: list[str]) -> tuple[int | None, int | None]:
    """Return first reference page and character start within that page."""
    for number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return number, match.start()
    return None, None


def title_candidates(first_text: str) -> list[str]:
    abstract = re.search(r"(?im)^\s*abstract\b", first_text)
    zone = first_text[:abstract.start()] if abstract else first_text[:2500]
    lines = [norm(line) for line in zone.splitlines() if norm(line)]
    found: set[str] = set()
    stop = {"Abstract", "Introduction", "Proceedings", "University", "Department",
            "Institute", "School", "Laboratory", "College", "Corresponding"}
    for line in lines:
        for candidate in NAME_RE.findall(line):
            if (not any(word in stop for word in candidate.split()) and len(candidate) >= 5
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        # These short title-matter lines can disclose a correspondence role or an
        # accepted venue. They are concrete extracted strings, never page regions.
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda item: (-len(item), item))


def automatic_targets(texts: list[str], ref_page: int | None, ref_char: int | None) -> list[str]:
    """Build an exact-string discovery list from non-bibliography text."""
    pre_parts: list[str] = []
    for page_no, text in enumerate(texts):
        if ref_page is None or page_no < ref_page:
            pre_parts.append(text)
        elif page_no == ref_page:
            pre_parts.append(text[:ref_char])
            break
        else:
            break
    pre_text = "\n".join(pre_parts)
    found: set[str] = set(title_candidates(texts[0] if texts else ""))
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(pre_text))

    # Read acknowledgement-context phrases rather than treating every proper noun
    # in the paper as a name. Human review can supply additional unusual wording.
    acknowledgement = re.search(
        r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)",
        pre_text,
    )
    if acknowledgement:
        for candidate in ACK_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)

    # A standalone accepted/publication line outside the title block is also an
    # indirect identity leak; limit it to short, explicit statements.
    for line in pre_text.splitlines():
        line = norm(line)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda item: (-len(item), item.casefold()))


def checked_pages(target: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    scope = target.get("scope", "before_references")
    if scope == "all":
        return list(range(count))
    if scope == "before_references":
        # Include a References page for only its content above the heading; the
        # rectangle filter in allowed_rect excludes bibliography entries.
        return list(range(count if ref_page is None else ref_page + 1))
    if scope == "pages":
        pages = target.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("pages scope requires a nonempty pages array")
        result: list[int] = []
        for page in pages:
            if not isinstance(page, int) or isinstance(page, bool) or not 0 <= page < count:
                raise ValueError("selected page is outside the document")
            if page not in result:
                result.append(page)
        return result
    raise ValueError("target scope must be before_references, pages, or all")


def heading_top(doc: Any, ref_page: int | None, text: str) -> float | None:
    if ref_page is None:
        return None
    match = REF_RE.search(text)
    if not match:
        return None
    label = match.group(0).strip()
    rectangles = doc[ref_page].search_for(label)
    return min((rect.y0 for rect in rectangles), default=None)


def allowed_rect(rect: Any, page_no: int, target: dict[str, Any], ref_page: int | None,
                 ref_top: float | None) -> bool:
    # An automatic/default before_references target must not touch the bibliography
    # when the heading begins partway down its page.
    if target.get("scope", "before_references") == "before_references" and page_no == ref_page:
        return ref_top is None or rect.y1 <= ref_top + 0.5
    return True


def validate_extra(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("targets_by_input values must be arrays")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each manual target needs a nonempty text string")
        target = {"text": item["text"], "scope": item.get("scope", "before_references")}
        if "pages" in item:
            target["pages"] = item["pages"]
        result.append(target)
    return result


def redact_one(input_path: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    if not Path(input_path).is_file():
        raise ValueError(f"input file does not exist: {input_path}")
    doc = fitz.open(input_path)
    try:
        texts = page_texts(doc)
        original_pages = doc.page_count
        ref_page, ref_char = reference_position(texts)
        ref_top = heading_top(doc, ref_page, texts[ref_page]) if ref_page is not None else None
        automatic = automatic_targets(texts, ref_page, ref_char)
        targets = [{"text": text, "scope": "before_references", "origin": "automatic"}
                   for text in automatic]
        targets.extend({**target, "origin": "manual"} for target in manual)

        # Deduplicate only identical text/scope/page selections, retaining audit
        # provenance in the first record. Locate all rectangles before modifying a
        # page so every search is performed against the original content stream.
        unique: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in targets:
            key = (target["text"], target.get("scope", "before_references"),
                   tuple(target.get("pages", [])))
            if key not in seen:
                seen.add(key)
                unique.append(target)

        page_rects: dict[int, list[Any]] = {}
        audit_targets: list[dict[str, Any]] = []
        for target in unique:
            rectangles = 0
            for page_no in checked_pages(target, original_pages, ref_page):
                for rect in doc[page_no].search_for(target["text"]):
                    if allowed_rect(rect, page_no, target, ref_page, ref_top):
                        page_rects.setdefault(page_no, []).append(rect)
                        rectangles += 1
            audit_targets.append({"text": target["text"], "scope": target.get("scope", "before_references"),
                                  "origin": target["origin"], "rectangles": rectangles})

        for page_no, rectangles in page_rects.items():
            page = doc[page_no]
            for rect in rectangles:
                page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()

        metadata = dict(doc.metadata or {})
        cleared: list[str] = []
        for key in ("author", "creator", "subject", "keywords"):
            if key in metadata:
                metadata[key] = ""
                cleared.append(key)
        doc.set_metadata(metadata)
        xmp_cleared = False
        if hasattr(doc, "set_xml_metadata"):
            doc.set_xml_metadata("")
            xmp_cleared = True

        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / Path(input_path).name
        temporary = output.with_name(output.name + ".anonymizing.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)

        # Reopen so the report describes the delivered artifact, not in-memory data.
        delivered = fitz.open(str(output))
        try:
            readable = delivered.page_count > 0
            delivered_pages = delivered.page_count
        finally:
            delivered.close()
        unmatched_manual = [item["text"] for item in audit_targets
                            if item["origin"] == "manual" and item["rectangles"] == 0]
        return {
            "input": input_path,
            "output": str(output),
            "readable": readable,
            "original_page_count": original_pages,
            "output_page_count": delivered_pages,
            "page_count_matches": original_pages == delivered_pages,
            "references_page_zero_based": ref_page,
            "metadata_cleared": cleared,
            "xmp_cleared": xmp_cleared,
            "targets": audit_targets,
            "unmatched_manual_targets": unmatched_manual,
            "unmatched_automatic_candidates": [item["text"] for item in audit_targets
                                                 if item["origin"] == "automatic" and item["rectangles"] == 0],
        }
    finally:
        if not doc.is_closed:
            doc.close()


def main() -> int:
    try:
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        request = read_request()
        inputs = request.get("inputs")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(path, str) and path for path in inputs):
            raise ValueError("inputs must be a nonempty array of PDF path strings")
        output_value = request.get("output_dir")
        if not isinstance(output_value, str) or not output_value:
            raise ValueError("output_dir must be a nonempty path string")
        supplied = request.get("targets_by_input", {})
        if not isinstance(supplied, dict):
            raise ValueError("targets_by_input must be an object when supplied")
        output_dir = Path(output_value)
        jobs = [redact_one(path, output_dir, validate_extra(supplied.get(path))) for path in inputs]
        status = "ok" if all(job["readable"] and job["page_count_matches"] for job in jobs) else "error"
        payload = {"status": status, "jobs": jobs}
        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path string")
            destination = Path(report_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload["report_path"] = str(destination)
        emit(payload)
        return 0 if status == "ok" else 2
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
