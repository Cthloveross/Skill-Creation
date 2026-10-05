"""Apply only explicit search-based PDF redactions.

JSON stdin:
{"jobs":[{"input":"...","output":"...","references_page":3,
 "targets":[{"text":"Exact string","scope":"before_references"}],
 "metadata_clear":["author"],"clear_xmp":false}]}

Each target is searched using page.search_for() only on its declared pages. A job
is not written when any target has no matching rectangle or violates an optional
expected_matches guard.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pdf_common import (emit, read_request, require_fitz, reviewed_metadata_keys,
                        target_pages, validate_path, validate_target)


def redact_job(fitz: Any, job: Any) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise ValueError("each job must be an object")
    input_path = validate_path(job.get("input"), "job input")
    output_path = validate_path(job.get("output"), "job output")
    if os.path.abspath(input_path) == os.path.abspath(output_path):
        raise ValueError("output must differ from input; source PDFs are never modified")
    if not Path(input_path).is_file():
        raise ValueError(f"input file does not exist: {input_path}")
    raw_targets = job.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("each job needs a nonempty explicit targets array")
    targets = [validate_target(item) for item in raw_targets]
    metadata_keys = reviewed_metadata_keys(job.get("metadata_clear"))
    clear_xmp = job.get("clear_xmp", False)
    if not isinstance(clear_xmp, bool):
        raise ValueError("clear_xmp must be true or false")

    doc = fitz.open(input_path)
    tmp_path = output_path + ".anonymizing.tmp.pdf"
    try:
        page_count = doc.page_count
        references_page = job.get("references_page")
        records: list[dict[str, Any]] = []
        # Locate every rectangle before applying any page redactions. This makes a
        # count failure transactional and ensures all searches see original text.
        page_rects: dict[int, list[Any]] = {}
        for target in targets:
            text = target["text"]
            pages = target_pages(target, page_count, references_page)
            match_count = 0
            for page_number in pages:
                rects = doc[page_number].search_for(text)
                match_count += len(rects)
                page_rects.setdefault(page_number, []).extend(rects)
            expected = target.get("expected_matches")
            if match_count == 0:
                raise ValueError(f"target was not found in its allowed scope: {text!r}")
            if expected is not None and match_count != expected:
                raise ValueError(f"target match count for {text!r} was {match_count}, expected {expected}")
            records.append({"text": text, "scope": target["scope"], "pages": pages, "rectangles": match_count})

        for page_number, rects in page_rects.items():
            page = doc[page_number]
            for rect in rects:
                # The rectangle comes directly from search_for; it is never a
                # guessed page area. Applying the annotation removes text data.
                page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions()

        if metadata_keys:
            metadata = dict(doc.metadata or {})
            for key in metadata_keys:
                metadata[key] = ""
            doc.set_metadata(metadata)
        if clear_xmp:
            setter = getattr(doc, "set_xml_metadata", None)
            if setter is None:
                raise RuntimeError("this PyMuPDF version cannot clear reviewed XMP metadata")
            setter("")

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            Path(tmp_path).unlink(missing_ok=True)
            doc.save(tmp_path, garbage=4, deflate=True)
            doc.close()
            os.replace(tmp_path, output_path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        return {"status": "ok", "input": input_path, "output": output_path,
                "page_count": page_count, "targets": records,
                "metadata_cleared": metadata_keys, "xmp_cleared": clear_xmp}
    finally:
        if not doc.is_closed:
            doc.close()


def main() -> int:
    try:
        request = read_request()
        fitz = require_fitz()
        jobs = request.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("jobs must be a nonempty array")
        results = [redact_job(fitz, job) for job in jobs]
        emit({"status": "ok", "jobs": results})
        return 0
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
