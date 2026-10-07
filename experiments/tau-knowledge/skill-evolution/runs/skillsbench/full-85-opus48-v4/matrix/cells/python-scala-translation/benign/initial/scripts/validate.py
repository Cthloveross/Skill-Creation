#!/usr/bin/env python3
"""Static validator for a translated Scala file.

stdin JSON: {
  "scala_path": str (required),
  "python_path": str (optional),
  "package": str (optional, e.g. "tokenizer"),
  "required": [str] (optional required identifier names)
}
stdout JSON report (see SKILL.md).
"""
import json
import os
import re
import sys


def parse_python_names(src):
    names = set()
    for m in re.finditer(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)', src, re.M):
        names.add(m.group(1))
    for m in re.finditer(r'^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)', src, re.M):
        names.add(m.group(1))
    return names


def snake_to_camel(name):
    parts = name.split('_')
    if len(parts) == 1:
        return name
    return parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:])


def scala_defines(scala, ident):
    # type-level or method/val definition of ident
    patterns = [
        r'\b(?:sealed\s+)?(?:abstract\s+)?(?:final\s+)?(?:case\s+)?(?:class|trait|object)\s+' + re.escape(ident) + r'\b',
        r'\bdef\s+' + re.escape(ident) + r'\b',
        r'\bval\s+' + re.escape(ident) + r'\b',
    ]
    return any(re.search(p, scala) for p in patterns)


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["bad stdin json: %s" % e]}))
        return

    scala_path = req.get("scala_path")
    errors, warnings = [], []
    report = {
        "ok": False, "errors": errors, "warnings": warnings,
        "missing_required": [], "python_names_absent": [],
        "var_count": 0, "val_count": 0,
        "uses_option": False, "uses_try_or_either": False, "uses_null": False,
    }

    if not scala_path or not os.path.isfile(scala_path):
        errors.append("scala file missing: %s" % scala_path)
        print(json.dumps(report))
        return

    with open(scala_path, "r", encoding="utf-8", errors="replace") as f:
        scala = f.read()

    pkg = req.get("package")
    if pkg:
        if not re.search(r'^\s*package\s+' + re.escape(pkg) + r'\b', scala, re.M):
            errors.append("missing or wrong package declaration (want 'package %s')" % pkg)

    required = req.get("required") or []
    for ident in required:
        if not scala_defines(scala, ident):
            report["missing_required"].append(ident)
    if report["missing_required"]:
        errors.append("required identifiers not defined: %s" % ', '.join(report["missing_required"]))

    py_path = req.get("python_path")
    if py_path and os.path.isfile(py_path):
        with open(py_path, "r", encoding="utf-8", errors="replace") as f:
            pysrc = f.read()
        for name in sorted(parse_python_names(pysrc)):
            if name.startswith("__"):
                continue
            if scala_defines(scala, name) or scala_defines(scala, snake_to_camel(name)):
                continue
            report["python_names_absent"].append(name)
        if report["python_names_absent"]:
            warnings.append("python names not obviously present in scala (check mapping): %s"
                            % ', '.join(report["python_names_absent"]))

    # strip strings/comments crudely for idiom metrics
    stripped = re.sub(r'//[^\n]*', '', scala)
    stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.S)
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', stripped)

    report["var_count"] = len(re.findall(r'\bvar\s+[A-Za-z_]', stripped))
    report["val_count"] = len(re.findall(r'\bval\s+[A-Za-z_]', stripped))
    report["uses_option"] = bool(re.search(r'\bOption\b|\bSome\(|\bNone\b', stripped))
    report["uses_try_or_either"] = bool(re.search(r'\bTry\b|\bEither\b|\bRight\(|\bLeft\(', stripped))
    report["uses_null"] = bool(re.search(r'\bnull\b', stripped))

    if report["uses_null"]:
        warnings.append("uses 'null' - prefer Option")
    if not report["uses_option"]:
        warnings.append("no Option usage detected - absence handling may be non-idiomatic")
    if report["var_count"] > report["val_count"]:
        warnings.append("var count (%d) exceeds val count (%d) - likely imperative port"
                        % (report["var_count"], report["val_count"]))
    if re.search(r'\breturn\b', stripped):
        warnings.append("'return' keyword present - prefer expression-oriented style")
    if re.search(r'\bthrow\b', stripped) and not report["uses_try_or_either"]:
        warnings.append("throws without Try/Either - prefer functional error handling")

    report["ok"] = len(errors) == 0
    print(json.dumps(report))


if __name__ == "__main__":
    main()
