#!/usr/bin/env python3
"""Check basic delivery structure without pretending to compile Scala.
Input JSON: {"source": path, "package": name, "required": [symbol, ...]}
Output JSON: {"ok", "missing", "package_found", "delimiter_errors"}.
"""
import json
import re
import sys
from pathlib import Path


def strip_comments_and_strings(text):
    # Conservative scanner: removes quoted text/comments so braces in literals do not count.
    out = []
    i, state = 0, "code"
    while i < len(text):
        if state == "code" and text.startswith("//", i):
            state = "line"; out.extend("  "); i += 2
        elif state == "code" and text.startswith("/*", i):
            state = "block"; out.extend("  "); i += 2
        elif state == "line":
            out.append("\n" if text[i] == "\n" else " ")
            if text[i] == "\n": state = "code"
            i += 1
        elif state == "block" and text.startswith("*/", i):
            state = "code"; out.extend("  "); i += 2
        elif state == "block":
            out.append("\n" if text[i] == "\n" else " "); i += 1
        elif state == "code" and text[i] == '"':
            state = "string"; out.append(" "); i += 1
        elif state == "string":
            if text[i] == "\\" and i + 1 < len(text): out.extend("  "); i += 2
            elif text[i] == '"': state = "code"; out.append(" "); i += 1
            else: out.append("\n" if text[i] == "\n" else " "); i += 1
        else:
            out.append(text[i]); i += 1
    return "".join(out)


def main():
    try:
        request = json.load(sys.stdin)
        text = Path(request["source"]).read_text(encoding="utf-8")
        package = request["package"]
        required = request.get("required", [])
        package_found = bool(re.search(r"(?m)^\s*package\s+" + re.escape(package) + r"\s*$", text))
        missing = []
        for symbol in required:
            # Covers types/objects and defs; semantic compilation remains mandatory.
            pattern = r"\b(?:class|trait|object|case\s+class|case\s+object|def)\s+" + re.escape(symbol) + r"\b"
            if not re.search(pattern, text): missing.append(symbol)
        cleaned = strip_comments_and_strings(text)
        stack, errors = [], []
        pairs = {")": "(", "]": "[", "}": "{"}
        for pos, char in enumerate(cleaned):
            if char in "([{": stack.append((char, pos))
            elif char in pairs:
                if not stack or stack[-1][0] != pairs[char]: errors.append("unmatched %s at %d" % (char, pos))
                else: stack.pop()
        errors.extend("unclosed %s at %d" % item for item in stack)
        result = {"ok": package_found and not missing and not errors,
                  "package_found": package_found, "missing": missing,
                  "delimiter_errors": errors}
        print(json.dumps(result, indent=2))
        if not result["ok"]: sys.exit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
