#!/usr/bin/env python3
"""Fill named AcroForm fields and verify values after reopening the saved PDF."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from pdf_form import deref, emit, field_value_map, load_pypdf, normalize, require_paths


def expected_value(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return normalize(value)


def main(request: Dict[str, Any]) -> Dict[str, Any]:
    source = request.get("source_pdf")
    output = request.get("output_pdf")
    assignments = request.get("assignments")
    if not isinstance(source, str) or not source:
        raise RuntimeError("source_pdf must be a nonempty string")
    if not isinstance(output, str) or not output:
        raise RuntimeError("output_pdf must be a nonempty string")
    if not isinstance(assignments, dict) or not assignments:
        raise RuntimeError("assignments must be a nonempty object containing only intended fields")
    if any(not isinstance(key, str) or not key for key in assignments):
        raise RuntimeError("every assignment key must be a nonempty field-name string")
    if any(value is None or isinstance(value, (dict, bool, int, float)) for value in assignments.values()):
        raise RuntimeError("assignment values must be strings or lists of strings")
    if any(isinstance(value, list) and not all(isinstance(item, str) for item in value) for value in assignments.values()):
        raise RuntimeError("list assignment values must contain only strings")

    source_path, output_path = require_paths(source, output)
    assert output_path is not None
    PdfReader, PdfWriter, _, _, _ = load_pypdf()
    reader = PdfReader(str(source_path))
    if reader.is_encrypted:
        raise RuntimeError("encrypted PDFs are unsupported")
    root = deref(reader.trailer.get("/Root"))
    if not hasattr(root, "get") or not root.get("/AcroForm"):
        raise RuntimeError("PDF has no AcroForm fields to fill")

    source_fields = reader.get_fields() or {}
    missing = sorted(set(assignments) - set(source_fields))
    if missing:
        raise RuntimeError("unknown field name(s): " + ", ".join(missing))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    # Update every page because widgets for one logical field can occur on more than one page.
    for page in writer.pages:
        writer.update_page_form_field_values(page, assignments, auto_regenerate=True)
    try:
        writer.set_need_appearances_writer(True)
    except AttributeError:
        # Older pypdf versions still retain the values written above.
        pass
    with output_path.open("wb") as stream:
        writer.write(stream)

    # Reopen from disk, rather than trusting the in-memory writer, to verify semantic values.
    reopened = PdfReader(str(output_path))
    if reopened.is_encrypted:
        raise RuntimeError("saved output unexpectedly became encrypted")
    actual = field_value_map(reopened)
    read_back = {name: actual.get(name) for name in assignments}
    expected = {name: expected_value(value) for name, value in assignments.items()}
    mismatches = {
        name: {"expected": expected[name], "actual": read_back[name]}
        for name in assignments
        if read_back[name] != expected[name]
    }
    return {
        "ok": not bool(mismatches),
        "verified": not bool(mismatches),
        "source_pdf": str(source_path),
        "output_pdf": str(output_path),
        "requested": expected,
        "read_back": read_back,
        "mismatches": mismatches,
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise RuntimeError("stdin JSON must be an object")
        result = main(request)
        emit(result)
        if not result["ok"]:
            sys.exit(1)
    except Exception as exc:
        emit({"ok": False, "verified": False, "error": str(exc)})
        sys.exit(1)
