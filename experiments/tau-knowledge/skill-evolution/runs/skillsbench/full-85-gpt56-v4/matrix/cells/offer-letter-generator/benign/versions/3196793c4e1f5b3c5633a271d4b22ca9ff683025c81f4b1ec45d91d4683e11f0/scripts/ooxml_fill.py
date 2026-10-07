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


def _remove_fully_covered_paragraphs(
    root: ET.Element, refs: list[TextRef], start: int, end: int
) -> None:
    """Remove paragraphs wholly inside a false conditional region.

    Text-only replacement handles inline conditions. Removing fully covered
    paragraphs also avoids leaving visible blank conditional sections when the
    markers occupy their own paragraphs.
    """
    paragraphs = list(root.iter(W_P))
    positions = {id(p): index for index, p in enumerate(paragraphs)}
    first = _paragraph_for_offset(refs, start)
    last = _paragraph_for_offset(refs, end - 1)
    if first is None or last is None:
        return
    first_i, last_i = positions[id(first)], positions[id(last)]
    if first_i > last_i:
        first_i, last_i = last_i, first_i

    bounds: dict[int, tuple[int, int]] = {}
    for ref in refs:
        if ref.paragraph is None or ref.end <= ref.start:
            continue
        key = id(ref.paragraph)
        before = bounds.get(key)
        bounds[key] = (ref.start, ref.end) if before is None else (
            min(before[0], ref.start), max(before[1], ref.end)
        )

    parent = {child: node for node in root.iter() for child in node}
    for index in range(first_i, last_i + 1):
        paragraph = paragraphs[index]
        interval = bounds.get(id(paragraph))
        # Interior paragraphs are necessarily conditional content, including
        # image-only/empty paragraphs. End paragraphs are removed only if all
        # their text belongs to the matched conditional span.
        wholly_inside = interval is not None and interval[0] >= start and interval[1] <= end
        if (first_i < index < last_i) or wholly_inside:
            container = parent.get(paragraph)
            if container is not None:
                container.remove(paragraph)


def _is_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"yes", "true", "1"}


def _resolve_conditionals(root: ET.Element, values: dict[str, Any]) -> bool:
    changed = False
    # Rebuild spans after each substitution because XML text lengths change.
    while True:
        refs = _text_refs(root)
        text = _logical_text(refs)
        match = CONDITIONAL.search(text)
        if match is None:
            break
        key = match.group(1)
        if key not in values:
            raise FillError("conditional requires missing data key: " + key)
        if _is_enabled(values[key]):
            replacement = match.group(2)
        else:
            _remove_fully_covered_paragraphs(root, refs, match.start(), match.end())
            replacement = ""
        _replace_span(root, match.start(), match.end(), replacement)
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
