"""Small pypdf utilities shared by the PDF inspection and filling entrypoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def load_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter  # type: ignore
        from pypdf.generic import ArrayObject, DictionaryObject, NameObject  # type: ignore
        return PdfReader, PdfWriter, ArrayObject, DictionaryObject, NameObject
    except ImportError as exc:
        raise RuntimeError("pypdf is required to inspect or fill this PDF") from exc


def deref(value: Any) -> Any:
    """Resolve a pypdf indirect object where possible."""
    try:
        return value.get_object()
    except AttributeError:
        return value


def pdf_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = deref(value)
    if value is None:
        return None
    return str(value)


def json_value(value: Any) -> Any:
    """Produce a JSON-safe representation of PDF primitives/arrays/dictionaries."""
    value = deref(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


def inherited(obj: Any, key: str) -> Any:
    """Look up a widget/field property through its /Parent chain."""
    current = deref(obj)
    seen: Set[Tuple[int, int]] = set()
    while current is not None:
        marker = getattr(current, "indirect_reference", None)
        marker_key = (getattr(marker, "idnum", 0), getattr(marker, "generation", 0))
        if marker_key in seen:
            break
        seen.add(marker_key)
        if key in current:
            return deref(current[key])
        parent = current.get("/Parent") if hasattr(current, "get") else None
        current = deref(parent) if parent is not None else None
    return None


def qualified_name(obj: Any) -> Optional[str]:
    """Return the fully qualified /T name of a widget or terminal field."""
    pieces: List[str] = []
    current = deref(obj)
    seen: Set[Tuple[int, int]] = set()
    while current is not None:
        marker = getattr(current, "indirect_reference", None)
        marker_key = (getattr(marker, "idnum", 0), getattr(marker, "generation", 0))
        if marker_key in seen:
            break
        seen.add(marker_key)
        title = current.get("/T") if hasattr(current, "get") else None
        if title is not None:
            pieces.append(str(deref(title)))
        parent = current.get("/Parent") if hasattr(current, "get") else None
        current = deref(parent) if parent is not None else None
    return ".".join(reversed(pieces)) if pieces else None


def widget_on_states(widget_or_field: Any) -> List[str]:
    """Return selectable /AP /N names excluding the conventional off state."""
    ap = inherited(widget_or_field, "/AP")
    if not hasattr(ap, "get"):
        return []
    normal = deref(ap.get("/N"))
    if not hasattr(normal, "keys"):
        return []
    return [str(key).lstrip("/") for key in normal.keys() if str(key) != "/Off"]


def collect_widgets(reader: Any) -> List[Dict[str, Any]]:
    widgets: List[Dict[str, Any]] = []
    for page_index, page in enumerate(reader.pages):
        annotations = deref(page.get("/Annots")) or []
        for annotation_ref in annotations:
            annotation = deref(annotation_ref)
            if not hasattr(annotation, "get"):
                continue
            subtype = str(annotation.get("/Subtype", ""))
            field_type = inherited(annotation, "/FT")
            if subtype != "/Widget" and field_type is None:
                continue
            widgets.append({
                "page": page_index + 1,
                "name": qualified_name(annotation),
                "field_type": pdf_string(field_type),
                "rect": json_value(annotation.get("/Rect")),
                "on_states": widget_on_states(annotation),
            })
    return widgets


def normalize(value: Any) -> Any:
    """Normalize pypdf values for stable semantic comparison."""
    value = deref(value)
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if value is None:
        return None
    return str(value).lstrip("/")


def field_value_map(reader: Any) -> Dict[str, Any]:
    fields = reader.get_fields() or {}
    return {str(name): normalize(field.get("/V")) for name, field in fields.items()}


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def require_paths(source: str, output: Optional[str] = None) -> Tuple[Path, Optional[Path]]:
    source_path = Path(source)
    if not source_path.is_file():
        raise RuntimeError("source_pdf does not exist or is not a regular file: %s" % source)
    output_path = Path(output) if output is not None else None
    if output_path is not None and source_path.resolve() == output_path.resolve():
        raise RuntimeError("output_pdf must be different from source_pdf")
    return source_path, output_path
