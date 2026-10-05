#!/usr/bin/env python3
"""Inspect an interactive PDF. Reads one JSON object from stdin and emits one JSON object."""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from pdf_form import collect_widgets, deref, emit, field_value_map, json_value, load_pypdf, require_paths, widget_on_states


def main(request: Dict[str, Any]) -> Dict[str, Any]:
    source = request.get("source_pdf")
    if not isinstance(source, str) or not source:
        raise RuntimeError("source_pdf must be a nonempty string")
    source_path, _ = require_paths(source)
    PdfReader, _, _, _, _ = load_pypdf()
    reader = PdfReader(str(source_path))
    if reader.is_encrypted:
        raise RuntimeError("encrypted PDFs are unsupported")

    root = deref(reader.trailer.get("/Root"))
    acroform = deref(root.get("/AcroForm")) if hasattr(root, "get") else None
    if not acroform:
        if hasattr(root, "get") and root.get("/AcroForm") is None and root.get("/XFA") is not None:
            raise RuntimeError("XFA-only PDF is unsupported")
        raise RuntimeError("PDF has no AcroForm fields to inspect")

    fields = reader.get_fields() or {}
    widgets = collect_widgets(reader)
    widgets_by_name: Dict[str, List[Dict[str, Any]]] = {}
    for widget in widgets:
        if widget["name"]:
            widgets_by_name.setdefault(widget["name"], []).append(widget)

    report_fields = []
    for name, field in fields.items():
        options = deref(field.get("/Opt")) if hasattr(field, "get") else None
        on_states = widget_on_states(field)
        for widget in widgets_by_name.get(str(name), []):
            on_states.extend(widget.get("on_states", []))
        report_fields.append({
            "name": str(name),
            "field_type": str(field.get("/FT", "")),
            "current_value": json_value(field.get("/V")),
            "flags": json_value(field.get("/Ff")),
            "options": json_value(options) if options is not None else [],
            "on_states": sorted(set(on_states)),
            "widgets": widgets_by_name.get(str(name), []),
        })

    result: Dict[str, Any] = {
        "ok": True,
        "form_type": "AcroForm",
        "source_pdf": str(source_path),
        "page_count": len(reader.pages),
        "fields": report_fields,
        "semantic_values": field_value_map(reader),
        "acroform_has_xfa": bool(acroform.get("/XFA")) if hasattr(acroform, "get") else False,
    }
    if request.get("include_page_text", False):
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                text = "[text extraction failed: %s]" % exc
            pages.append({"page": number, "text": text})
        result["pages"] = pages
    return result


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise RuntimeError("stdin JSON must be an object")
        emit(main(request))
    except Exception as exc:
        emit({"ok": False, "error": str(exc)})
        sys.exit(1)
