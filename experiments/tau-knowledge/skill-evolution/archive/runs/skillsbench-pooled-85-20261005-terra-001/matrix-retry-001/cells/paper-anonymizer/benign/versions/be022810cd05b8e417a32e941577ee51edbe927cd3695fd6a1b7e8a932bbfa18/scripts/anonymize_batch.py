"""True, targeted PDF anonymization for blind peer review.

Reads one JSON request from stdin and writes a JSON status object to stdout.
Requires PyMuPDF (the ``fitz`` module).  It changes no source PDF.
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
except Exception as exc:  # pragma: no cover - environment-dependent
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
ACK_RE = re.compile(r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)")
ACK_NAME_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def reference_boundary(texts: list[str]) -> tuple[int | None, int | None]:
    """Return zero-based reference-heading page and its character offset."""
    for number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return number, match.start()
    return None, None


def pre_reference_text(texts: list[str], ref_page: int | None, ref_at: int | None) -> str:
    if ref_page is None:
        return "\n".join(texts)
    return "\n".join(texts[:ref_page] + [texts[ref_page][:ref_at or 0]])


def title_targets(first_page: str) -> set[str]:
    """Conservatively identify exact title-block candidates, not body prose."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [norm(line) for line in zone.splitlines() if norm(line)]
    blocked = {
        "Abstract", "Introduction", "Proceedings", "University", "Department",
        "Institute", "School", "Laboratory", "College", "Corresponding",
    }
    out: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            if (len(candidate) >= 5 and not any(word in blocked for word in candidate.split())
                    and (len(line) <= 180 or line.count(",") >= 1)):
                out.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            out.add(line)
        # These title/footnote statements directly link the manuscript to a public record.
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            out.add(line)
    return out


def metadata_targets(doc: Any) -> set[str]:
    metadata = doc.metadata or {}
    author = norm(str(metadata.get("author") or ""))
    if not author or author.casefold() in {"anonymous", "anon", "none"}:
        return set()
    result = {author}
    for part in re.split(r"\s*(?:;|\||\band\b)\s*", author, flags=re.I):
        part = norm(part)
        if len(part) >= 5 and NAME_RE.fullmatch(part):
            result.add(part)
    return result


def discover_targets(doc: Any, texts: list[str], ref_page: int | None,
                     ref_at: int | None) -> list[str]:
    """Return exact source strings appropriate for the pre-reference scope."""
    prefix = pre_reference_text(texts, ref_page, ref_at)
    found = title_targets(texts[0] if texts else "")
    found.update(metadata_targets(doc))
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(prefix))

    acknowledgement = ACK_RE.search(prefix)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)

    # Retain ordinary prose.  Only a short explicit venue disclosure is removed whole.
    for raw in prefix.splitlines():
        line = norm(raw)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda value: (-len(value), value.casefold()))


def parse_manual(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("targets_by_input values must be arrays")
    parsed: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each target requires nonempty text")
        scope = item.get("scope", "before_references")
        if scope not in {"before_references", "all", "pages"}:
            raise ValueError("target scope must be before_references, all, or pages")
        parsed.append({"text": item["text"], "scope": scope,
                       "pages": item.get("pages"), "origin": "manual"})
    return parsed


def scope_pages(target: dict[str, Any], page_count: int, ref_page: int | None) -> list[int]:
    scope = target["scope"]
    if scope == "all":
        return list(range(page_count))
    if scope == "before_references":
        return list(range(page_count if ref_page is None else ref_page + 1))
    raw = target.get("pages")
    if not isinstance(raw, list) or not raw:
        raise ValueError("pages scope requires a nonempty pages array")
    pages: list[int] = []
    for page in raw:
        if not isinstance(page, int) or isinstance(page, bool) or page < 0 or page >= page_count:
            raise ValueError("selected page is outside the document")
        if page not in pages:
            pages.append(page)
    return pages


def heading_y(doc: Any, page_number: int | None, page_text: str) -> float | None:
    if page_number is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    boxes = doc[page_number].search_for(match.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def anonymize_one(source_text: str, output_dir: Path, reviewed: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_text)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    doc = fitz.open(str(source))
    temporary: Path | None = None
    try:
        original_pages = doc.page_count
        if original_pages < 1:
            raise ValueError(f"input has no pages: {source}")
        texts = [page.get_text("text") for page in doc]
        ref_page, ref_at = reference_boundary(texts)
        ref_y = heading_y(doc, ref_page, texts[ref_page]) if ref_page is not None else None
        automatic = [
            {"text": text, "scope": "before_references", "pages": None, "origin": "automatic"}
            for text in discover_targets(doc, texts, ref_page, ref_at)
        ]

        targets: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in automatic + reviewed:
            key = (target["text"], target["scope"], tuple(target.get("pages") or []))
            if key not in seen:
                seen.add(key)
                targets.append(target)

        pending: dict[int, list[Any]] = {}
        audit: list[dict[str, Any]] = []
        for target in targets:
            hits = 0
            for page_number in scope_pages(target, original_pages, ref_page):
                page = doc[page_number]
                for box in page.search_for(target["text"]):
                    # On a mixed final-body/reference page, do not touch bibliography material.
                    if (target["scope"] == "before_references" and page_number == ref_page
                            and ref_y is not None and box.y1 > ref_y + 0.5):
                        continue
                    pending.setdefault(page_number, []).append(box)
                    hits += 1
            audit.append({"text": target["text"], "scope": target["scope"],
                          "origin": target["origin"], "rectangles": hits})

        for page_number, boxes in pending.items():
            page = doc[page_number]
            for box in boxes:
                page.add_redact_annot(box, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()

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
        temporary = None

        delivered = fitz.open(str(output))
        try:
            output_pages = delivered.page_count
            readable = output_pages > 0
        finally:
            delivered.close()
        if not readable or output_pages != original_pages:
            raise RuntimeError("saved output is unreadable or its page count changed")
        return {
            "input": str(source), "output": str(output), "readable": True,
            "original_page_count": original_pages, "output_page_count": output_pages,
            "page_count_matches": True, "references_page_zero_based": ref_page,
            "metadata_cleared": cleared, "xmp_cleared": xmp_cleared, "targets": audit,
            "unmatched_manual_targets": [x["text"] for x in audit if x["origin"] == "manual" and x["rectangles"] == 0],
            "unmatched_automatic_candidates": [x["text"] for x in audit if x["origin"] == "automatic" and x["rectangles"] == 0],
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
        output_dir_value = request.get("output_dir")
        if not isinstance(output_dir_value, str) or not output_dir_value:
            raise ValueError("output_dir must be a nonempty path")
        manual_map = request.get("targets_by_input", {})
        if not isinstance(manual_map, dict):
            raise ValueError("targets_by_input must be an object")

        jobs = [anonymize_one(source, Path(output_dir_value), parse_manual(manual_map.get(source)))
                for source in inputs]
        payload: dict[str, Any] = {"status": "ok", "jobs": jobs}
        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path")
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload["report_path"] = str(report)
        emit(payload)
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
