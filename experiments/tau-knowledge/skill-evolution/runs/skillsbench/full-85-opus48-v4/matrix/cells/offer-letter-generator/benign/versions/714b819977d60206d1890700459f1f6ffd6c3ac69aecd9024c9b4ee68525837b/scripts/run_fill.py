#!/usr/bin/env python3
"""Fill a .docx offer-letter template from JSON data and resolve a relocation
conditional. Reads a JSON config on stdin, writes a JSON report on stdout.

Config: {"data_path"?, "template_path"?, "output_path"?}
All optional; defaults target the task's /root locations.
"""
import sys, os, json, re, zipfile
import xml.etree.ElementTree as ET

DEFAULT_DATA = "/root/employee_data.json"
DEFAULT_TEMPLATE = "/root/offer_letter_template.docx"
DEFAULT_OUTPUT = "/root/offer_letter_filled.docx"

IF_MARK = "{{IF_RELOCATION}}"
END_MARK = "{{END_IF_RELOCATION}}"

# Common WordprocessingML namespaces so re-serialized prefixes stay readable.
NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "ve": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}
for _p, _u in NAMESPACES.items():
    try:
        ET.register_namespace(_p, _u)
    except Exception:
        pass

W = NAMESPACES["w"]
W_T = "{%s}t" % W
W_P = "{%s}p" % W
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def build_parent_map(root):
    return {c: p for p in root.iter() for c in p}


def para_text(p):
    return "".join((t.text or "") for t in p.iter(W_T))


def set_para_text(p, new):
    """Redistribute `new` across the paragraph's existing w:t runs, preserving
    run count. All but the last run keep their original character length; the
    last run absorbs the remainder."""
    ts = list(p.iter(W_T))
    if not ts:
        return
    orig_lens = [len(t.text or "") for t in ts]
    rem = new
    for idx, t in enumerate(ts):
        t.set(XML_SPACE, "preserve")
        if idx == len(ts) - 1:
            t.text = rem
            rem = ""
        else:
            l = orig_lens[idx]
            t.text = rem[:l]
            rem = rem[l:]


def handle_conditional(root, keep):
    paras = list(root.iter(W_P))
    texts = [para_text(p) for p in paras]
    ii = [k for k, t in enumerate(texts) if IF_MARK in t]
    jj = [k for k, t in enumerate(texts) if END_MARK in t]
    if not ii and not jj:
        return
    i = ii[0] if ii else None
    j = jj[0] if jj else None

    # Both markers in the same paragraph -> inline edit.
    if i is not None and j is not None and i == j:
        combined = texts[i]
        s = combined.index(IF_MARK)
        e = combined.index(END_MARK) + len(END_MARK)
        if keep:
            new = combined.replace(IF_MARK, "").replace(END_MARK, "")
        else:
            new = combined[:s] + combined[e:]
        set_para_text(paras[i], new)
        return

    # Only one marker present -> just strip whatever markers we can find.
    if i is None or j is None:
        for k in sorted(set(ii + jj)):
            set_para_text(paras[k], texts[k].replace(IF_MARK, "").replace(END_MARK, ""))
        return

    if i > j:
        i, j = j, i

    if keep:
        set_para_text(paras[i], texts[i].replace(IF_MARK, ""))
        set_para_text(paras[j], texts[j].replace(END_MARK, ""))
        return

    # Remove block spanning paragraphs i..j.
    before = texts[i][: texts[i].index(IF_MARK)]
    after = texts[j][texts[j].index(END_MARK) + len(END_MARK):]
    pm = build_parent_map(root)
    for k in range(i + 1, j):
        child = paras[k]
        parent = pm.get(child)
        if parent is not None:
            parent.remove(child)
    set_para_text(paras[i], before)
    set_para_text(paras[j], after)
    if before.strip() == "":
        parent = pm.get(paras[i])
        if parent is not None:
            parent.remove(paras[i])
    if after.strip() == "":
        parent = pm.get(paras[j])
        if parent is not None:
            parent.remove(paras[j])


def apply_placeholders(root, data):
    for p in list(root.iter(W_P)):
        txt = para_text(p)
        if "{{" not in txt:
            continue
        new = txt
        for k, v in data.items():
            token = "{{" + str(k) + "}}"
            if token in new:
                new = new.replace(token, "" if v is None else str(v))
        if new != txt:
            set_para_text(p, new)


def preserve_root_ns(original_bytes, new_str):
    try:
        orig = original_bytes.decode("utf-8", "ignore")
    except Exception:
        return new_str
    m = re.search(r"<([\w:]+)([^>]*)>", orig)
    if not m:
        return new_str
    decls = re.findall(r'xmlns(?::\w+)?="[^"]*"', m.group(2))
    m2 = re.search(r"<([\w:]+)([^>]*?)>", new_str)
    if not m2:
        return new_str
    new_attrs = m2.group(2)
    additions = [d for d in decls if d not in new_attrs]
    if not additions:
        return new_str
    insert = " " + " ".join(additions)
    end = m2.start(2) + len(m2.group(2))
    return new_str[:end] + insert + new_str[end:]


def process_part(content, data, keep):
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    handle_conditional(root, keep)
    apply_placeholders(root, data)
    body = ET.tostring(root, encoding="unicode")
    body = preserve_root_ns(content, body)
    decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    return (decl + body).encode("utf-8")


def scan_leftovers(zip_path):
    unresolved = set()
    markers = set()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".xml"):
                continue
            try:
                txt = z.read(name).decode("utf-8", "ignore")
            except Exception:
                continue
            for tok in re.findall(r"\{\{[^}]*\}\}", txt):
                if tok in (IF_MARK, END_MARK):
                    markers.add(tok)
                else:
                    unresolved.add(tok)
            if "IF_RELOCATION" in txt:
                for m in re.findall(r"\{\{[^}]*IF_RELOCATION[^}]*\}\}", txt):
                    markers.add(m)
    return sorted(unresolved), sorted(markers)


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}
    data_path = cfg.get("data_path", DEFAULT_DATA)
    template_path = cfg.get("template_path", DEFAULT_TEMPLATE)
    output_path = cfg.get("output_path", DEFAULT_OUTPUT)

    for pth, label in ((data_path, "data"), (template_path, "template")):
        if not os.path.exists(pth):
            print(json.dumps({"status": "error", "message": "missing %s file: %s" % (label, pth)}))
            return

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(json.dumps({"status": "error", "message": "cannot parse data json: %s" % e}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "message": "data json must be an object"}))
        return

    reloc = str(data.get("RELOCATION_PACKAGE", "")).strip().lower()
    keep = reloc in ("yes", "y", "true", "1")

    edited = []
    try:
        with zipfile.ZipFile(template_path) as zin:
            infos = zin.infolist()
            raw_parts = {it.filename: zin.read(it.filename) for it in infos}
            new_parts = {}
            for it in infos:
                content = raw_parts[it.filename]
                if it.filename.endswith(".xml") and b"{{" in content:
                    np = process_part(content, data, keep)
                    if np is not None:
                        new_parts[it.filename] = np
                        edited.append(it.filename)
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for it in infos:
                    out = new_parts.get(it.filename, raw_parts[it.filename])
                    zout.writestr(it, out)
    except Exception as e:
        print(json.dumps({"status": "error", "message": "processing failed: %s" % e}))
        return

    unresolved, markers = scan_leftovers(output_path)
    status = "ok" if not unresolved and not markers else "warning"
    print(json.dumps({
        "status": status,
        "output_path": output_path,
        "relocation_kept": keep,
        "edited_parts": edited,
        "unresolved_placeholders": unresolved,
        "leftover_markers": markers,
        "message": "done" if status == "ok" else "leftover tokens/markers found",
    }))


if __name__ == "__main__":
    main()
