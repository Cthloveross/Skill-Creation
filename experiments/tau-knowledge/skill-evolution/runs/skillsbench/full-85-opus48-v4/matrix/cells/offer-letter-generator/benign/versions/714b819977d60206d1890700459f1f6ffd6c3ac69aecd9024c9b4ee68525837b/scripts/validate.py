#!/usr/bin/env python3
"""Independent validation of a produced .docx.
Input (stdin JSON): {"path": "/root/offer_letter_filled.docx"}
Output (stdout JSON): {valid_zip, opens, unresolved_placeholders, leftover_markers, status}
"""
import sys, json, re, zipfile
import xml.etree.ElementTree as ET

IF_MARK = "{{IF_RELOCATION}}"
END_MARK = "{{END_IF_RELOCATION}}"


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}
    path = cfg.get("path", "/root/offer_letter_filled.docx")

    result = {"path": path, "valid_zip": False, "opens": False,
              "unresolved_placeholders": [], "leftover_markers": [], "status": "error"}
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            result["valid_zip"] = bad is None
            opens = True
            unresolved, markers = set(), set()
            for name in z.namelist():
                if not name.endswith(".xml"):
                    continue
                data = z.read(name)
                try:
                    ET.fromstring(data)
                except ET.ParseError:
                    opens = False
                txt = data.decode("utf-8", "ignore")
                for tok in re.findall(r"\{\{[^}]*\}\}", txt):
                    if tok in (IF_MARK, END_MARK):
                        markers.add(tok)
                    else:
                        unresolved.add(tok)
            result["opens"] = opens
            result["unresolved_placeholders"] = sorted(unresolved)
            result["leftover_markers"] = sorted(markers)
    except Exception as e:
        result["message"] = str(e)
        print(json.dumps(result))
        return

    result["status"] = ("ok" if result["valid_zip"] and result["opens"]
                        and not result["unresolved_placeholders"]
                        and not result["leftover_markers"] else "warning")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
