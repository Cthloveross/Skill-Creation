#!/usr/bin/env python3
"""Emit a JSON inventory of terminal AcroForm fields in a supplied PDF."""
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:
    raise SystemExit("pypdf is required to inspect interactive PDFs") from exc


def s(value):
    if value is None:
        return None
    return str(value)


def deref(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def button_states(field):
    """Return distinct /AP /N export states from a terminal and its widgets."""
    found = []
    candidates = [field] + [deref(x) for x in field.get("/Kids", [])]
    for item in candidates:
        ap = deref(item.get("/AP")) if item.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        if normal and hasattr(normal, "keys"):
            for key in normal.keys():
                name = str(key)
                if name not in found:
                    found.append(name)
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
    if acro.get("/XFA"):
        raise ValueError("PDF contains XFA form data; this AcroForm-only Skill does not safely populate XFA")
    fields = reader.get_fields() or {}
    result = []
    for name in sorted(fields):
        field = deref(fields[name])
        ftype = s(field.get("/FT"))
        opts = field.get("/Opt", [])
        normalized_opts = []
        for opt in opts:
            item = deref(opt)
            if isinstance(item, (list, tuple)):
                normalized_opts.append([s(v) for v in item])
            else:
                normalized_opts.append(s(item))
        result.append({
            "name": name,
            "type": ftype,
            "value": s(field.get("/V")),
            "states": button_states(field) if ftype == "/Btn" else [],
            "options": normalized_opts,
            "flags": int(field.get("/Ff", 0)),
        })
    print(json.dumps({"ok": True, "input_pdf": str(source), "field_count": len(result), "fields": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        sys.exit(2)
