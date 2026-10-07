"""Create page-preserving, applied PDF redactions for blind peer review.

JSON stdin schema:
  {"inputs": [PDF_PATH, ...], "output_dir": DIR,
   "targets_by_input": {PDF_PATH: [{"text": TEXT, "scope": SCOPE,
                                      "pages": [ZERO_BASED_PAGE, ...]}]},
   "report_path": OPTIONAL_JSON_PATH}

Outputs one JSON result on stdout. Requires PyMuPDF (fitz). Existing source files
are read only; each result is written under output_dir using the source basename.
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
except Exception as exc:  # pragma: no cover - depends on executor environment
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
    r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)"
)
ACK_NAME_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def reference_boundary(page_texts: list[str]) -> tuple[int | None, int | None]:
    """Return the page and character offset at the first bibliography heading."""
    for page_number, text in enumerate(page_texts):
        hit = REF_RE.search(text)
        if hit:
            return page_number, hit.start()
    return None, None


def before_references_text(
    page_texts: list[str], reference_page: int | None, reference_offset: int | None
) -> str:
    if reference_page is None:
        return "\n".join(page_texts)
    return "\n".join(page_texts[:reference_page] + [page_texts[reference_page][:reference_offset or 0]])


def title_block_candidates(first_page: str) -> set[str]:
    """Collect conservative, exact title-block strings rather than page regions."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    title_zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [normalized(line) for line in title_zone.splitlines() if normalized(line)]
    excluded = {
        "Abstract", "Introduction", "Proceedings", "University", "Department",
        "Institute", "School", "Laboratory", "College", "Corresponding",
    }
    found: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            words = candidate.split()
            # Short capitalized byline fragments are candidates; this deliberately
            # avoids global person-name matching in scientific prose.
            if (len(candidate) >= 5 and not any(word in excluded for word in words)
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return found


def repeated_direct_identifier_candidates(page_texts: list[str], direct: set[str]) -> set[str]:
    """Find recurring header/footer instances of already discovered direct leaks.

    This is deliberately limited to strings already identified as title-block or
    machine-readable identifiers; ordinary repeated scientific text is untouched.
    """
    if len(page_texts) < 2 or not direct:
        return set()
    found: set[str] = set()
    for text in page_texts:
        lines = [normalized(x) for x in text.splitlines() if normalized(x)]
        edge_lines = lines[:5] + lines[-5:]
        for line in edge_lines:
            for candidate in direct:
                if candidate.casefold() in line.casefold():
                    found.add(candidate)
    return found


def discover_targets(
    page_texts: list[str], reference_page: int | None, reference_offset: int | None
) -> list[str]:
    """Return exact candidate strings appropriate for redaction before references."""
    before = before_references_text(page_texts, reference_page, reference_offset)
    found = title_block_candidates(page_texts[0] if page_texts else "")
    direct = set(found)
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        values = {match.group(0) for match in pattern.finditer(before)}
        found.update(values)
        direct.update(values)

    acknowledgement = ACK_RE.search(before)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)
                direct.add(candidate)

    # Redact an exact short disclosure line, never a surrounding paragraph/area.
    for raw_line in before.splitlines():
        line = normalized(raw_line)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
            direct.add(line)
    found.update(repeated_direct_identifier_candidates(page_texts, direct))
    return sorted(found, key=lambda item: (-len(item), item.casefold()))


def parse_manual_targets(raw: Any) -> list[dict[str, Any]]:
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
        parsed.append({
            "text": item["text"], "scope": scope, "pages": item.get("pages"), "origin": "manual"
        })
    return parsed


def target_pages(
    target: dict[str, Any], page_count: int, reference_page: int | None
) -> list[int]:
    if target["scope"] == "all":
        return list(range(page_count))
    if target["scope"] == "before_references":
        return list(range(page_count if reference_page is None else reference_page + 1))
    supplied = target.get("pages")
    if not isinstance(supplied, list) or not supplied:
        raise ValueError("pages scope requires a nonempty pages array")
    result: list[int] = []
    for page_number in supplied:
        if (not isinstance(page_number, int) or isinstance(page_number, bool)
                or not 0 <= page_number < page_count):
            raise ValueError("selected page is outside the document")
        if page_number not in result:
            result.append(page_number)
    return result


def references_heading_y(doc: Any, page_number: int | None, page_text: str) -> float | None:
    if page_number is None:
        return None
    hit = REF_RE.search(page_text)
    if not hit:
        return None
    boxes = doc[page_number].search_for(hit.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def clear_identifying_metadata(doc: Any) -> tuple[list[str], bool]:
    metadata = dict(doc.metadata or {})
    cleared: list[str] = []
    # Creator/producer can include names or institutional toolchains. Clearing all
    # common viewer fields avoids metadata-based identity leakage.
    for key in ("author", "creator", "producer", "title", "subject", "keywords"):
        if metadata.get(key):
            cleared.append(key)
        metadata[key] = ""
    doc.set_metadata(metadata)
    xmp_cleared = False
    if hasattr(doc, "set_xml_metadata"):
        try:
            doc.set_xml_metadata("")
            xmp_cleared = True
        except Exception:
            pass
    return cleared, xmp_cleared


def text_in_before_reference_scope(
    doc: Any, reference_page: int | None, heading_y: float | None
) -> str:
    chunks: list[str] = []
    for page_number, page in enumerate(doc):
        if reference_page is not None and page_number > reference_page:
            break
        text = page.get_text("text")
        if page_number == reference_page:
            match = REF_RE.search(text)
            text = text[:match.start()] if match else text
        chunks.append(text)
    return "\n".join(chunks)


def anonymize_one(source_name: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_name)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    output = output_dir / source.name
    if source.resolve() == output.resolve():
        raise ValueError("output path must not be an input path")

    doc = fitz.open(str(source))
    temporary: Path | None = None
    try:
        page_count = doc.page_count
        if page_count < 1:
            raise ValueError(f"input has no pages: {source}")
        page_texts = [page.get_text("text") for page in doc]
        reference_page, reference_offset = reference_boundary(page_texts)
        heading_y = references_heading_y(
            doc, reference_page, page_texts[reference_page] if reference_page is not None else ""
        )

        automatic = [
            {"text": value, "scope": "before_references", "pages": None, "origin": "automatic"}
            for value in discover_targets(page_texts, reference_page, reference_offset)
        ]
        targets: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in automatic + manual:
            identity = (target["text"], target["scope"], tuple(target.get("pages") or []))
            if identity not in seen:
                seen.add(identity)
                targets.append(target)

        rectangles_by_page: dict[int, list[Any]] = {}
        audit: list[dict[str, Any]] = []
        for target in targets:
            hits = 0
            for page_number in target_pages(target, page_count, reference_page):
                page = doc[page_number]
                for rectangle in page.search_for(target["text"]):
                    # A References heading can share the final body page. Never
                    # redact occurrences positioned in its bibliography portion.
                    if (target["scope"] == "before_references" and page_number == reference_page
                            and heading_y is not None and rectangle.y1 > heading_y + 0.5):
                        continue
                    rectangles_by_page.setdefault(page_number, []).append(rectangle)
                    hits += 1
            audit.append({
                "text": target["text"], "scope": target["scope"],
                "origin": target["origin"], "rectangles": hits,
            })

        for page_number, rectangles in rectangles_by_page.items():
            page = doc[page_number]
            for rectangle in rectangles:
                page.add_redact_annot(rectangle, fill=(1, 1, 1))
            page.apply_redactions()

        metadata_cleared, xmp_cleared = clear_identifying_metadata(doc)
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)
        temporary = None

        delivered = fitz.open(str(output))
        try:
            saved_pages = delivered.page_count
            pre_reference_output = text_in_before_reference_scope(delivered, reference_page, heading_y)
        finally:
            delivered.close()
        if saved_pages != page_count or saved_pages < 1:
            raise RuntimeError("saved output is unreadable or its page count changed")

        residual = [
            row["text"] for row in audit
            if row["rectangles"] > 0 and re.search(re.escape(row["text"]), pre_reference_output, re.I)
        ]
        return {
            "input": str(source), "output": str(output), "readable": True,
            "original_page_count": page_count, "output_page_count": saved_pages,
            "page_count_matches": True, "references_page_zero_based": reference_page,
            "metadata_cleared": metadata_cleared, "xmp_cleared": xmp_cleared,
            "targets": audit,
            "unmatched_manual_targets": [r["text"] for r in audit if r["origin"] == "manual" and r["rectangles"] == 0],
            "unmatched_automatic_candidates": [r["text"] for r in audit if r["origin"] == "automatic" and r["rectangles"] == 0],
            "residual_targets_before_references": residual,
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
        if (not isinstance(inputs, list) or not inputs
                or not all(isinstance(item, str) and item for item in inputs)):
            raise ValueError("inputs must be a nonempty array of paths")
        output_dir_raw = request.get("output_dir")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("output_dir must be a nonempty path")
        target_map = request.get("targets_by_input", {})
        if not isinstance(target_map, dict):
            raise ValueError("targets_by_input must be an object")

        jobs = [
            anonymize_one(source, Path(output_dir_raw), parse_manual_targets(target_map.get(source)))
            for source in inputs
        ]
        result: dict[str, Any] = {"status": "ok", "jobs": jobs}
        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path")
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["report_path"] = str(report)
        emit(result)
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
