#!/usr/bin/env python3
"""Extract supplied PDF text and concrete blind-review candidates for human review.

stdin: {"inputs":["source.pdf", ...]}
stdout: {"documents":[{path,page_count,metadata,reference_boundary,pages,candidates}]}
"""
import json
import re
import sys
from pathlib import Path
try:
    import fitz
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

EMAIL = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
ARXIV = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.I)
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
REF = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references|bibliography)\s*$", re.I)
VENUE = re.compile(r"\b(?:accepted|acceptance|proceedings|conference|published|copyright|camera[ -]?ready)\b", re.I)


def inspect(path):
    doc = fitz.open(path)
    try:
        texts = [page.get_text("text") for page in doc]
        boundary = None
        for pno, text in enumerate(texts):
            for line in text.splitlines():
                if REF.match(line.strip()):
                    boxes = doc[pno].search_for(line.strip())
                    boundary = {"page": pno + 1, "y": float(boxes[0].y0) if boxes else None, "heading": line.strip()}
                    break
            if boundary:
                break
        candidates = []
        for pno, text in enumerate(texts, 1):
            for category, pattern in (("email", EMAIL), ("arxiv_id", ARXIV), ("doi", DOI)):
                for match in pattern.finditer(text):
                    candidates.append({"category": category, "page": pno, "text": match.group(0)})
            for line in text.splitlines():
                if VENUE.search(line):
                    candidates.append({"category": "venue_or_acceptance_clue", "page": pno, "text": line.strip()})
        return {"path": str(path), "page_count": doc.page_count, "metadata": dict(doc.metadata or {}),
                "reference_boundary": boundary, "pages": [{"page": n + 1, "text": text} for n, text in enumerate(texts)],
                "candidates": candidates,
                "review_note": "Read bylines, acknowledgements, contribution notes, headers, footers, and metadata. Preserve bibliography and self-citations."}
    finally:
        doc.close()


def main():
    request = json.load(sys.stdin)
    paths = request.get("inputs") if isinstance(request, dict) else None
    if not isinstance(paths, list) or not paths or not all(isinstance(x, str) for x in paths):
        raise ValueError("input must contain a nonempty inputs array of paths")
    missing = [x for x in paths if not Path(x).is_file()]
    if missing:
        raise FileNotFoundError("input PDF(s) not found: " + ", ".join(missing))
    print(json.dumps({"documents": [inspect(x) for x in paths]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
