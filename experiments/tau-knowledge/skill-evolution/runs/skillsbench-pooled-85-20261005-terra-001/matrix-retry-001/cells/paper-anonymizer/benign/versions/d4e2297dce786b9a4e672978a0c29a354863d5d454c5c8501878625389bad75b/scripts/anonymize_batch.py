"""Create true-redacted PDFs for blind review.

Read one JSON request from stdin and emit an audit JSON object on stdout.

{
  "inputs": ["/path/source.pdf"],
  "output_dir": "/path/redacted",
  "targets_by_input": {
    "/path/source.pdf": [
      {"text": "Exact reviewed string", "scope": "before_references"}
    ]
  },
  "report_path": "/optional/audit.json"
}
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
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def reference_location(texts: list[str]) -> tuple[int | None, int | None]:
    for page_number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return page_number, match.start()
    return None, None


def text_before_references(texts: list[str], ref_page: int | None, ref_offset: int | None) -> str:
    result: list[str] = []
    for number, text in enumerate(texts):
        if ref_page is None or number < ref_page:
            result.append(text)
        elif number == ref_page:
            result.append(text[:ref_offset])
            break
        else:
            break
    return "\n".join(result)


def title_targets(first_page: str) -> set[str]:
    """Return concrete title-matter identity candidates, never rectangular regions."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [normalize(line) for line in zone.splitlines() if normalize(line)]
    stop_words = {"Abstract", "Introduction", "Proceedings", "University", "Department",
                  "Institute", "School", "Laboratory", "College", "Corresponding"}
    targets: set[str] = set()
    for line in lines:
        for name in NAME_RE.findall(line):
            if (len(name) >= 5 and not any(word in stop_words for word in name.split())
                    and (len(line) <= 180 or line.count(",") >= 1)):
                targets.add(name)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            targets.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            targets.add(line)
    return targets


def automatic_targets(texts: list[str], ref_page: int | None, ref_offset: int | None) -> list[str]:
    """Discover exact, narrowly scoped identity strings outside the bibliography."""
    before_refs = text_before_references(texts, ref_page, ref_offset)
    targets = title_targets(texts[0] if texts else "")
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        targets.update(match.group(0) for match in pattern.finditer(before_refs))

    acknowledgement = re.search(
        r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)",
        before_refs,
    )
    if acknowledgement:
        for name in ACK_NAME_RE.findall(acknowledgement.group(1)):
            name = re.sub(r"\s+and\s+", " and ", name).strip()
            if len(name) >= 5:
                targets.add(name)

    for raw_line in before_refs.splitlines():
        line = normalize(raw_line)
        if VENUE_RE.search(line) and len(line) <= 300:
            targets.add(line)
    return sorted(targets, key=lambda item: (-len(item), item.casefold()))


def validate_manual(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("targets_by_input values must be arrays")
    targets: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each manual target requires nonempty text")
        target: dict[str, Any] = {"text": item["text"], "scope": item.get("scope", "before_references")}
        if "pages" in item:
            target["pages"] = item["pages"]
        targets.append(target)
    return targets


def target_pages(target: dict[str, Any], page_count: int, ref_page: int | None) -> list[int]:
    scope = target.get("scope", "before_references")
    if scope == "all":
        return list(range(page_count))
    if scope == "before_references":
        return list(range(page_count if ref_page is None else ref_page + 1))
    if scope != "pages":
        raise ValueError("target scope must be before_references, pages, or all")
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


def references_top(document: Any, ref_page: int | None, page_text: str) -> float | None:
    if ref_page is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    boxes = document[ref_page].search_for(match.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def allowed_box(box: Any, page_number: int, target: dict[str, Any], ref_page: int | None,
                ref_top: float | None) -> bool:
    if target.get("scope", "before_references") == "before_references" and page_number == ref_page:
        return ref_top is None or box.y1 <= ref_top + 0.5
    return True


def redact_one(source_name: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_name)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source_name}")
    document = fitz.open(str(source))
    try:
        texts = [page.get_text("text") for page in document]
        original_pages = document.page_count
        ref_page, ref_offset = reference_location(texts)
        ref_top = references_top(document, ref_page, texts[ref_page]) if ref_page is not None else None
        targets = ([{"text": text, "scope": "before_references", "origin": "automatic"}
                    for text in automatic_targets(texts, ref_page, ref_offset)]
                   + [{**item, "origin": "manual"} for item in manual])

        distinct: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in targets:
            key = (target["text"], target.get("scope", "before_references"), tuple(target.get("pages", [])))
            if key not in seen:
                seen.add(key)
                distinct.append(target)

        boxes_by_page: dict[int, list[Any]] = {}
        audited: list[dict[str, Any]] = []
        for target in distinct:
            matches = 0
            for page_number in target_pages(target, original_pages, ref_page):
                # Every box below comes from an exact string search, not a guessed area.
                for box in document[page_number].search_for(target["text"]):
                    if allowed_box(box, page_number, target, ref_page, ref_top):
                        boxes_by_page.setdefault(page_number, []).append(box)
                        matches += 1
            audited.append({"text": target["text"], "scope": target.get("scope", "before_references"),
                            "origin": target["origin"], "rectangles": matches})

        for page_number, boxes in boxes_by_page.items():
            page = document[page_number]
            for box in boxes:
                page.add_redact_annot(box, fill=(1, 1, 1), cross_out=False)
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
            "input": source_name, "output": str(output), "readable": readable,
            "original_page_count": original_pages, "output_page_count": delivered_pages,
            "page_count_matches": original_pages == delivered_pages,
            "references_page_zero_based": ref_page, "metadata_cleared": cleared,
            "xmp_cleared": xmp_cleared, "targets": audited,
            "unmatched_manual_targets": [x["text"] for x in audited if x["origin"] == "manual" and x["rectangles"] == 0],
            "unmatched_automatic_candidates": [x["text"] for x in audited if x["origin"] == "automatic" and x["rectangles"] == 0],
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
        if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) and x for x in inputs):
            raise ValueError("inputs must be a nonempty array of PDF paths")
        output_dir = request.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a nonempty path")
        supplied = request.get("targets_by_input", {})
        if not isinstance(supplied, dict):
            raise ValueError("targets_by_input must be an object")
        jobs = [redact_one(path, Path(output_dir), validate_manual(supplied.get(path))) for path in inputs]
        status = "ok" if all(job["readable"] and job["page_count_matches"] for job in jobs) else "error"
        payload: dict[str, Any] = {"status": status, "jobs": jobs}
        report = request.get("report_path")
        if report is not None:
            if not isinstance(report, str) or not report:
                raise ValueError("report_path must be a nonempty path")
            destination = Path(report)
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
