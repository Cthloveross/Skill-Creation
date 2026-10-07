#!/usr/bin/env python3
"""Fill run-split Word OOXML placeholders and a relocation conditional.

Reads one JSON object from stdin and emits one JSON result object on stdout.
See SKILL.md for the public schema.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
import xml.etree.ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_T = "{" + W_NS + "}t"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
IF_MARKER = "{{IF_RELOCATION}}"
END_MARKER = "{{END_IF_RELOCATION}}"
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
ANY_MARKER_RE = re.compile(r"\{\{[^{}]+\}\}")
CONTROL_RE = re.compile(r"\{\{(?:IF_RELOCATION|END_IF_RELOCATION)\}\}")


class FillError(Exception):
    """A clear, input/template-related failure that must not produce output."""


def parse_xml(data: bytes) -> ET.Element:
    # Keep comments and processing instructions if a changed part contains them.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(data, parser=parser)


def word_text_nodes(root: ET.Element) -> List[ET.Element]:
    return [element for element in root.iter() if element.tag == W_T]


def logical_text(nodes: Sequence[ET.Element]) -> str:
    return "".join(node.text or "" for node in nodes)


def ensure_xml_text(value: str, key: str) -> None:
    """Reject XML 1.0-invalid characters before they can corrupt a DOCX part."""
    for char in value:
        code = ord(char)
        allowed = code in (0x9, 0xA, 0xD) or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF
        if not allowed:
            raise FillError("value for %s contains an XML 1.0-invalid character" % key)


def normalize_values(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise FillError("employee data must be a JSON object")
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise FillError("employee data contains a non-string key")
        if isinstance(value, (dict, list)):
            raise FillError("value for %s must be a scalar or null, not an object or array" % key)
        if value is None:
            text = ""
        elif isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value)
        ensure_xml_text(text, key)
        result[key] = text
    return result


def merge_edits(edits: Iterable[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """Validate sorted deletion/replacement edits and merge overlapping deletions."""
    ordered = sorted(edits, key=lambda item: (item[0], item[1]))
    merged: List[Tuple[int, int, str]] = []
    for start, end, replacement in ordered:
        if start > end:
            raise FillError("internal invalid text span")
        if not merged:
            merged.append((start, end, replacement))
            continue
        old_start, old_end, old_replacement = merged[-1]
        if start < old_end:
            # Conditional false-regions can nest. They are all deletions and
            # therefore safely collapse to their union.
            if replacement or old_replacement:
                raise FillError("overlapping template substitutions")
            merged[-1] = (old_start, max(old_end, end), "")
        else:
            merged.append((start, end, replacement))
    return merged


def relocation_edits(text: str, keep: bool) -> List[Tuple[int, int, str]]:
    """Return edits for balanced relocation markers, supporting nested regions."""
    tokens = list(CONTROL_RE.finditer(text))
    stack: List[int] = []
    edits: List[Tuple[int, int, str]] = []
    for token in tokens:
        if token.group(0) == IF_MARKER:
            stack.append(token.start())
            if keep:
                edits.append((token.start(), token.end(), ""))
        else:
            if not stack:
                raise FillError("found {{END_IF_RELOCATION}} without a matching {{IF_RELOCATION}}")
            start = stack.pop()
            if keep:
                edits.append((token.start(), token.end(), ""))
            elif not stack:
                # Removing the outer region also removes any nested regions.
                edits.append((start, token.end(), ""))
    if stack:
        raise FillError("found {{IF_RELOCATION}} without a matching {{END_IF_RELOCATION}}")
    return merge_edits(edits)


def node_ranges(nodes: Sequence[ET.Element]) -> Tuple[List[int], List[int], List[str]]:
    starts: List[int] = []
    ends: List[int] = []
    source: List[str] = []
    position = 0
    for node in nodes:
        text = node.text or ""
        starts.append(position)
        position += len(text)
        ends.append(position)
        source.append(text)
    return starts, ends, source


def apply_edits(nodes: Sequence[ET.Element], edits: Sequence[Tuple[int, int, str]]) -> bool:
    """Apply logical-text edits while assigning untouched text back to its nodes."""
    if not edits:
        return False
    starts, ends, source = node_ranges(nodes)
    total = ends[-1] if ends else 0
    for start, end, _replacement in edits:
        if start < 0 or end > total or start > end:
            raise FillError("template edit lies outside the available Word text")

    buckets: List[List[str]] = [[] for _ in nodes]

    def append_original(left: int, right: int) -> None:
        if left >= right:
            return
        for index, (node_start, node_end) in enumerate(zip(starts, ends)):
            begin = max(left, node_start)
            finish = min(right, node_end)
            if begin < finish:
                buckets[index].append(source[index][begin - node_start:finish - node_start])

    def anchor(position: int) -> int:
        # Use the node containing the start. At a boundary, attach to the
        # preceding nonempty node so replacement order remains natural.
        for index, (node_start, node_end) in enumerate(zip(starts, ends)):
            if node_start <= position < node_end:
                return index
        for index in range(len(nodes) - 1, -1, -1):
            if ends[index] <= position and ends[index] > starts[index]:
                return index
        if nodes:
            return 0
        raise FillError("cannot place replacement in a part with no Word text nodes")

    cursor = 0
    for start, end, replacement in edits:
        append_original(cursor, start)
        if replacement:
            buckets[anchor(start)].append(replacement)
        cursor = end
    append_original(cursor, total)

    for node, pieces in zip(nodes, buckets):
        value = "".join(pieces)
        node.text = value
        if value and (value[0].isspace() or value[-1].isspace()):
            node.set(XML_SPACE, "preserve")
    return True


def substitute_edits(text: str, values: Dict[str, str]) -> Tuple[List[Tuple[int, int, str]], int]:
    edits: List[Tuple[int, int, str]] = []
    count = 0
    for match in PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        if key not in values:
            raise FillError("template requires placeholder %s, but it is missing from employee data" % key)
        edits.append((match.start(), match.end(), values[key]))
        count += 1
    return edits, count


def contains_template_marker(text: str) -> bool:
    return ANY_MARKER_RE.search(text) is not None


def is_word_xml(name: str) -> bool:
    return name.startswith("word/") and name.endswith(".xml")


def validate_output(output_path: Path) -> None:
    try:
        with zipfile.ZipFile(output_path, "r") as archive:
            corrupt = archive.testzip()
            if corrupt is not None:
                raise FillError("output DOCX has a corrupt ZIP member: %s" % corrupt)
            names = set(archive.namelist())
            for mandatory in ("[Content_Types].xml", "word/document.xml"):
                if mandatory not in names:
                    raise FillError("output DOCX is missing required part %s" % mandatory)
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                try:
                    root = parse_xml(archive.read(name))
                except ET.ParseError as exc:
                    raise FillError("output XML part %s does not parse: %s" % (name, exc)) from exc
                if is_word_xml(name) and contains_template_marker(logical_text(word_text_nodes(root))):
                    raise FillError("unresolved template marker remains in %s" % name)
    except zipfile.BadZipFile as exc:
        raise FillError("output is not a valid DOCX ZIP package: %s" % exc) from exc


def fill(template_path: Path, output_path: Path, values: Dict[str, str]) -> Dict[str, Any]:
    if not template_path.is_file():
        raise FillError("template_path does not exist or is not a file: %s" % template_path)
    if output_path.parent and not output_path.parent.is_dir():
        raise FillError("output directory does not exist: %s" % output_path.parent)

    relocation_kept = values.get("RELOCATION_PACKAGE", "").strip().casefold() == "yes"
    changed_parts: List[str] = []
    replacement_count = 0
    temporary_name = ""

    try:
        with zipfile.ZipFile(template_path, "r") as source:
            if source.testzip() is not None:
                raise FillError("input template has a corrupt ZIP member")
            fd, temporary_name = tempfile.mkstemp(prefix=".offer-letter-", suffix=".docx", dir=str(output_path.parent))
            os.close(fd)
            with zipfile.ZipFile(temporary_name, "w") as destination:
                destination.comment = source.comment
                for info in source.infolist():
                    data = source.read(info.filename)
                    changed = False
                    if is_word_xml(info.filename):
                        try:
                            root = parse_xml(data)
                        except ET.ParseError as exc:
                            raise FillError("template XML part %s does not parse: %s" % (info.filename, exc)) from exc
                        nodes = word_text_nodes(root)
                        if nodes:
                            current = logical_text(nodes)
                            condition_changes = relocation_edits(current, relocation_kept)
                            changed = apply_edits(nodes, condition_changes) or changed
                            current = logical_text(nodes)
                            substitutions, number = substitute_edits(current, values)
                            changed = apply_edits(nodes, substitutions) or changed
                            replacement_count += number
                        if changed:
                            data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                            changed_parts.append(info.filename)
                    destination.writestr(info, data)
        validate_output(Path(temporary_name))
        os.replace(temporary_name, output_path)
        temporary_name = ""
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    return {
        "ok": True,
        "output_path": str(output_path),
        "changed_parts": changed_parts,
        "replacements": replacement_count,
        "relocation_kept": relocation_kept,
    }


def load_request(request: Dict[str, Any]) -> Tuple[Path, Path, Dict[str, str]]:
    template_value = request.get("template_path")
    output_value = request.get("output_path")
    if not isinstance(template_value, str) or not template_value:
        raise FillError("template_path must be a nonempty string")
    if not isinstance(output_value, str) or not output_value:
        raise FillError("output_path must be a nonempty string")

    if "values" in request:
        raw_values = request["values"]
    else:
        data_value = request.get("data_path")
        if not isinstance(data_value, str) or not data_value:
            raise FillError("provide data_path or values")
        try:
            with open(data_value, "r", encoding="utf-8") as handle:
                raw_values = json.load(handle)
        except OSError as exc:
            raise FillError("cannot read data_path: %s" % exc) from exc
        except json.JSONDecodeError as exc:
            raise FillError("data_path is not valid JSON: %s" % exc) from exc
    return Path(template_value), Path(output_value), normalize_values(raw_values)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise FillError("stdin JSON must be an object")
        template_path, output_path, values = load_request(request)
        result = fill(template_path, output_path, values)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (FillError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:  # Keep stdout machine-readable for unexpected failures.
        print(json.dumps({"ok": False, "error": "unexpected error: " + str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
