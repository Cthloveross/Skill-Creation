"""Verify explicit redaction results without treating bibliography matches as leaks.

JSON stdin has the same jobs schema as redact_pdfs.py plus optional
max_unexpected_missing_words (default 50) and report_path. JSON stdout contains
results; report_path, when present, receives the complete pretty JSON report.
"""
from __future__ import annotations

from collections import Counter
import json
import sys
from pathlib import Path
from typing import Any

from pdf_common import (emit, page_texts, read_request, require_fitz,
                        reviewed_metadata_keys, target_pages, validate_path,
                        validate_target, words, write_utf8)


def xmp_present(doc: Any) -> bool:
    getter = getattr(doc, "get_xml_metadata", None)
    if getter is None:
        return False
    try:
        return bool((getter() or "").strip())
    except Exception:
        return True


def verify_job(fitz: Any, job: Any, limit: int) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise ValueError("each job must be an object")
    input_path = validate_path(job.get("input"), "job input")
    output_path = validate_path(job.get("output"), "job output")
    if not Path(input_path).is_file() or not Path(output_path).is_file():
        raise ValueError("both input and output PDF files must exist for verification")
    raw_targets = job.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("each verification job needs its explicit targets array")
    targets = [validate_target(item) for item in raw_targets]
    metadata_keys = reviewed_metadata_keys(job.get("metadata_clear"))
    clear_xmp = job.get("clear_xmp", False)
    if not isinstance(clear_xmp, bool):
        raise ValueError("clear_xmp must be true or false")

    original = fitz.open(input_path)
    redacted = fitz.open(output_path)
    try:
        original_text = page_texts(original)
        redacted_text = page_texts(redacted)
        failures: list[str] = []
        if original.page_count != redacted.page_count:
            failures.append(f"page count changed: {original.page_count} -> {redacted.page_count}")
        if original.page_count != len(redacted_text):
            failures.append("redacted document text/page structure could not be read")

        # Build the expected original text by deleting exactly the planned strings
        # only from their planned page scopes. This supports a legitimate matching
        # name/DOI that remains in an untouched bibliography.
        expected_text = list(original_text)
        target_results: list[dict[str, Any]] = []
        for target in targets:
            pages = target_pages(target, original.page_count, job.get("references_page"))
            remaining = 0
            for page_number in pages:
                if page_number < redacted.page_count:
                    remaining += len(redacted[page_number].search_for(target["text"]))
                expected_text[page_number] = expected_text[page_number].replace(target["text"], "")
            target_results.append({"text": target["text"], "scope": target["scope"],
                                   "checked_pages": pages, "remaining_rectangles": remaining})
            if remaining:
                failures.append(f"target remains in intended scope: {target['text']!r} ({remaining} rectangles)")

        original_expected_counts = Counter(words("\n".join(expected_text)))
        redacted_counts = Counter(words("\n".join(redacted_text)))
        missing = original_expected_counts - redacted_counts
        missing_count = sum(missing.values())
        if missing_count > limit:
            failures.append(f"{missing_count} non-target words are missing (limit {limit})")

        metadata = dict(redacted.metadata or {})
        uncleared = [key for key in metadata_keys if str(metadata.get(key, "")).strip()]
        if uncleared:
            failures.append("selected metadata fields still contain values: " + ", ".join(uncleared))
        if clear_xmp and xmp_present(redacted):
            failures.append("XMP metadata remains after clear_xmp was requested")

        return {
            "status": "pass" if not failures else "fail",
            "input": input_path,
            "output": output_path,
            "original_page_count": original.page_count,
            "redacted_page_count": redacted.page_count,
            "targets": target_results,
            "metadata_fields_checked": metadata_keys,
            "xmp_checked": clear_xmp,
            "unexpected_missing_word_count": missing_count,
            "unexpected_missing_word_examples": missing.most_common(25),
            "failures": failures,
        }
    finally:
        original.close()
        redacted.close()


def main() -> int:
    try:
        request = read_request()
        fitz = require_fitz()
        jobs = request.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("jobs must be a nonempty array")
        limit = request.get("max_unexpected_missing_words", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("max_unexpected_missing_words must be a nonnegative integer")
        results = [verify_job(fitz, job, limit) for job in jobs]
        payload = {"status": "pass" if all(x["status"] == "pass" for x in results) else "fail", "jobs": results}
        report_path = request.get("report_path")
        if report_path is not None:
            report_path = validate_path(report_path, "report_path")
            write_utf8(report_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            payload["report_path"] = report_path
        emit(payload)
        return 0 if payload["status"] == "pass" else 2
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
