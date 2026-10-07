"""Applied, page-preserving PDF redaction entrypoint.

Reads JSON from stdin:
{"inputs": ["/source.pdf"], "output_dir": "/out",
 "targets_by_input": {"/source.pdf": [{"text": "exact text",
 "scope": "before_references|pages|all", "pages": [0]}]},
 "report_path": "/optional/audit.json"}

Writes one JSON result to stdout. Requires PyMuPDF (fitz).
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
except Exception as exc:  # environment-dependent prerequisite
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
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(
    r"(?i)\b(?:accepted|to appear|published|appearing|presented)\s+(?:at|in)\b|"
    r"\b(?:proceedings of|copyright .*?(?:association|conference|society))\b"
)


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def reference_boundary(texts: list[str]) -> tuple[int | None, int | None]:
    for number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return number, match.start()
    return None, None


def before_references(texts: list[str], page: int | None, offset: int | None) -> str:
    if page is None:
        return "\n".join(texts)
    return "\n".join(texts[:page] + [texts[page][:offset or 0]])


def title_targets(first_page: str) -> set[str]:
    """Find exact title-block strings; this never selects a page area."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [norm(line) for line in zone.splitlines() if norm(line)]
    excluded = {"Abstract", "Introduction", "Proceedings", "University", "Department",
                "Institute", "School", "Laboratory", "College", "Corresponding"}
    found: set[str] = set()
    for line in lines:
        for candidate in NAME_RE.findall(line):
            words = candidate.split()
            if (len(candidate) >= 5 and not any(word in excluded for word in words)
                    and (len(line) <= 180 or line.count(",") >= 1)):
                found.add(candidate)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            found.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            found.add(line)
    return found


def discover(texts: list[str], ref_page: int | None, ref_offset: int | None) -> list[str]:
    """Discover exact automatic targets outside bibliography text."""
    before = before_references(texts, ref_page, ref_offset)
    found = title_targets(texts[0] if texts else "")
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(before))

    acknowledgement = ACK_RE.search(before)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                found.add(candidate)

    # Exact disclosure lines preserve all surrounding paper content.
    for raw in before.splitlines():
        line = norm(raw)
        if line and len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            found.add(line)
    return sorted(found, key=lambda s: (-len(s), s.casefold()))


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
        if scope not in {"before_references", "pages", "all"}:
            raise ValueError("target scope must be before_references, pages, or all")
        parsed.append({"text": item["text"], "scope": scope,
                       "pages": item.get("pages"), "origin": "manual"})
    return parsed


def selected_pages(target: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    scope = target["scope"]
    if scope == "all":
        return list(range(count))
    if scope == "before_references":
        return list(range(count if ref_page is None else ref_page + 1))
    pages = target.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages scope requires a nonempty pages array")
    answer: list[int] = []
    for page in pages:
        if not isinstance(page, int) or isinstance(page, bool) or not 0 <= page < count:
            raise ValueError("selected page is outside the document")
        if page not in answer:
            answer.append(page)
    return answer


def reference_heading_y(doc: Any, page: int | None, page_text: str) -> float | None:
    if page is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    boxes = doc[page].search_for(match.group(0).strip())
    return min((box.y0 for box in boxes), default=None)


def sanitize_metadata(doc: Any) -> tuple[list[str], bool]:
    metadata = dict(doc.metadata or {})
    changed: list[str] = []
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        if metadata.get(key):
            changed.append(key)
        metadata[key] = ""
    doc.set_metadata(metadata)
    xmp = False
    if hasattr(doc, "set_xml_metadata"):
        try:
            doc.set_xml_metadata("")
            xmp = True
        except Exception:
            pass
    return changed, xmp


def output_pre_reference_text(doc: Any, ref_page: int | None) -> str:
    chunks: list[str] = []
    for number, page in enumerate(doc):
        if ref_page is not None and number > ref_page:
            break
        text = page.get_text("text")
        if number == ref_page:
            match = REF_RE.search(text)
            if match:
                text = text[:match.start()]
        chunks.append(text)
    return "\n".join(chunks)


def anonymize_one(source_text: str, out_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_text)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    output = out_dir / source.name
    if source.resolve() == output.resolve():
        raise ValueError("output path must not overwrite an input")

    doc = fitz.open(str(source))
    temporary: Path | None = None
    try:
        page_count = doc.page_count
        if page_count < 1:
            raise ValueError(f"input has no pages: {source}")
        texts = [page.get_text("text") for page in doc]
        ref_page, ref_offset = reference_boundary(texts)
        heading_y = reference_heading_y(doc, ref_page, texts[ref_page] if ref_page is not None else "")

        automatic = [{"text": text, "scope": "before_references", "pages": None,
                      "origin": "automatic"} for text in discover(texts, ref_page, ref_offset)]
        targets: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for target in automatic + manual:
            identity = (target["text"], target["scope"], tuple(target.get("pages") or []))
            if identity not in seen:
                seen.add(identity)
                targets.append(target)

        rectangles: dict[int, list[Any]] = {}
        audit: list[dict[str, Any]] = []
        for target in targets:
            hit_count = 0
            for page_number in selected_pages(target, page_count, ref_page):
                page = doc[page_number]
                for box in page.search_for(target["text"]):
                    # The final body page may contain the References heading. Do not
                    # touch text visually below the heading for automatic/body scope.
                    if (target["scope"] == "before_references" and page_number == ref_page
                            and heading_y is not None and box.y1 > heading_y + 0.5):
                        continue
                    rectangles.setdefault(page_number, []).append(box)
                    hit_count += 1
            audit.append({"text": target["text"], "scope": target["scope"],
                          "origin": target["origin"], "rectangles": hit_count})

        for page_number, boxes in rectangles.items():
            page = doc[page_number]
            unique: set[tuple[float, float, float, float]] = set()
            for box in boxes:
                key = tuple(round(value, 3) for value in (box.x0, box.y0, box.x1, box.y1))
                if key not in unique:
                    unique.add(key)
                    page.add_redact_annot(box, fill=(1, 1, 1))
            page.apply_redactions()

        metadata_cleared, xmp_cleared = sanitize_metadata(doc)
        out_dir.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)
        temporary = None

        delivered = fitz.open(str(output))
        try:
            output_count = delivered.page_count
            scoped_text = output_pre_reference_text(delivered, ref_page)
        finally:
            delivered.close()
        if output_count != page_count or output_count < 1:
            raise RuntimeError("saved output is unreadable or its page count changed")

        residual = [row["text"] for row in audit if row["rectangles"] > 0
                    and re.search(re.escape(row["text"]), scoped_text, re.I)]
        return {"input": str(source), "output": str(output), "readable": True,
                "original_page_count": page_count, "output_page_count": output_count,
                "page_count_matches": True, "references_page_zero_based": ref_page,
                "metadata_cleared": metadata_cleared, "xmp_cleared": xmp_cleared,
                "targets": audit,
                "unmatched_manual_targets": [row["text"] for row in audit
                    if row["origin"] == "manual" and row["rectangles"] == 0],
                "unmatched_automatic_candidates": [row["text"] for row in audit
                    if row["origin"] == "automatic" and row["rectangles"] == 0],
                "residual_targets_before_references": residual}
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
        if (not isinstance(inputs, list) or not inputs or
                not all(isinstance(value, str) and value for value in inputs)):
            raise ValueError("inputs must be a nonempty array of paths")
        output_dir = request.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a nonempty path")
        target_map = request.get("targets_by_input", {})
        if not isinstance(target_map, dict):
            raise ValueError("targets_by_input must be an object")

        results = [anonymize_one(item, Path(output_dir), parse_manual(target_map.get(item)))
                   for item in inputs]
        result: dict[str, Any] = {"status": "ok", "jobs": results}
        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path")
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
            result["report_path"] = str(report)
        emit(result)
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
