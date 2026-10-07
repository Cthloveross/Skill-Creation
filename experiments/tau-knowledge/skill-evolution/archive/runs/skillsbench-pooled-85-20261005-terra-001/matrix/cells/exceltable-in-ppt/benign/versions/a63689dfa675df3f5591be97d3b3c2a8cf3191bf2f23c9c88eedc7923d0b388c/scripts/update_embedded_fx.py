#!/usr/bin/env python3
"""Discover and update a labeled rate in an XLSX embedded in a PPTX.

stdin JSON: {"input_pptx": str, "output_pptx": str,
             "max_text_candidates": optional positive int}
stdout JSON: success/failure audit.  Requires only Python 3 standard library.
"""
import copy
import io
import json
import math
import os
import posixpath
import re
import sys
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
R_ID = "{%s}id" % NS["r"]
REL_TARGET = "Target"
REL_MODE = "TargetMode"
NUM_RE = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?"


def local(tag):
    return tag.rsplit("}", 1)[-1]


def q(ns, tag):
    return "{%s}%s" % (NS[ns], tag)


def parse_xml(data, name):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Invalid XML in %s: %s" % (name, exc))


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def resolve_target(source_part, target):
    if not target or target.startswith("/"):
        target = target.lstrip("/")
        return posixpath.normpath(target)
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def source_from_rels_part(rels_part):
    # e.g. ppt/slides/_rels/slide1.xml.rels -> ppt/slides/slide1.xml
    d, f = posixpath.split(rels_part)
    if d == "_rels" and f == ".rels":
        return ""
    marker = "/_rels/"
    if marker not in rels_part or not f.endswith(".rels"):
        return None
    before, after = rels_part.split(marker, 1)
    return before + "/" + after[:-5]


def relationship_map(zip_file, rels_part, source_part):
    root = parse_xml(zip_file.read(rels_part), rels_part)
    result = {}
    for rel in root:
        if local(rel.tag) != "Relationship" or rel.get(REL_MODE) == "External":
            continue
        rid = rel.get("Id")
        target = rel.get(REL_TARGET)
        if rid and target:
            result[rid] = resolve_target(source_part, target)
    return result


def all_relationship_targets_exist(zip_file):
    names = set(zip_file.namelist())
    missing = []
    for name in names:
        if not name.endswith(".rels") or "/_rels/" not in name and name != "_rels/.rels":
            continue
        source = source_from_rels_part(name)
        if source is None:
            continue
        root = parse_xml(zip_file.read(name), name)
        for rel in root:
            if local(rel.tag) != "Relationship" or rel.get(REL_MODE) == "External":
                continue
            target = rel.get(REL_TARGET)
            if target and resolve_target(source, target) not in names:
                missing.append({"rels": name, "target": target})
    return missing


def extract_geometry(shape):
    # The transform may be p:xfrm or a:xfrm. Pick the first one owned by shape.
    xfrm = next((e for e in shape.iter() if local(e.tag) == "xfrm"), None)
    if xfrm is None:
        return (0, 0, 0, 0)
    off = next((e for e in xfrm if local(e.tag) == "off"), None)
    ext = next((e for e in xfrm if local(e.tag) == "ext"), None)
    try:
        return (int(off.get("x", "0")), int(off.get("y", "0")),
                int(ext.get("cx", "0")), int(ext.get("cy", "0")))
    except (AttributeError, ValueError):
        return (0, 0, 0, 0)


def rect_gap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(ax - (bx + bw), bx - (ax + aw), 0)
    dy = max(ay - (by + bh), by - (ay + ah), 0)
    if dx == 0 and dy == 0:
        return 0.0
    return math.hypot(dx, dy)


def text_from_shape(shape):
    return "".join((node.text or "") for node in shape.iter(q("a", "t"))).strip()


def parse_decimal(text):
    normalized = text.replace(",", "")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def parse_rate_instruction(text):
    """Return (source, destination, Decimal) only for explicit rate phrasing."""
    cleaned = " ".join(text.replace("–", "-").replace("—", "-").split())
    # A conventional quote explicitly establishes the denominator/destination.
    patterns = [
        re.compile(r"\b1\s+(?P<src>[A-Za-z]{3})\s*(?:=|equals|is)\s*"
                   r"(?P<rate>" + NUM_RE + r")\s+(?P<dst>[A-Za-z]{3})\b", re.I),
        re.compile(r"\b(?:from\s+)?(?P<src>[A-Za-z]{3})\s*"
                   r"(?:/|->|→|\bto\b)\s*(?P<dst>[A-Za-z]{3})\b"
                   r"(?:\s+(?:exchange\s+)?rate)?\s*(?:=|:|\bis\b|\bat\b)?\s*"
                   r"(?P<rate>" + NUM_RE + r")\b", re.I),
    ]
    matches = []
    for pattern in patterns:
        for m in pattern.finditer(cleaned):
            rate = parse_decimal(m.group("rate"))
            if rate is not None:
                matches.append((m.group("src").upper(), m.group("dst").upper(), rate))
    unique = {(s, d, str(v)): (s, d, v) for s, d, v in matches}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def slide_embeds_and_text(zip_file):
    """Yield workbook-linked object geometries and text shapes by slide."""
    names = set(zip_file.namelist())
    slides = sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
    for slide in slides:
        rels = posixpath.dirname(slide) + "/_rels/" + posixpath.basename(slide) + ".rels"
        if rels not in names:
            continue
        relmap = relationship_map(zip_file, rels, slide)
        root = parse_xml(zip_file.read(slide), slide)
        embeds, texts = [], []
        # Direct children of spTree correspond to visible top-level shapes.
        sp_tree = root.find(".//p:spTree", NS)
        if sp_tree is None:
            continue
        for shape in list(sp_tree):
            geom = extract_geometry(shape)
            text = text_from_shape(shape)
            if text:
                texts.append({"text": text, "geometry": geom})
            ids = {node.get(R_ID) for node in shape.iter() if node.get(R_ID)}
            for rid in ids:
                target = relmap.get(rid)
                if target and target in names:
                    # Verify it is an OOXML spreadsheet rather than assuming extension.
                    try:
                        with zipfile.ZipFile(io.BytesIO(zip_file.read(target))) as z:
                            is_xlsx = "xl/workbook.xml" in z.namelist()
                    except zipfile.BadZipFile:
                        is_xlsx = False
                    if is_xlsx:
                        embeds.append({"part": target, "geometry": geom})
        yield slide, embeds, texts


def discover_single_update(ppt_bytes, max_candidates):
    with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as ppt:
        found = []
        workbook_parts = set()
        for slide, embeds, texts in slide_embeds_and_text(ppt):
            workbook_parts.update(e["part"] for e in embeds)
            for embed in embeds:
                ordered = sorted(texts, key=lambda t: rect_gap(embed["geometry"], t["geometry"]))
                parsed = []
                for candidate in ordered[:max_candidates]:
                    item = parse_rate_instruction(candidate["text"])
                    if item:
                        parsed.append((candidate, item))
                # More than one different explicit nearby instruction is unsafe.
                distinct = {(x[1][0], x[1][1], str(x[1][2])) for x in parsed}
                if len(distinct) > 1:
                    raise ValueError("Multiple conflicting explicit rate instructions near embedded workbook on %s" % slide)
                if parsed:
                    candidate, (src, dst, rate) = parsed[0]
                    found.append({"part": embed["part"], "slide": slide,
                                  "text": candidate["text"], "source": src,
                                  "destination": dst, "rate": rate})
        if not found:
            raise ValueError("No embedded OOXML workbook with a nearby explicit exchange-rate text instruction was found")
        distinct = {(f["part"], f["source"], f["destination"], str(f["rate"])) for f in found}
        if len(distinct) != 1:
            raise ValueError("Rate instruction does not uniquely identify one embedded workbook and one update")
        return found[0]


def col_to_num(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref):
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref or "", re.I)
    if not m:
        return None
    return int(m.group(2)), col_to_num(m.group(1).upper())


def read_shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = parse_xml(z.read("xl/sharedStrings.xml"), "xl/sharedStrings.xml")
    values = []
    for si in root.findall("x:si", NS):
        values.append("".join((t.text or "") for t in si.iter(q("x", "t"))))
    return values


def cell_display_value(cell, shared):
    typ = cell.get("t")
    if typ == "inlineStr":
        return "".join((t.text or "") for t in cell.iter(q("x", "t")))
    v = cell.find("x:v", NS)
    if v is None or v.text is None:
        return None
    if typ == "s":
        try:
            return shared[int(v.text)]
        except (ValueError, IndexError):
            return None
    return v.text


def sheet_catalog(z):
    root = parse_xml(z.read("xl/workbook.xml"), "xl/workbook.xml")
    rels = relationship_map(z, "xl/_rels/workbook.xml.rels", "xl/workbook.xml")
    result = []
    sheets = root.find("x:sheets", NS)
    if sheets is None:
        raise ValueError("Embedded workbook has no worksheets")
    for sheet in sheets.findall("x:sheet", NS):
        target = rels.get(sheet.get(R_ID))
        if target and target in z.namelist():
            result.append((sheet.get("name", target), target))
    return result


def currency_mentions(value, code):
    return bool(value is not None and re.search(r"(?<![A-Za-z])" + re.escape(code) + r"(?![A-Za-z])", str(value), re.I))


def find_target_cell(xlsx_bytes, source, destination):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        shared = read_shared_strings(z)
        choices = []
        for sheet_name, sheet_part in sheet_catalog(z):
            root = parse_xml(z.read(sheet_part), sheet_part)
            cells = {}
            for cell in root.findall(".//x:c", NS):
                coord = split_ref(cell.get("r"))
                if coord:
                    cells[coord] = cell
            source_labels = []
            destination_labels = []
            for (row, col), cell in cells.items():
                value = cell_display_value(cell, shared)
                if currency_mentions(value, source):
                    source_labels.append((row, col))
                if currency_mentions(value, destination):
                    destination_labels.append((row, col))
            for row, row_label_col in source_labels:
                for header_row, col in destination_labels:
                    if row_label_col >= col or header_row >= row:
                        continue
                    target = cells.get((row, col))
                    if target is None:
                        continue
                    # Favor the closest plausible row and column labels.
                    score = (col - row_label_col) + (row - header_row)
                    choices.append((score, sheet_name, sheet_part, root, target, (row, col)))
        if not choices:
            raise ValueError("Could not locate a populated matrix cell using row label %s and column label %s" % (source, destination))
        choices.sort(key=lambda x: x[0])
        best_score = choices[0][0]
        best = [c for c in choices if c[0] == best_score]
        identities = {(c[2], c[4].get("r")) for c in best}
        if len(identities) != 1:
            raise ValueError("Currency labels map ambiguously to multiple equally plausible target cells")
        _, name, part, root, target, _ = best[0]
        if target.find("x:f", NS) is not None:
            raise ValueError("Refusing to overwrite formula cell %s!%s" % (name, target.get("r")))
        return name, part, root, target.get("r")


def formula_map(xlsx_bytes):
    result = {}
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        for name in z.namelist():
            if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                continue
            root = parse_xml(z.read(name), name)
            for cell in root.findall(".//x:c", NS):
                formula = cell.find("x:f", NS)
                if formula is not None:
                    result[(name, cell.get("r"))] = (formula.get("t"), formula.text or "")
    return result


def update_xlsx(xlsx_bytes, sheet_part, cell_ref, rate):
    before_formulas = formula_map(xlsx_bytes)
    source = io.BytesIO(xlsx_bytes)
    output = io.BytesIO()
    with zipfile.ZipFile(source, "r") as zin:
        root = parse_xml(zin.read(sheet_part), sheet_part)
        cell = next((c for c in root.findall(".//x:c", NS) if c.get("r") == cell_ref), None)
        if cell is None:
            raise ValueError("Target cell disappeared while preparing update")
        if cell.find("x:f", NS) is not None:
            raise ValueError("Target cell is a formula and cannot be replaced")
        # Numeric cells must not retain a shared-string or inline-string type.
        cell.attrib.pop("t", None)
        for inline in list(cell.findall("x:is", NS)):
            cell.remove(inline)
        value = cell.find("x:v", NS)
        if value is None:
            value = ET.SubElement(cell, q("x", "v"))
        # Decimal's fixed-point representation avoids unintended binary rounding.
        value.text = format(rate, "f")
        changed_sheet = xml_bytes(root)
        with zipfile.ZipFile(output, "w") as zout:
            zout.comment = zin.comment
            for info in zin.infolist():
                data = changed_sheet if info.filename == sheet_part else zin.read(info.filename)
                zout.writestr(copy.copy(info), data)
    updated = output.getvalue()
    if formula_map(updated) != before_formulas:
        raise ValueError("Formula text changed during embedded workbook update")
    return updated


def stored_cell_decimal(xlsx_bytes, sheet_part, cell_ref):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        root = parse_xml(z.read(sheet_part), sheet_part)
        cell = next((c for c in root.findall(".//x:c", NS) if c.get("r") == cell_ref), None)
        if cell is None or cell.find("x:f", NS) is not None:
            return None
        value = cell.find("x:v", NS)
        return parse_decimal(value.text if value is not None else "")


def replace_ppt_embedded(ppt_bytes, part, new_xlsx):
    source, output = io.BytesIO(ppt_bytes), io.BytesIO()
    with zipfile.ZipFile(source, "r") as zin:
        if part not in zin.namelist():
            raise ValueError("Discovered embedded workbook part is absent from presentation")
        with zipfile.ZipFile(output, "w") as zout:
            zout.comment = zin.comment
            for info in zin.infolist():
                data = new_xlsx if info.filename == part else zin.read(info.filename)
                zout.writestr(copy.copy(info), data)
    return output.getvalue()


def validate(before_ppt, after_ppt, workbook_part, sheet_part, cell_ref, rate):
    with zipfile.ZipFile(io.BytesIO(after_ppt)) as after, zipfile.ZipFile(io.BytesIO(before_ppt)) as before:
        bad = after.testzip()
        if bad:
            raise ValueError("Output PPTX ZIP CRC validation failed at %s" % bad)
        missing = all_relationship_targets_exist(after)
        if missing:
            raise ValueError("Output PPTX has broken internal relationship targets: %s" % missing[:3])
        before_names, after_names = set(before.namelist()), set(after.namelist())
        if before_names != after_names:
            raise ValueError("Presentation part list changed unexpectedly")
        changed_parts = [n for n in sorted(before_names) if before.read(n) != after.read(n)]
        if changed_parts != [workbook_part]:
            raise ValueError("Unexpected presentation parts changed: %s" % changed_parts)
        embedded = after.read(workbook_part)
        with zipfile.ZipFile(io.BytesIO(embedded)) as wb:
            if wb.testzip():
                raise ValueError("Updated embedded workbook ZIP is corrupt")
        stored = stored_cell_decimal(embedded, sheet_part, cell_ref)
        if stored != rate:
            raise ValueError("Updated embedded cell value does not equal requested rate")
    return {"zip_crc": True, "relationships": True, "unchanged_nonembedded_parts": True,
            "formula_text_preserved": True, "updated_value_verified": True}


def run(payload):
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    input_path = payload.get("input_pptx")
    output_path = payload.get("output_pptx")
    if not isinstance(input_path, str) or not isinstance(output_path, str):
        raise ValueError("input_pptx and output_pptx must be strings")
    if os.path.abspath(input_path) == os.path.abspath(output_path):
        raise ValueError("output_pptx must differ from input_pptx")
    max_candidates = payload.get("max_text_candidates", 12)
    if not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("max_text_candidates must be a positive integer")
    ppt_bytes = Path(input_path).read_bytes()
    # Confirm this before discovery so failures identify bad input clearly.
    try:
        with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as z:
            if "[Content_Types].xml" not in z.namelist():
                raise ValueError("Input is not an OOXML PowerPoint package")
    except zipfile.BadZipFile as exc:
        raise ValueError("Input PPTX is not a valid ZIP package: %s" % exc)
    update = discover_single_update(ppt_bytes, max_candidates)
    with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as ppt:
        xlsx = ppt.read(update["part"])
    sheet_name, sheet_part, _, cell_ref = find_target_cell(xlsx, update["source"], update["destination"])
    updated_xlsx = update_xlsx(xlsx, sheet_part, cell_ref, update["rate"])
    result_ppt = replace_ppt_embedded(ppt_bytes, update["part"], updated_xlsx)
    validation = validate(ppt_bytes, result_ppt, update["part"], sheet_part, cell_ref, update["rate"])
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".embedded-rate-", suffix=".pptx", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(result_ppt)
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"ok": True, "output_pptx": str(destination),
            "embedded_workbook_part": update["part"], "slide": update["slide"],
            "instruction_text": update["text"], "source_currency": update["source"],
            "destination_currency": update["destination"], "rate": format(update["rate"], "f"),
            "worksheet": sheet_name, "cell": cell_ref, "validation": validation}


def main():
    try:
        payload = json.load(sys.stdin)
        answer = run(payload)
        print(json.dumps(answer, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
