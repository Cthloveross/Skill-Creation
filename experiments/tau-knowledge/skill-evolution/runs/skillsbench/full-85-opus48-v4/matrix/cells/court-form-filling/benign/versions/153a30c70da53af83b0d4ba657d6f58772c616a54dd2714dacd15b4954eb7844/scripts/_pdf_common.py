"""Shared pypdf helpers for the interactive PDF form filler Skill.

Imports pypdf, falling back to PyPDF2. Provides reader/writer construction
and field-state extraction so the entry scripts stay small.
"""
import sys

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject
except Exception:  # pragma: no cover - fallback for older envs
    from PyPDF2 import PdfReader, PdfWriter  # type: ignore
    from PyPDF2.generic import NameObject, BooleanObject  # type: ignore


def _as_text(v):
    if v is None:
        return None
    try:
        return str(v)
    except Exception:
        return repr(v)


def field_states(obj):
    """Return the list of valid on-state names for a button field."""
    states = set()
    s = obj.get('/_States_') if hasattr(obj, 'get') else None
    if s:
        for st in s:
            states.add(_as_text(st))
    return sorted(states)


def read_fields(pdf_path):
    reader = PdfReader(pdf_path)
    fields = reader.get_fields() or {}
    out = []
    for name, obj in fields.items():
        ft = _as_text(obj.get('/FT')) if hasattr(obj, 'get') else None
        val = obj.get('/V') if hasattr(obj, 'get') else None
        tu = obj.get('/TU') if hasattr(obj, 'get') else None
        out.append({
            'name': _as_text(name),
            'type': ft,
            'value': _as_text(val),
            'states': field_states(obj),
            'tooltip': _as_text(tu),
        })
    return out


def set_need_appearances(writer):
    try:
        writer.set_need_appearances_writer(True)
        return
    except Exception:
        pass
    try:
        root = writer._root_object
        if '/AcroForm' in root:
            root['/AcroForm'][NameObject('/NeedAppearances')] = BooleanObject(True)
    except Exception:
        pass
