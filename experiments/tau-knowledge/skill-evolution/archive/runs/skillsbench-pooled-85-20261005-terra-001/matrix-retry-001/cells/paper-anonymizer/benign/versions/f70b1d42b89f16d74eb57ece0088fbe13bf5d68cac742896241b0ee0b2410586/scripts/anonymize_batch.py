"""True-redact supplied PDFs for blind review.

stdin JSON:
{
  "inputs": ["/path/input.pdf", ...],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/input.pdf": [
      {"text": "Exact reviewed text", "scope": "before_references"},
      {"text": "Reviewed repeated string", "scope": "pages", "pages": [0, 2]},
      {"text": "All-page paper-owned leak", "scope": "all"}
    ]
  },
  "report_path": "/optional/audit.json"
}

Outputs are output_dir / basename(input). stdout is one JSON audit object.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import fitz
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
ACK_NAME_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def reference_position(texts: list[str]) -> tuple[int | None, int | None]:
    """Return the first References page and heading character offset."""
    for page_number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return page_number, match.start()
    return None, None


def pre_reference_text(texts: list[str], ref_page: int | None, ref_char: int | None) -> str:
    parts: list[str] = []
    for page_number, text in enumerate(texts):
        if ref_page is None or page_number < ref_page:
            parts.append(text)
        elif page_number == ref_page:
            parts.append(text[:ref_char])
            break
        else:
            break
    return "\n".join(parts)


def title_block_candidates(first_page: str) -> set[str]:
    """Return exact author/affiliation/title-matter strings, not page regions."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [normalized(line) for line in zone.splitlines() if normalized(line)]
    stop_words = {
        "Abstract", "Introduction", "Proceedings", "University", "Department",
        "Institute", "School", "Laboratory", "College", "Corresponding",
    }
    found: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            if (len(candidate) >= 5 and not any(word in stop_words for word in candidate.split())
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return found


def discovered_targets(texts: list[str], ref_page: int | None, ref_char: int | None) -> list[str]:
    """Discover narrowly-scoped concrete identity strings outside bibliography."""
    pre_text = pre_reference_text(texts, ref_page, ref_char)
    found = title_block_candidates(texts[0] if texts else "")
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(pre_text))

    acknowledgement = re.search(
        r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)",
        pre_text,
    )
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)

    for raw_line in pre_text.splitlines():
        line = normalized(raw_line)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda value: (-len(value), value.casefold()))


def validate_manual(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("targets_by_input values must be arrays")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("every manual target requires a nonempty text string")
        target: dict[str, Any] = {"text": item["text"], "scope": item.get("scope", "before_references")}
        if "pages" in item:
            target["pages"] = item["pages"]
        result.append(target)
    return result


def pages_for_target(target: dict[str, Any], page_count: int, ref_page: int | None) -> list[int]:
    scope = target.get("scope", "before_references")
    if scope == "all":
        return list(range(page_count))
    if scope == "before_references":
        return list(range(page_count if ref_page is None else ref_page + 1))
    if scope != "pages":
        raise ValueError("target scope must be before_references, pages, or all")
    raw_pages = target.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("pages scope requires a nonempty pages array")
    result: list[int] = []
    for page in raw_pages:
        if not isinstance(page, int) or isinstance(page, bool) or not 0 <= page < page_count:
            raise ValueError("selected page is outside the document")
        if page not in result:
            result.append(page)
    return result


def references_heading_top(doc: Any, page_number: int | None, page_text: str) -> float | None:
    if page_number is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    rectangles = doc[page_number].search_for(match.group(0).strip())
    return min((rectangle.y0 for rectangle in rectangles), default=None)


def rectangle_allowed(rect: Any, page_number: int, target: dict[str, Any], ref_page: int | None,
                      ref_top: float | None) -> bool:
    """Keep default targets above a References heading sharing their page."""
    if target.get("scope", "before_references") == "before_references" and page_number == ref_page:
        return ref_top is None or rect.y1 <= ref_top + 0.5
    return True


def redact_one(input_path: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(input_path)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {input_path}")
    document = fitz.open(str(source))
    try:
        texts = [page.get_text("text") for page in document]
        page_count = document.page_count
        ref_page, ref_char = reference_position(texts)
        ref_top = references_heading_top(document, ref_page, texts[ref_page]) if ref_page is not None else None

        targets: list[dict[str, Any]] = [
            {"text": text, "scope": "before_references", "origin": "automatic"}
            for text in discovered_targets(texts, ref_page, ref_char)
        ]
        targets.extend({**target, "origin": "manual"} for target in manual)

        unique: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in targets:
            key = (target["text"], target.get("scope", "before_references"), tuple(target.get("pages", [])))
            if key not in seen:
                seen.add(key)
                unique.append(target)

        rectangles_by_page: dict[int, list[Any]] = {}
        audit_targets: list[dict[str, Any]] = []
        for target in unique:
            count = 0
            for page_number in pages_for_target(target, page_count, ref_page):
                for rectangle in document[page_number].search_for(target["text"]):
                    if rectangle_allowed(rectangle, page_number, target, ref_page, ref_top):
                        rectangles_by_page.setdefault(page_number, []).append(rectangle)
                        count += 1
            audit_targets.append({
                "text": target["text"], "scope": target.get("scope", "before_references"),
                "origin": target["origin"], "rectangles": count,
            })

        # Search results were collected before modifications. Apply actual PDF
        # redactions, never a visual overlay, once for each affected page.
        for page_number, rectangles in rectangles_by_page.items():
            page = document[page_number]
            for rectangle in rectangles:
                page.add_redact_annot(rectangle, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()

        metadata = dict(document.metadata or {})
        cleared: list[str] = []
        for key in ("author", "creator", "subject", "keywords"):
            if key in metadata:
                metadata[key] = ""
                cleared.append(key)
        document.set_metadata(metadata)
        xmp_cleared = False
        if hasattr(document, "set_xml_metadata"):
            document.set_xml_metadata("")
            xmp_cleared = True

        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / source.name
        temporary = output.with_name(output.name + ".anonymizing.tmp.pdf")
        temporary.unlink(missing_ok=True)
        document.save(str(temporary), garbage=4, deflate=True)
        document.close()
        os.replace(temporary, output)

        delivered = fitz.open(str(output))
        try:
            delivered_pages = delivered.page_count
            readable = delivered_pages > 0
        finally:
            delivered.close()

        return {
            "input": input_path,
            "output": str(output),
            "readable": readable,
            "original_page_count": page_count,
            "output_page_count": delivered_pages,
            "page_count_matches": page_count == delivered_pages,
            "references_page_zero_based": ref_page,
            "metadata_cleared": cleared,
            "xmp_cleared": xmp_cleared,
            "targets": audit_targets,
            "unmatched_manual_targets": [
                item["text"] for item in audit_targets
                if item["origin"] == "manual" and item["rectangles"] == 0
            ],
            "unmatched_automatic_candidates": [
                item["text"] for item in audit_targets
                if item["origin"] == "automatic" and item["rectangles"] == 0
            ],
        }
    finally:
        if not document.is_closed:
            document.close()


def main() -> int:
    try:
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        inputs = request.get("inputs")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(value, str) and value for value in inputs):
            raise ValueError("inputs must be a nonempty array of PDF path strings")
        output_value = request.get("output_dir")
        if not isinstance(output_value, str) or not output_value:
            raise ValueError("output_dir must be a nonempty path string")
        supplied = request.get("targets_by_input", {})
        if not isinstance(supplied, dict):
            raise ValueError("targets_by_input must be an object when supplied")

        jobs = [redact_one(path, Path(output_value), validate_manual(supplied.get(path))) for path in inputs]
        status = "ok" if all(job["readable"] and job["page_count_matches"] for job in jobs) else "error"
        payload: dict[str, Any] = {"status": status, "jobs": jobs}

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
