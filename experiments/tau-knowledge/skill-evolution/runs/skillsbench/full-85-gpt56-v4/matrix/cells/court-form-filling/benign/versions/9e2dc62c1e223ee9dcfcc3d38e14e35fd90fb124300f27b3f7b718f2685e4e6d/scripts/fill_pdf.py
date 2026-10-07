#!/usr/bin/env python3
"""Fill explicit AcroForm and/or XFA dataset fields, then reopen to verify."""
import json
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject, TextStringObject
except ImportError as exc:
    raise SystemExit("pypdf is required to fill interactive PDFs") from exc

from pdf_form_utils import (deref, enumerate_xfa_data, find_xfa_data_node,
                            xfa_data_instance, xfa_dataset_root, xfa_packets)


def as_text(value):
    return "" if value is None else str(value)


def terminal_states(field):
    # /_States_ is supplied by pypdf for some terminal fields.
    states = [str(state) for state in field.get("/_States_", [])]
    for item in [field] + [deref(k) for k in field.get("/Kids", [])]:
        ap = deref(item.get("/AP")) if item.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        if normal and hasattr(normal, "keys"):
            for key in normal.keys():
                if str(key) not in states:
                    states.append(str(key))
    return states


def set_button(field, requested):
    requested = str(requested)
    states = terminal_states(field)
    if requested not in states:
        raise ValueError("button value %r is not an advertised state; states=%r" % (requested, states))
    state = NameObject(requested)
    field[NameObject("/V")] = state
    for widget in [field] + [deref(k) for k in field.get("/Kids", [])]:
        ap = deref(widget.get("/AP")) if widget.get("/AP") else None
        normal = deref(ap.get("/N")) if ap and ap.get("/N") else None
        keys = [str(x) for x in normal.keys()] if normal and hasattr(normal, "keys") else []
        if requested in keys:
            widget[NameObject("/AS")] = state
        elif "/Off" in keys:
            widget[NameObject("/AS")] = NameObject("/Off")


def cloned_fields(writer):
    """Return writer-side terminal field dictionaries indexed by full field name."""
    root = deref(writer._root_object)
    acro = deref(root.get("/AcroForm"))
    if not acro:
        return {}

    def walk(entries, prefix=""):
        answer = {}
        for ref in entries:
            obj = deref(ref)
            part = str(obj.get("/T", ""))
            full = part if not prefix else (prefix + "." + part if part else prefix)
            if obj.get("/FT"):
                answer[full] = obj
            if obj.get("/Kids"):
                answer.update(walk(obj["/Kids"], full))
        return answer
    return walk(acro.get("/Fields", []))


def acro_parts(name, drop_pages=False):
    parts = [re.sub(r"\[\d+\]$", "", part) for part in str(name).split(".")]
    return [part for part in parts if not (drop_pages and re.fullmatch(r"Page\d+", part))]


def mirror_xfa_text_into_acro(cloned, xfa_values):
    """Supplement hybrid PDFs with unambiguous Acro text /V values.

    XFA is authoritative, but many generic PDF tools inspect only AcroForm /V.
    Matching the complete structural tail avoids copying similarly named XFA fields
    (for example different FillField2 controls) into the wrong widget.
    """
    mirrored = {}
    for data_path, value in xfa_values.items():
        wanted = [part for part in str(data_path).split("/") if part]
        wanted_no_pages = [part for part in wanted if not re.fullmatch(r"Page\d+", part)]
        matches = []
        for name, field in cloned.items():
            if str(field.get("/FT")) not in ("/Tx", "/Ch"):
                continue
            actual = acro_parts(name)
            actual_no_pages = acro_parts(name, drop_pages=True)
            if (len(actual) >= len(wanted) and actual[-len(wanted):] == wanted) or \
               (len(actual_no_pages) >= len(wanted_no_pages) and
                actual_no_pages[-len(wanted_no_pages):] == wanted_no_pages):
                matches.append(name)
        if len(matches) == 1:
            cloned[matches[0]][NameObject("/V")] = TextStringObject(value)
            mirrored[data_path] = matches[0]
    return mirrored


def update_xfa(reader, acro, desired):
    """Mutate the reader's XFA datasets stream and return normalized desired values."""
    packets = xfa_packets(acro)
    if not desired:
        return {}, packets
    if not packets:
        raise ValueError("xfa_fields was supplied but PDF has no XFA datasets packet")
    stream, dataset_root = xfa_dataset_root(packets)
    instance = xfa_data_instance(dataset_root)
    legal = {entry["path"] for entry in enumerate_xfa_data(instance)}
    missing = sorted(set(desired) - legal)
    if missing:
        raise ValueError("unknown or non-leaf XFA data paths: " + ", ".join(missing))
    normalized = {str(path): as_text(value) for path, value in desired.items()}
    for path, value in normalized.items():
        find_xfa_data_node(instance, path).text = value
    # pypdf stream objects support set_data and clone_document_from_reader preserves it.
    from xml.etree import ElementTree as ET
    stream.set_data(ET.tostring(dataset_root, encoding="utf-8", xml_declaration=False))
    return normalized, packets


def read_xfa_values(reader, requested):
    if not requested:
        return {}
    acro = deref(deref(reader.trailer["/Root"]).get("/AcroForm"))
    packets = xfa_packets(acro)
    _, dataset_root = xfa_dataset_root(packets)
    instance = xfa_data_instance(dataset_root)
    return {path: as_text(find_xfa_data_node(instance, path).text) for path in requested}


def main():
    request = json.load(sys.stdin)
    source = Path(request["input_pdf"])
    output = Path(request["output_pdf"])
    desired = request.get("fields", {})
    desired_xfa = request.get("xfa_fields", {})
    if not isinstance(desired, dict) or not isinstance(desired_xfa, dict):
        raise ValueError("fields and xfa_fields must each be objects mapping exact field names to values")
    if not source.is_file():
        raise ValueError("input_pdf does not exist: " + str(source))
    if source.resolve() == output.resolve():
        raise ValueError("output_pdf must differ from input_pdf to preserve the blank original")

    reader = PdfReader(str(source))
    root = deref(reader.trailer["/Root"])
    acro = deref(root.get("/AcroForm")) if root.get("/AcroForm") else None
    if not acro:
        raise ValueError("PDF has no AcroForm")
    source_fields = reader.get_fields() or {}
    missing = sorted(set(desired) - set(source_fields))
    if missing:
        print(json.dumps({"ok": False, "missing_fields": missing, "mismatches": [], "written_fields": []}, indent=2))
        sys.exit(2)

    normalized_xfa, _ = update_xfa(reader, acro, desired_xfa)
    text_values, button_values = {}, {}
    for name, value in desired.items():
        kind = str(deref(source_fields[name]).get("/FT"))
        if kind in ("/Tx", "/Ch"):
            text_values[name] = as_text(value)
        elif kind == "/Btn":
            button_values[name] = value
        else:
            raise ValueError("field %r has unsupported type %s" % (name, kind))

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    # Standard pypdf update maintains ordinary AcroForm widget values/appearances.
    if text_values:
        for page in writer.pages:
            try:
                writer.update_page_form_field_values(page, text_values, auto_regenerate=False)
            except TypeError:
                writer.update_page_form_field_values(page, text_values)
    cloned = cloned_fields(writer)
    for name, value in text_values.items():
        if name in cloned:
            cloned[name][NameObject("/V")] = TextStringObject(value)
    for name, value in button_values.items():
        if name not in cloned:
            raise ValueError("could not locate cloned button field " + name)
        set_button(cloned[name], value)
    mirrored_xfa = mirror_xfa_text_into_acro(cloned, normalized_xfa)
    cloned_acro = deref(deref(writer._root_object).get("/AcroForm"))
    cloned_acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)

    reopened = PdfReader(str(output))
    observed_fields = reopened.get_fields() or {}
    observed, mismatches = {}, []
    for name, expected in desired.items():
        actual = observed_fields.get(name)
        actual_value = as_text(deref(actual).get("/V")) if actual else None
        expected_value = as_text(expected)
        observed[name] = actual_value
        if actual_value != expected_value:
            mismatches.append({"field": name, "expected": expected_value, "actual": actual_value})
    observed_xfa = read_xfa_values(reopened, normalized_xfa)
    for path, expected in normalized_xfa.items():
        actual = observed_xfa.get(path)
        observed["xfa:" + path] = actual
        if actual != expected:
            mismatches.append({"field": "xfa:" + path, "expected": expected, "actual": actual})
    report = {"ok": not mismatches, "output_pdf": str(output),
              "written_fields": sorted(desired), "written_xfa_fields": sorted(normalized_xfa),
              "mirrored_xfa_fields": mirrored_xfa, "missing_fields": [], "mismatches": mismatches, "observed": observed}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if mismatches:
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
