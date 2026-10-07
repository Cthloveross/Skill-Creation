"""Create true, page-preserving blind-review PDF redactions.

Read a JSON request from stdin and emit one JSON result to stdout. Requires
PyMuPDF (fitz). The program never writes to an input path.
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
except Exception as exc:
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
    r"college|laboratory|lab(?:oratory)?|centre|center|research group|inc\.|llc|"
    r"ltd\.|corporation|gmbh)\b"
)
ACK_RE = re.compile(r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)")
ACK_NAME_RE = re.compile(
    r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+"
    r"([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})"
)
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published)\s+(?:at|in)\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def reference_boundary(texts: list[str]) -> tuple[int | None, int | None]:
    for page_no, text in enumerate(texts):
        hit = REF_RE.search(text)
        if hit:
            return page_no, hit.start()
    return None, None


def text_before_references(texts: list[str], ref_page: int | None, ref_at: int | None) -> str:
    if ref_page is None:
        return "\n".join(texts)
    return "\n".join(texts[:ref_page] + [texts[ref_page][:ref_at or 0]])


def title_block_targets(first_page: str) -> set[str]:
    """Conservatively obtain exact title-page author/affiliation candidates."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [norm(line) for line in zone.splitlines() if norm(line)]
    excluded_words = {
        "Abstract", "Introduction", "Proceedings", "University", "Department",
        "Institute", "School", "Laboratory", "College", "Corresponding",
    }
    found: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            words = candidate.split()
            if (len(candidate) >= 5 and not any(word in excluded_words for word in words)
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return found


def discover_targets(texts: list[str], ref_page: int | None, ref_at: int | None) -> list[str]:
    """Return exact strings that may be safely redacted before References."""
    before = text_before_references(texts, ref_page, ref_at)
    found = title_block_targets(texts[0] if texts else "")
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(before))

    acknowledgement = ACK_RE.search(before)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)

    # Target a short, exact acceptance line rather than an area containing it.
    for raw_line in before.splitlines():
        line = norm(raw_line)
        if VENUE_RE.search(line) and len(line) <= 300:
            found.add(line)
    return sorted(found, key=lambda value: (-len(value), value.casefold()))


def parse_manual(raw: Any) -> list[dict[str, Any]]:
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
        result.append({"text": item["text"], "scope": scope, "pages": item.get("pages"), "origin": "manual"})
    return result


def pages_for(target: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    if target["scope"] == "all":
        return list(range(count))
    if target["scope"] == "before_references":
        return list(range(count if ref_page is None else ref_page + 1))
    raw = target.get("pages")
    if not isinstance(raw, list) or not raw:
        raise ValueError("pages scope requires a nonempty pages array")
    result: list[int] = []
    for page_no in raw:
        if not isinstance(page_no, int) or isinstance(page_no, bool) or not 0 <= page_no < count:
            raise ValueError("selected page is outside the document")
        if page_no not in result:
            result.append(page_no)
    return result


def reference_y(doc: Any, page_no: int | None, page_text: str) -> float | None:
    if page_no is None:
        return None
    heading = REF_RE.search(page_text)
    if not heading:
        return None
    boxes = doc[page_no].search_for(heading.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def clear_metadata(doc: Any) -> tuple[list[str], bool]:
    metadata = dict(doc.metadata or {})
    cleared: list[str] = []
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
        texts = [page.get_text("text") for page in doc]
        ref_page, ref_at = reference_boundary(texts)
        ref_top = reference_y(doc, ref_page, texts[ref_page]) if ref_page is not None else None

        automatic = [
            {"text": text, "scope": "before_references", "pages": None, "origin": "automatic"}
            for text in discover_targets(texts, ref_page, ref_at)
        ]
        targets: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in automatic + manual:
            identity = (target["text"], target["scope"], tuple(target.get("pages") or []))
            if identity not in seen:
                seen.add(identity)
                targets.append(target)

        boxes_by_page: dict[int, list[Any]] = {}
        audit: list[dict[str, Any]] = []
        for target in targets:
            hits = 0
            for page_no in pages_for(target, page_count, ref_page):
                page = doc[page_no]
                for box in page.search_for(target["text"]):
                    # The page containing the heading can contain both final body
                    # material and bibliography. Preserve the latter unchanged.
                    if (target["scope"] == "before_references" and page_no == ref_page
                            and ref_top is not None and box.y1 > ref_top + 0.5):
                        continue
                    boxes_by_page.setdefault(page_no, []).append(box)
                    hits += 1
            audit.append({"text": target["text"], "scope": target["scope"], "origin": target["origin"], "rectangles": hits})

        for page_no, boxes in boxes_by_page.items():
            page = doc[page_no]
            for box in boxes:
                page.add_redact_annot(box, fill=(1, 1, 1))
            page.apply_redactions()

        cleared, xmp_cleared = clear_metadata(doc)
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
            output_text = "\n".join(page.get_text("text") for page in delivered)
        finally:
            delivered.close()
        if saved_pages != page_count or saved_pages < 1:
            raise RuntimeError("saved output is unreadable or its page count changed")

        residual = [item["text"] for item in audit if item["rectangles"] > 0 and re.search(re.escape(item["text"]), output_text, re.I)]
        return {
            "input": str(source), "output": str(output), "readable": True,
            "original_page_count": page_count, "output_page_count": saved_pages,
            "page_count_matches": True, "references_page_zero_based": ref_page,
            "metadata_cleared": cleared, "xmp_cleared": xmp_cleared,
            "targets": audit,
            "unmatched_manual_targets": [x["text"] for x in audit if x["origin"] == "manual" and x["rectangles"] == 0],
            "unmatched_automatic_candidates": [x["text"] for x in audit if x["origin"] == "automatic" and x["rectangles"] == 0],
            "residual_matched_targets": residual,
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
        output_dir_raw = request.get("output_dir")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("output_dir must be a nonempty path")
        target_map = request.get("targets_by_input", {})
        if not isinstance(target_map, dict):
            raise ValueError("targets_by_input must be an object")

        jobs = [anonymize_one(source, Path(output_dir_raw), parse_manual(target_map.get(source))) for source in inputs]
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
