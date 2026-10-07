#!/usr/bin/env python3
"""Emit a JSON inventory of terminal AcroForm fields and, when present, XFA data."""
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:
    raise SystemExit("pypdf is required to inspect interactive PDFs") from exc

from pdf_form_utils import (deref, enumerate_xfa_data, enumerate_xfa_template,
                            xfa_data_instance, xfa_dataset_root, xfa_packets)


def s(value):
    return None if value is None else str(value)


def button_states(field):
    # pypdf exposes widget states as /_States_ on get_fields() results.
    found = [str(state) for state in field.get("/_States_", [])]
    for item in [field] + [deref(x) for x in field.get("/Kids", [])]:
        ap = deref(item.get("/AP")) if item.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        if normal and hasattr(normal, "keys"):
            for key in normal.keys():
                if str(key) not in found:
                    found.append(str(key))
    return found


def main():
    request = json.load(sys.stdin)
    source = Path(request["input_pdf"])
    if not source.is_file():
        raise ValueError("input_pdf does not exist: " + str(source))
    reader = PdfReader(str(source))
    root = deref(reader.trailer["/Root"])
    acro = deref(root.get("/AcroForm")) if root.get("/AcroForm") else None
    if not acro:
        raise ValueError("PDF has no AcroForm; this Skill cannot safely fill a noninteractive PDF")
    fields = reader.get_fields() or {}
    result = []
    for name in sorted(fields):
        field = deref(fields[name])
        ftype = s(field.get("/FT"))
        options = []
        for option in field.get("/Opt", []):
            option = deref(option)
            options.append([s(v) for v in option] if isinstance(option, (list, tuple)) else s(option))
        result.append({"name": name, "type": ftype, "value": s(field.get("/V")),
                       "states": button_states(field) if ftype == "/Btn" else [],
                       "options": options, "flags": int(field.get("/Ff", 0)),
                       "label": s(field.get("/TU"))})
    packets = xfa_packets(acro)
    response = {"ok": True, "input_pdf": str(source), "field_count": len(result),
                "fields": result, "form_kind": "hybrid-xfa" if packets else "acroform"}
    if packets:
        _, dataset_root = xfa_dataset_root(packets)
        instance = xfa_data_instance(dataset_root)
        xfa_data_fields = enumerate_xfa_data(instance)
        paths = [entry["path"] for entry in xfa_data_fields]
        response["xfa_data_fields"] = xfa_data_fields
        response["xfa_template_fields"] = enumerate_xfa_template(packets, paths)
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
