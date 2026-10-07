"""Create page-preserving, applied PDF redactions.

stdin JSON:
{"inputs":["/source.pdf"], "output_dir":"/out", "targets_by_input":{
 "/source.pdf":[{"text":"exact text", "scope":"before_references|pages|all",
                   "pages":[0]}]}, "report_path":"/optional/report.json"}

stdout is a JSON status/audit object. Requires PyMuPDF (fitz).
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
    for page_number, text in enumerate(texts):
        match = REF_RE.search(text)
        if match:
            return page_number, match.start()
    return None, None


def before_references(texts: list[str], ref_page: int | None, offset: int | None) -> str:
    if ref_page is None:
        return "\n".join(texts)
    return "\n".join(texts[:ref_page] + [texts[ref_page][:offset or 0]])


def title_targets(first_page: str) -> set[str]:
    """Return exact strings from the pre-abstract title block, never page regions."""
    abstract = re.search(r"(?im)^\s*abstract\b", first_page)
    zone = first_page[:abstract.start()] if abstract else first_page[:2500]
    lines = [norm(line) for line in zone.splitlines() if norm(line)]
    excluded = {"Abstract", "Introduction", "Proceedings", "University", "Department",
                "Institute", "School", "Laboratory", "College", "Corresponding"}
    targets: set[str] = set()
    for line in lines:
        for person in NAME_RE.findall(line):
            words = person.split()
            if (len(person) >= 5 and not any(word in excluded for word in words)
                    and (len(line) <= 180 or line.count(",") >= 1)):
                targets.add(person)
        if AFFILIATION_RE.search(line) and len(line) <= 250:
            targets.add(line)
        if (NOTE_RE.search(line) or VENUE_RE.search(line)) and len(line) <= 300:
            targets.add(line)
    return targets


def discover(texts: list[str], ref_page: int | None, ref_offset: int | None) -> list[str]:
    """Discover conservative exact candidates outside the bibliography."""
    body = before_references(texts, ref_page, ref_offset)
    targets = title_targets(texts[0] if texts else "")
    for pattern in (EMAIL_RE, ARXIV_RE, DOI_RE):
        targets.update(match.group(0) for match in pattern.finditer(body))

    acknowledgement = ACK_RE.search(body)
    if acknowledgement:
        for candidate in ACK_NAME_RE.findall(acknowledgement.group(1)):
            candidate = re.sub(r"\s+and\s+", " and ", candidate).strip()
            if len(candidate) >= 5:
                targets.add(candidate)

    # Whole, short disclosure lines are precise targets and retain nearby content.
    for raw_line in body.splitlines():
        line = norm(raw_line)
        if line and len(line) <= 300 and (NOTE_RE.search(line) or VENUE_RE.search(line)):
            targets.add(line)
    return sorted(targets, key=lambda item: (-len(item), item.casefold()))


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
        if scope not in {"before_references", "pages", "all"}:
            raise ValueError("target scope must be before_references, pages, or all")
        result.append({"text": item["text"], "scope": scope,
                       "pages": item.get("pages"), "origin": "manual"})
    return result


def target_pages(target: dict[str, Any], count: int, ref_page: int | None) -> list[int]:
    if target["scope"] == "all":
        return list(range(count))
    if target["scope"] == "before_references":
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


def reference_heading_y(doc: Any, page_number: int | None, text: str) -> float | None:
    if page_number is None:
        return None
    match = REF_RE.search(text)
    if not match:
        return None
    rects = doc[page_number].search_for(match.group(0).strip())
    return min((rect.y0 for rect in rects), default=None)


def find_rects(page: Any, text: str) -> list[Any]:
    """Search exact extracted text, with a safe word fallback for split PDF lines."""
    rects = list(page.search_for(text))
    if rects or " " not in text:
        return rects
    # Some PDFs represent a title-block affiliation as separate spans although text
    # extraction joins it. Fallback only applies to long literal words, and only
    # when the exact phrase did not match at all.
    pieces = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ'’.-]{2,}", text)
    if len(pieces) < 2:
        return rects
    for piece in pieces:
        rects.extend(page.search_for(piece))
    return rects


def sanitize_metadata(doc: Any) -> tuple[list[str], bool]:
    metadata = dict(doc.metadata or {})
    changed: list[str] = []
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        if metadata.get(key):
            changed.append(key)
        metadata[key] = ""
    doc.set_metadata(metadata)
    xmp_cleared = False
    if hasattr(doc, "set_xml_metadata"):
        try:
            doc.set_xml_metadata("")
            xmp_cleared = True
        except Exception:
            pass
    return changed, xmp_cleared


def scoped_output_text(doc: Any, ref_page: int | None) -> str:
    parts: list[str] = []
    for number, page in enumerate(doc):
        if ref_page is not None and number > ref_page:
            break
        text = page.get_text("text")
        if number == ref_page:
            match = REF_RE.search(text)
            if match:
                text = text[:match.start()]
        parts.append(text)
    return "\n".join(parts)


def anonymize_one(source_value: str, output_dir: Path, manual: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_value)
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")
    output = output_dir / source.name
    if source.resolve() == output.resolve():
        raise ValueError("output path must not overwrite an input")

    doc = fitz.open(str(source))
    temporary: Path | None = None
    try:
        count = doc.page_count
        if count < 1:
            raise ValueError(f"input has no pages: {source}")
        texts = [page.get_text("text") for page in doc]
        ref_page, ref_offset = reference_boundary(texts)
        ref_y = reference_heading_y(doc, ref_page, texts[ref_page] if ref_page is not None else "")

        automatic = [{"text": text, "scope": "before_references", "pages": None,
                      "origin": "automatic"}
                     for text in discover(texts, ref_page, ref_offset)]
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
            for page_number in target_pages(target, count, ref_page):
                page = doc[page_number]
                for rect in find_rects(page, target["text"]):
                    # On a mixed body/references page, automatic targets may only
                    # touch text above the visible References heading.
                    if (target["scope"] == "before_references" and page_number == ref_page
                            and ref_y is not None and rect.y1 > ref_y + 0.5):
                        continue
                    boxes_by_page.setdefault(page_number, []).append(rect)
                    hits += 1
            audit.append({"text": target["text"], "scope": target["scope"],
                          "origin": target["origin"], "rectangles": hits})

        for page_number, rects in boxes_by_page.items():
            page = doc[page_number]
            used: set[tuple[float, float, float, float]] = set()
            for rect in rects:
                key = tuple(round(value, 3) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
                if key not in used:
                    used.add(key)
                    page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

        metadata_cleared, xmp_cleared = sanitize_metadata(doc)
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".redacting.tmp.pdf")
        temporary.unlink(missing_ok=True)
        doc.save(str(temporary), garbage=4, deflate=True)
        doc.close()
        os.replace(temporary, output)
        temporary = None

        saved = fitz.open(str(output))
        try:
            saved_count = saved.page_count
            after_text = scoped_output_text(saved, ref_page)
        finally:
            saved.close()
        if saved_count != count or saved_count < 1:
            raise RuntimeError("saved output is unreadable or its page count changed")
        residual = [row["text"] for row in audit if row["rectangles"] > 0 and
                    re.search(re.escape(row["text"]), after_text, re.I)]
        return {"input": str(source), "output": str(output), "readable": True,
                "original_page_count": count, "output_page_count": saved_count,
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
                not all(isinstance(item, str) and item for item in inputs)):
            raise ValueError("inputs must be a nonempty array of paths")
        output_dir_value = request.get("output_dir")
        if not isinstance(output_dir_value, str) or not output_dir_value:
            raise ValueError("output_dir must be a nonempty path")
        target_map = request.get("targets_by_input", {})
        if not isinstance(target_map, dict):
            raise ValueError("targets_by_input must be an object")

        jobs: list[dict[str, Any]] = []
        for source in inputs:
            try:
                jobs.append(anonymize_one(source, Path(output_dir_value), parse_manual(target_map.get(source))))
            except Exception as exc:
                jobs.append({"input": source, "status": "error", "error": str(exc)})
        result: dict[str, Any] = {"status": "ok" if all("error" not in job for job in jobs) else "error",
                                  "jobs": jobs}
        report_path = request.get("report_path")
        if report_path is not None:
            if not isinstance(report_path, str) or not report_path:
                raise ValueError("report_path must be a nonempty path")
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["report_path"] = str(report)
        emit(result)
        return 0 if result["status"] == "ok" else 2
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
