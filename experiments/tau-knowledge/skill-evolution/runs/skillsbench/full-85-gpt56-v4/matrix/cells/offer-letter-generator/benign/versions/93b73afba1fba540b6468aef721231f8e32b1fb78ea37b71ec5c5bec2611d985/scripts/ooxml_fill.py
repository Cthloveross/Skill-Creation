"""Dependency-free OOXML logical-text replacement for DOCX templates."""
from __future__ import annotations

import copy
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W_T = "{" + W_NS + "}t"
W_P = "{" + W_NS + "}p"
XML_SPACE = "{" + XML_NS + "}space"
CONDITIONAL = re.compile(
    r"\{\{IF_([A-Za-z][A-Za-z0-9_]*)\}\}(.*?)\{\{END_IF_\1\}\}", re.DOTALL
)
PLACEHOLDER = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}")
ANY_MARKER = re.compile(r"\{\{[^{}]+\}\}")


class FillError(Exception):
    """A template or package condition that makes safe filling impossible."""


@dataclass
class TextRef:
    element: ET.Element
    start: int
    end: int
    paragraph: ET.Element | None


def _text_refs(root: ET.Element) -> list[TextRef]:
    """Return visible Word text nodes with offsets in their logical text stream."""
    parent = {child: node for node in root.iter() for child in node}
    refs: list[TextRef] = []
    offset = 0
    for node in root.iter(W_T):
        value = node.text or ""
        paragraph = parent.get(node)
        while paragraph is not None and paragraph.tag != W_P:
            paragraph = parent.get(paragraph)
        refs.append(TextRef(node, offset, offset + len(value), paragraph))
        offset += len(value)
    return refs


def _logical_text(refs: list[TextRef]) -> str:
    return "".join(ref.element.text or "" for ref in refs)


def _set_text(element: ET.Element, value: str) -> None:
    element.text = value
    # Word requires xml:space for leading/trailing whitespace in a w:t node.
    if value[:1].isspace() or value[-1:].isspace():
        element.set(XML_SPACE, "preserve")


def _replace_span(root: ET.Element, start: int, end: int, replacement: str) -> None:
    """Replace [start,end) in logical text, retaining prefix/suffix run ownership."""
    refs = _text_refs(root)
    affected = [ref for ref in refs if ref.start < end and ref.end > start]
    if not affected:
        raise FillError("internal error: matched template span has no Word text node")

    for index, ref in enumerate(affected):
        old = ref.element.text or ""
        left = max(start, ref.start) - ref.start
        right = min(end, ref.end) - ref.start
        if len(affected) == 1:
            new = old[:left] + replacement + old[right:]
        elif index == 0:
            new = old[:left] + replacement
        elif index == len(affected) - 1:
            # Keep the suffix in its original run so its formatting survives.
            new = old[right:]
        else:
            new = ""
        _set_text(ref.element, new)


def _paragraph_for_offset(refs: list[TextRef], offset: int) -> ET.Element | None:
    for ref in refs:
        if ref.start <= offset < ref.end:
            return ref.paragraph
    return None


def _fully_covered_paragraphs(
    root: ET.Element, refs: list[TextRef], start: int, end: int
) -> list[ET.Element]:
    """Identify paragraphs whose complete visible text is a false condition.

    The caller removes these only after deleting the logical span.  Computing
    the list before editing avoids stale logical offsets, and avoids deleting a
    paragraph that has text outside an inline conditional.
    """
    bounds: dict[int, tuple[ET.Element, int, int]] = {}
    for ref in refs:
        if ref.paragraph is None or ref.end <= ref.start:
            continue
        old = bounds.get(id(ref.paragraph))
        if old is None:
            bounds[id(ref.paragraph)] = (ref.paragraph, ref.start, ref.end)
        else:
            bounds[id(ref.paragraph)] = (ref.paragraph, min(old[1], ref.start), max(old[2], ref.end))
    return [paragraph for paragraph, left, right in bounds.values() if left >= start and right <= end]


def _remove_paragraphs(root: ET.Element, paragraphs: list[ET.Element]) -> None:
    parent = {child: node for node in root.iter() for child in node}
    # A paragraph can have been removed together with an ancestor; check that
    # it remains a direct child before attempting its removal.
    for paragraph in paragraphs:
        container = parent.get(paragraph)
        if container is not None and paragraph in list(container):
            container.remove(paragraph)

def _is_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"yes", "true", "1"}


def _condition_value(key: str, values: dict[str, Any]) -> Any:
    """Return the data value controlling IF_KEY.

    Templates commonly call the visible section ``IF_RELOCATION`` while the
    employee record names its yes/no field ``RELOCATION_PACKAGE``.  Prefer an
    exact field and then support that documented PACKAGE convention.
    """
    if key in values:
        return values[key]
    package_key = key + "_PACKAGE"
    if package_key in values:
        return values[package_key]
    raise FillError("conditional requires missing data key: " + key + " (or " + package_key + ")")


def _resolve_conditionals(root: ET.Element, values: dict[str, Any]) -> bool:
    changed = False
    # Resolve the innermost matching pair.  Each edit rebuilds text offsets.
    while True:
        refs = _text_refs(root)
        text = _logical_text(refs)
        match = CONDITIONAL.search(text)
        if match is None:
            break
        enabled = _is_enabled(_condition_value(match.group(1), values))
        if enabled:
            # Delete controls separately, right-to-left, so body runs and
            # their character formatting are retained verbatim.
            _replace_span(root, match.start(0) + len(match.group(0)) - len("{{END_IF_" + match.group(1) + "}}"), match.end(), "")
            refreshed = _logical_text(_text_refs(root))
            marker = "{{IF_" + match.group(1) + "}}"
            marker_start = refreshed.find(marker)
            if marker_start < 0:
                raise FillError("internal error: conditional start marker disappeared")
            _replace_span(root, marker_start, marker_start + len(marker), "")
        else:
            removable = _fully_covered_paragraphs(root, refs, match.start(), match.end())
            _replace_span(root, match.start(), match.end(), "")
            _remove_paragraphs(root, removable)
        changed = True
    return changed

def _resolve_placeholders(root: ET.Element, values: dict[str, Any]) -> bool:
    refs = _text_refs(root)
    text = _logical_text(refs)
    matches = list(PLACEHOLDER.finditer(text))
    if not matches:
        return False
    # Right-to-left preserves offsets of all earlier matches. It also ensures
    # braces that happen to occur in a data value are never treated as tokens.
    for match in reversed(matches):
        key = match.group(1)
        if key not in values:
            raise FillError("template requires missing data key: " + key)
        _replace_span(root, match.start(), match.end(), str(values[key]))
    return True


def _process_xml(xml_bytes: bytes, values: dict[str, Any]) -> tuple[bytes, bool]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise FillError("cannot parse XML part: " + str(exc)) from exc
    before = _logical_text(_text_refs(root))
    if "{{" not in before:
        return xml_bytes, False
    changed = _resolve_conditionals(root, values)
    changed = _resolve_placeholders(root, values) or changed
    after = _logical_text(_text_refs(root))
    if ANY_MARKER.search(after):
        raise FillError("unresolved placeholder or conditional marker remains in a Word XML part")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changed


def _validate_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path, "r") as package:
            names = set(package.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            missing = required - names
            if missing:
                raise FillError("generated package is missing required parts: " + ", ".join(sorted(missing)))
            for name in names:
                if name.endswith(".xml"):
                    ET.fromstring(package.read(name))
                if name.startswith("word/") and name.endswith(".xml"):
                    root = ET.fromstring(package.read(name))
                    if ANY_MARKER.search(_logical_text(_text_refs(root))):
                        raise FillError("validation found unresolved marker in " + name)
    except zipfile.BadZipFile as exc:
        raise FillError("generated output is not a valid DOCX ZIP package") from exc
    except ET.ParseError as exc:
        raise FillError("generated package contains invalid XML: " + str(exc)) from exc


def fill_docx(template: str, values: dict[str, Any], output: str) -> dict[str, Any]:
    """Fill *template* with *values*, validate it, and atomically write *output*."""
    source = Path(template)
    destination = Path(output)
    if not source.is_file():
        raise FillError("template does not exist: " + str(source))
    if source.resolve() == destination.resolve():
        raise FillError("output path must differ from the template path")
    destination.parent.mkdir(parents=True, exist_ok=True)

    modified_parts: list[str] = []
    temporary_name: str | None = None
    try:
        with zipfile.ZipFile(source, "r") as incoming:
            with tempfile.NamedTemporaryFile(
                prefix="filled-offer-", suffix=".docx", dir=str(destination.parent), delete=False
            ) as temporary:
                temporary_name = temporary.name
            with zipfile.ZipFile(temporary_name, "w", compression=zipfile.ZIP_DEFLATED) as outgoing:
                for info in incoming.infolist():
                    payload = incoming.read(info.filename)
                    if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                        payload, changed = _process_xml(payload, values)
                        if changed:
                            modified_parts.append(info.filename)
                    # Retain package member names and non-XML relationship/media bytes.
                    outgoing.writestr(info.filename, payload)
        _validate_docx(Path(temporary_name))
        os.replace(temporary_name, destination)
        temporary_name = None
    except zipfile.BadZipFile as exc:
        raise FillError("template is not a valid DOCX ZIP package") from exc
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)

    return {"output": str(destination), "modified_parts": modified_parts, "validated": True}
