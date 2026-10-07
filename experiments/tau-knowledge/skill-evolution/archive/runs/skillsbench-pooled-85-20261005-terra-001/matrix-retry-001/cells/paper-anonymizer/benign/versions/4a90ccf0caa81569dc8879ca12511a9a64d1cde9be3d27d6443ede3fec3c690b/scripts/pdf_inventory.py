"""Extract a reviewable, page-by-page PDF anonymity inventory.

JSON stdin:
{"inputs":["/path/a.pdf", ...], "report_path":"/path/inventory.txt"}
JSON stdout summarizes discovered document structure. The detailed text is written
only to report_path so large papers do not overflow command output.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from pdf_common import emit, find_references_page, page_texts, read_request, require_fitz, validate_path, write_utf8

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
ARXIV_RE = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/[0-9]{7})(?:v\d+)?\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def candidate_lines(text: str) -> list[str]:
    result: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        labels: list[str] = []
        if EMAIL_RE.search(line):
            labels.append("email")
        if ARXIV_RE.search(line):
            labels.append("arXiv")
        if DOI_RE.search(line):
            labels.append("DOI")
        if labels:
            result.append(f"  line {line_no} [{', '.join(labels)}]: {line}")
    return result


def xmp_value(doc: Any) -> str:
    getter = getattr(doc, "get_xml_metadata", None)
    if getter is None:
        return ""
    try:
        return getter() or ""
    except Exception as exc:
        return f"[XMP could not be read: {exc}]"


def main() -> int:
    try:
        request = read_request()
        fitz = require_fitz()
        inputs = request.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise ValueError("inputs must be a nonempty array of PDF path strings")
        report_path = validate_path(request.get("report_path"), "report_path")
        sections: list[str] = [
            "PDF ANONYMIZATION INVENTORY",
            "Read every page below before making a redaction plan. Candidate lines are leads, not automatic targets.",
            "Page indexes in the suggested plan are zero-based; displayed PDF page numbers are one-based.",
            "",
        ]
        summaries: list[dict[str, Any]] = []
        for input_value in inputs:
            input_path = validate_path(input_value, "input path")
            if not Path(input_path).is_file():
                raise ValueError(f"input file does not exist: {input_path}")
            doc = fitz.open(input_path)
            try:
                texts = page_texts(doc)
                reference_page = find_references_page(texts)
                metadata = dict(doc.metadata or {})
                xmp = xmp_value(doc)
                sections.extend([
                    "=" * 78,
                    f"FILE: {input_path}",
                    f"PAGE COUNT: {doc.page_count}",
                    "SUGGESTED REFERENCES PAGE (zero-based; confirm visually): " + (str(reference_page) if reference_page is not None else "NOT FOUND"),
                    "DOCUMENT INFORMATION METADATA:",
                ])
                for key in sorted(metadata):
                    sections.append(f"  {key}: {metadata[key]!r}")
                sections.append("XMP METADATA:")
                sections.append(xmp if xmp else "  [none or unavailable]")
                sections.append("PATTERN CANDIDATES (may legitimately occur in References):")
                any_candidates = False
                for idx, text in enumerate(texts):
                    found = candidate_lines(text)
                    if found:
                        any_candidates = True
                        sections.append(f"page {idx} / PDF page {idx + 1}:")
                        sections.extend(found)
                if not any_candidates:
                    sections.append("  [none]")
                for idx, text in enumerate(texts):
                    sections.extend([
                        "-" * 78,
                        f"PAGE {idx} (PDF page {idx + 1})" + ("  <SUGGESTED REFERENCES START>" if idx == reference_page else ""),
                        text if text else "[No extractable text on this page: inspect visually/OCR before redaction.]",
                    ])
                sections.append("")
                summaries.append({
                    "input": input_path,
                    "page_count": doc.page_count,
                    "suggested_references_page": reference_page,
                    "metadata_keys": sorted(metadata.keys()),
                    "xmp_present": bool(xmp),
                })
            finally:
                doc.close()
        write_utf8(report_path, "\n".join(sections))
        emit({"status": "ok", "report_path": report_path, "documents": summaries})
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
