#!/usr/bin/env python3
"""Fill explicitly selected AcroForm fields and reopen the saved PDF to verify them."""
import json
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject
except ImportError as exc:
    raise SystemExit("pypdf is required to fill interactive PDFs") from exc


def deref(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def as_text(value):
    return "" if value is None else str(value)


def terminal_states(field):
    states = []
    for item in [field] + [deref(k) for k in field.get("/Kids", [])]:
        ap = deref(item.get("/AP")) if item.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        if normal and hasattr(normal, "keys"):
            for key in normal.keys():
                value = str(key)
                if value not in states:
                    states.append(value)
    return states


def set_button(field, requested):
    """Set both semantic /V and each widget appearance state."""
    requested = str(requested)
    states = terminal_states(field)
    if requested not in states:
        raise ValueError("button value %r is not an advertised state for field; states=%r" % (requested, states))
    state = NameObject(requested)
    field[NameObject("/V")] = state
    widgets = [field] + [deref(k) for k in field.get("/Kids", [])]
    for widget in widgets:
        ap = deref(widget.get("/AP")) if widget.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        # Radio buttons may have a distinct on-state per widget. Off is valid for all.
        if normal and requested in [str(x) for x in normal.keys()]:
            widget[NameObject("/AS")] = state
        elif normal and "/Off" in [str(x) for x in normal.keys()]:
            widget[NameObject("/AS")] = NameObject("/Off")


def main():
    request = json.load(sys.stdin)
    source = Path(request["input_pdf"])
    output = Path(request["output_pdf"])
    desired = request["fields"]
    if not isinstance(desired, dict):
        raise ValueError("fields must be an object mapping exact field names to values")
    if not source.is_file():
        raise ValueError("input_pdf does not exist: " + str(source))
    if source.resolve() == output.resolve():
        raise ValueError("output_pdf must differ from input_pdf to preserve the blank original")

    reader = PdfReader(str(source))
    root = deref(reader.trailer["/Root"])
    acro = deref(root.get("/AcroForm")) if root.get("/AcroForm") else None
    if not acro or acro.get("/XFA"):
        raise ValueError("requires a non-XFA PDF with an AcroForm")
    source_fields = reader.get_fields() or {}
    missing = sorted(set(desired) - set(source_fields))
    if missing:
        report = {"ok": False, "missing_fields": missing, "mismatches": [], "written_fields": []}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(2)

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    text_values = {}
    button_values = {}
    for name, value in desired.items():
        field = deref(source_fields[name])
        kind = str(field.get("/FT"))
        if kind == "/Btn":
            button_values[name] = value
        elif kind in ("/Tx", "/Ch"):
            text_values[name] = as_text(value)
        else:
            raise ValueError("field %r has unsupported type %s" % (name, kind))

    # pypdf performs standard text/choice updates and maintains page annotations.
    for page in writer.pages:
        if text_values:
            try:
                writer.update_page_form_field_values(page, text_values, auto_regenerate=False)
            except TypeError:  # older pypdf API
                writer.update_page_form_field_values(page, text_values)

    # Obtain cloned fields, then make button state updates directly in the output tree.
    cloned_root = deref(writer._root_object)
    cloned_acro = deref(cloned_root.get("/AcroForm"))
    cloned_fields = PdfReader  # sentinel replaced after write; direct tree lookup below

    def walk(entries, prefix=""):
        found = {}
        for ref in entries:
            obj = deref(ref)
            partial = str(obj.get("/T", ""))
            full = partial if not prefix else (prefix + "." + partial if partial else prefix)
            kids = obj.get("/Kids", [])
            if obj.get("/FT"):
                found[full] = obj
            if kids:
                found.update(walk(kids, full))
        return found

    cloned_by_name = walk(cloned_acro.get("/Fields", []))
    for name, value in button_values.items():
        if name not in cloned_by_name:
            raise ValueError("could not locate cloned button field " + name)
        set_button(cloned_by_name[name], value)
    cloned_acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)

    # Semantic verification from a new reader, not the in-memory writer.
    reopened = PdfReader(str(output))
    observed_fields = reopened.get_fields() or {}
    mismatches = []
    observed = {}
    for name, expected in desired.items():
        actual = observed_fields.get(name)
        actual_value = as_text(deref(actual).get("/V")) if actual else None
        expected_value = as_text(expected)
        observed[name] = actual_value
        if actual_value != expected_value:
            mismatches.append({"field": name, "expected": expected_value, "actual": actual_value})
    report = {
        "ok": not mismatches,
        "output_pdf": str(output),
        "written_fields": sorted(desired),
        "missing_fields": [],
        "mismatches": mismatches,
        "observed": observed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if mismatches:
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        sys.exit(2)
