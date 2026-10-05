"""Create applied, page-preserving blind-review PDF redactions.

stdin JSON:
{"inputs":["/source.pdf"],"output_dir":"/out",
 "targets_by_input":{"/source.pdf":[{"text":"exact string",
 "scope":"before_references|pages|all","pages":[0]}]},
 "report_path":"/optional/audit.json"}
stdout JSON: {"status":"ok|error", "jobs":[...]}
Requires PyMuPDF (fitz).
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
AFF_RE = re.compile(r"(?i)\b(?:university|universit[eé]|institute|institution|department|school of|college|laboratory|lab(?:oratory)?|centre|center|research group|inc\.|llc|ltd\.|corporation|gmbh)\b")
ACK_RE = re.compile(r"(?is)\b(?:acknowledg(?:e)?ments?)\b(.*?)(?=\n\s*(?:references|bibliography)\b|\Z)")
ACK_NAME_RE = re.compile(r"(?i)(?:thank(?:s|ed)?|grateful to|indebted to|help from)\s+([A-Z][A-Za-z'’.-]+(?:\s+(?:and\s+)?[A-Z][A-Za-z'’.-]+){1,3})")
NOTE_RE = re.compile(r"(?i)\b(?:corresponding author|author contributions?|contributions?)\b")
VENUE_RE = re.compile(r"(?i)\b(?:accepted|to appear|published|appearing|presented)\s+(?:at|in)\b|\b(?:proceedings of|copyright .*?(?:association|conference|society))\b")


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def reference_boundary(page_texts: list[str]) -> tuple[int | None, int | None]:
    for page_no, text in enumerate(page_texts):
        match = REF_RE.search(text)
        if match:
            return page_no, match.start()
    return None, None


def before_references(page_texts: list[str], ref_page: int | None, offset: int | None) -> str:
    if ref_page is None:
        return "\n".join(page_texts)
    return "\n".join(page_texts[:ref_page] + [page_texts[ref_page][:offset or 0]])


def discover(page_texts: list[str], ref_page: int | None, offset: int | None) -> list[str]:
    """Find conservative exact candidates. This function never defines page areas."""
    body = before_references(page_texts, ref_page, offset)
    first = page_texts[0] if page_texts else ""
    abstract = re.search(r"(?im)^\s*abstract\b", first)
    title_zone = first[:abstract.start()] if abstract else first[:2500]
    lines = [norm(line) for line in title_zone.splitlines() if norm(line)]
    stop = {"Abstract", "Introduction", "Proceedings", "University", "Department", "Institute", "School", "Laboratory", "College", "Corresponding"}
    found: set[str] = set()

    # The title block is the primary direct-identity location.
    for line in lines:
        for name in NAME_RE.findall(line):
            if len(name) >= 5 and not any(word in stop for word in name.split()):
                if len(line) <= 180 or line.count(",") >= 1:
                    found.add(name)
        if AFF_RE.search(line) and len(line) <= 250:
            found.add(line)
        if len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            found.add(line)

    # Machine-readable identifiers only count before the bibliography.
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        found.update(match.group(0) for match in pattern.finditer(body))

    # Proper names in acknowledgement wording are intentionally considered only
    # within that section, avoiding a broad global proper-noun redaction.
    acknowledgement = ACK_RE.search(body)
    if acknowledgement:
        for name in ACK_NAME_RE.findall(acknowledgement.group(1)):
            name = re.sub(r"\s+and\s+", " and ", name).strip()
            if len(name) >= 5:
                found.add(name)

    # Short author-linked or accepted-venue lines outside the title block can occur
    # as footnotes or recurring running material.
    for raw_line in body.splitlines():
        line = norm(raw_line)
        if line and len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            found.add(line)

    return sorted(found, key=lambda item: (-len(item), item.casefold()))


def parse_manual(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("targets_by_input values must be arrays")
    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("each target requires nonempty text")
        scope = item.get("scope", "before_references")
        if scope not in {"before_references", "pages", "all"}:
            raise ValueError("target scope must be before_references, pages, or all")
        result.append({"text": item["text"], "scope": scope, "pages": item.get("pages"), "origin": "manual"})
    return result


def target_pages(target: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    if target["scope"] == "all":
        return list(range(count))
    if target["scope"] == "before_references":
        return list(range(count if ref_page is None else ref_page + 1))
    pages = target.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages scope requires a nonempty pages list")
    if any(not isinstance(page, int) or isinstance(page, bool) or page < 0 or page >= count for page in pages):
        raise ValueError("target pages must be valid zero-based page numbers")
    return list(dict.fromkeys(pages))


def reference_heading_y(doc: Any, page_no: int | None, page_text: str) -> float | None:
    if page_no is None:
        return None
    match = REF_RE.search(page_text)
    if not match:
        return None
    hits = doc[page_no].search_for(match.group(0).strip())
    return min((rect.y0 for rect in hits), default=None)


def find_rectangles(page: Any, text: str) -> list[Any]:
    hits = list(page.search_for(text))
    if hits or " " not in text:
        return hits
    # Some PDFs split a reviewed phrase across spans. This limited fallback keeps
    # the operation text-based, and is restricted to meaningful phrase components.
    words = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ'’.-]{2,}", text)
    if len(words) >= 2:
        for word in words:
            hits.extend(page.search_for(word))
    return hits


def clear_metadata(doc: Any) -> list[str]:
    metadata = dict(doc.metadata or {})
    changed = []
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        if metadata.get(key):
            changed.append(key)
        metadata[key] = ""
    doc.set_metadata(metadata)
    try:
        doc.set_xml_metadata("")
    except Exception:
        pass
    return changed


def process(source_name: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_name)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    output = output_dir / source.name
    if source.resolve() == output.resolve():
        raise ValueError("output must not overwrite its source")

    doc = fitz.open(str(source))
    temporary: Path | None = None
    try:
        page_count = doc.page_count
        if page_count < 1:
            raise ValueError("input PDF has no pages")
        text = [page.get_text("text") for page in doc]
        ref_page, ref_offset = reference_boundary(text)
        heading_y = reference_heading_y(doc, ref_page, text[ref_page] if ref_page is not None else "")
        automatic = [{"text": item, "scope": "before_references", "pages": None, "origin": "automatic"} for item in discover(text, ref_page, ref_offset)]
        targets = automatic + manual
        unique: list[dict[str, Any]] = []
        seen = set()
        for target in targets:
            key = (target["text"], target["scope"], tuple(target.get("pages") or []))
            if key not in seen:
                seen.add(key)
                unique.append(target)

        rectangles: dict[int, list[Any]] = {}
        audit = []
        for target in unique:
            matched = 0
            for page_no in target_pages(target, page_count, ref_page):
                for rect in find_rectangles(doc[page_no], target["text"]):
                    # Do not allow default candidates on a page containing the
                    # heading to reach bibliography entries below that heading.
                    if target["scope"] == "before_references" and page_no == ref_page and heading_y is not None and rect.y1 > heading_y + 0.5:
                        continue
                    rectangles.setdefault(page_no, []).append(rect)
                    matched += 1
            audit.append({"text": target["text"], "scope": target["scope"], "origin": target["origin"], "rectangles": matched})

        for page_no, rects in rectangles.items():
            page = doc[page_no]
            used = set()
            for rect in rects:
                key = tuple(round(value, 3) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
                if key not in used:
                    used.add(key)
                    page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

        metadata_cleared = clear_metadata(doc)
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)
        temporary = None

        saved = fitz.open(str(output))
        try:
            if saved.page_count != page_count:
                raise RuntimeError("saved PDF page count changed")
            saved_text = [page.get_text("text") for page in saved]
            surviving = before_references(saved_text, *reference_boundary(saved_text))
        finally:
            saved.close()

        residual = [entry["text"] for entry in audit if entry["rectangles"] and re.search(re.escape(entry["text"]), surviving, re.I)]
        unmatched_manual = [entry["text"] for entry in audit if entry["origin"] == "manual" and not entry["rectangles"]]
        return {"input": str(source), "output": str(output), "readable": True, "original_page_count": page_count, "output_page_count": page_count, "page_count_matches": True, "references_page_zero_based": ref_page, "metadata_cleared": metadata_cleared, "targets": audit, "unmatched_manual_targets": unmatched_manual, "residual_targets_before_references": residual}
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
        output_dir = request.get("output_dir")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(item, str) and item for item in inputs):
            raise ValueError("inputs must be a nonempty array of paths")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a nonempty path")
        mapping = request.get("targets_by_input", {})
        if not isinstance(mapping, dict):
            raise ValueError("targets_by_input must be an object")

        jobs = []
        for source in inputs:
            try:
                jobs.append(process(source, Path(output_dir), parse_manual(mapping.get(source))))
            except Exception as exc:
                jobs.append({"input": source, "status": "error", "error": str(exc)})
        result = {"status": "ok" if all("error" not in job for job in jobs) else "error", "jobs": jobs}

        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path")
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            result["report_path"] = str(report)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ok" else 2
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
