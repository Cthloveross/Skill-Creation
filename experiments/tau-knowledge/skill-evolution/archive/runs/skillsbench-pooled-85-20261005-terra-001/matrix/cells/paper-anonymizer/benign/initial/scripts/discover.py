#!/usr/bin/env python3
"""Extract review material for explicit PDF anonymization target selection.

stdin:  {"inputs": ["/absolute/or/relative/file.pdf", ...]}
stdout: {"documents": [{path, page_count, metadata, reference_boundary, pages, candidates}]}

Candidates are deliberately not a redaction list. Human/executor review is required,
especially for names in author blocks and acknowledgement prose.
"""
import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

ARXIV_RE = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
REF_HEADING_RE = re.compile(r"^\s*(?:\d+\.?\s+)?(?:references|bibliography)\s*$", re.I)
CLUE_RE = re.compile(r"\b(?:accepted|acceptance|proceedings|conference|published|copyright|©|camera.ready)\b", re.I)


def context(text, start, end, radius=180):
    return text[max(0, start - radius):min(len(text), end + radius)].replace("\n", " ")


def reference_boundary(doc, page_texts):
    """Return the first actual References/Bibliography heading and its y position."""
    for pno, text in enumerate(page_texts, start=1):
        for line in text.splitlines():
            heading = line.strip()
            if REF_HEADING_RE.match(heading):
                rects = doc[pno - 1].search_for(heading)
                if rects:
                    rect = rects[0]
                    return {"page": pno, "y": round(float(rect.y0), 3), "heading": heading}
                # A boundary without geometry is still useful to reviewers.
                return {"page": pno, "y": None, "heading": heading}
    return None


def candidates_for_page(text, pno):
    found = []
    for label, regex in (("email", EMAIL_RE), ("arxiv_id", ARXIV_RE), ("doi", DOI_RE)):
        for match in regex.finditer(text):
            found.append({"category": label, "page": pno, "text": match.group(0),
                          "context": context(text, match.start(), match.end())})
    for line in text.splitlines():
        if CLUE_RE.search(line):
            found.append({"category": "venue_or_acceptance_clue", "page": pno,
                          "text": line.strip(), "context": line.strip()})
    return found


def inspect(path):
    doc = fitz.open(path)
    try:
        texts = [page.get_text("text") for page in doc]
        pages = [{"page": i + 1, "text": text} for i, text in enumerate(texts)]
        candidates = []
        for i, text in enumerate(texts, start=1):
            candidates.extend(candidates_for_page(text, i))
        return {
            "path": str(path),
            "page_count": doc.page_count,
            "metadata": dict(doc.metadata or {}),
            "reference_boundary": reference_boundary(doc, texts),
            "pages": pages,
            "candidates": candidates,
            "review_note": (
                "Candidates are not approved targets. Manually read every page, especially "
                "the byline, acknowledgements, contribution notes, headers, and footers. "
                "Keep bibliographic references unchanged."
            ),
        }
    finally:
        doc.close()


def main():
    request = json.load(sys.stdin)
    inputs = request.get("inputs")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) for x in inputs):
        raise ValueError("input JSON must contain a nonempty inputs array of file paths")
    missing = [p for p in inputs if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError("input PDF(s) not found: " + ", ".join(missing))
    print(json.dumps({"documents": [inspect(p) for p in inputs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
