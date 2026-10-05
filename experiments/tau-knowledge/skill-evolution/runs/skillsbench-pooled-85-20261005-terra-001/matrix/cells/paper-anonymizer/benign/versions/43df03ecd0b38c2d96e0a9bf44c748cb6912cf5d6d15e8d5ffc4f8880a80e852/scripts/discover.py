#!/usr/bin/env python3
"""Extract supplied PDFs for human blind-review redaction discovery.

stdin:  {"inputs": ["input.pdf", ...]}
stdout: {"documents": [{path, page_count, metadata, reference_boundary,
                         pages, candidates}]}
Candidates are review prompts, not automatic authorization to redact prose.
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


def get_boundary(doc, texts):
    for index, text in enumerate(texts):
        for line in text.splitlines():
            heading = line.strip()
            if REF.match(heading):
                hits = doc[index].search_for(heading)
                return {"page": index + 1, "y": float(hits[0].y0) if hits else None,
                        "heading": heading}
    return None


def excerpt(text, start, end):
    return text[max(0, start - 150): min(len(text), end + 150)].replace("\n", " ")


def inspect(path):
    doc = fitz.open(path)
    try:
        texts = [page.get_text("text") for page in doc]
        candidates = []
        for number, text in enumerate(texts, 1):
            for category, pattern in (("email", EMAIL), ("arxiv_id", ARXIV), ("doi", DOI)):
                for match in pattern.finditer(text):
                    candidates.append({"category": category, "page": number,
                                       "text": match.group(0),
                                       "context": excerpt(text, match.start(), match.end())})
            for line in text.splitlines():
                if VENUE.search(line):
                    candidates.append({"category": "venue_or_acceptance_clue", "page": number,
                                       "text": line.strip(), "context": line.strip()})
        return {
            "path": str(path), "page_count": doc.page_count,
            "metadata": dict(doc.metadata or {}),
            "reference_boundary": get_boundary(doc, texts),
            "pages": [{"page": n + 1, "text": text} for n, text in enumerate(texts)],
            "candidates": candidates,
            "review_note": "Read title/byline, acknowledgement and contribution prose, headers, footers, and metadata. Preserve references and self-citations."
        }
    finally:
        doc.close()


def main():
    request = json.load(sys.stdin)
    paths = request.get("inputs") if isinstance(request, dict) else None
    if not isinstance(paths, list) or not paths or not all(isinstance(x, str) for x in paths):
        raise ValueError("input must contain a nonempty inputs array of paths")
    absent = [x for x in paths if not Path(x).is_file()]
    if absent:
        raise FileNotFoundError("input PDF(s) not found: " + ", ".join(absent))
    print(json.dumps({"documents": [inspect(x) for x in paths]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
