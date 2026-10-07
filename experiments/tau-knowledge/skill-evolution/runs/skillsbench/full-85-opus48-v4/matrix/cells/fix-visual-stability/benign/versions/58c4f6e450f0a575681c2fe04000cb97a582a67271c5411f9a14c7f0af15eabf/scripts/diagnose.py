#!/usr/bin/env python3
"""Scan a Next.js App Router project for visual-stability anti-patterns.

Input (stdin JSON):
  {"app_root": "/app"}        # project root; defaults to "/app"

Output (stdout JSON):
  {
    "app_root": "/app",
    "issues": [
      {"id": "<fix-pattern-id>", "file": "<path>", "line": <int|null>,
       "reason": "<human-readable>"}
    ],
    "summary": {"<id>": <count>, ...},
    "notes": [ ... ]
  }

The report is a checklist. Each issue references a fix pattern documented in
references/fix-patterns.md. Heuristic/regex based: confirm against source.
"""
import json
import os
import re
import sys


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def find_files(root, exts):
    out = []
    for base, dirs, files in os.walk(root):
        if "node_modules" in dirs:
            dirs.remove("node_modules")
        if ".next" in dirs:
            dirs.remove(".next")
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            if any(fn.endswith(e) for e in exts):
                out.append(os.path.join(base, fn))
    return sorted(out)


def lineno(text, idx):
    return text.count("\n", 0, idx) + 1


def check_theme_flicker(root, issues, notes):
    # locate layout.tsx (App Router) under src/app or app
    layout = None
    for cand in ("src/app/layout.tsx", "app/layout.tsx",
                 "src/app/layout.jsx", "app/layout.jsx"):
        p = os.path.join(root, cand)
        if os.path.exists(p):
            layout = p
            break
    if layout is None:
        notes.append("layout.tsx not found under src/app or app")
        return
    txt = read(layout) or ""
    rel = os.path.relpath(layout, root)
    # A blocking inline script that reads localStorage before hydration.
    has_inline = ("dangerouslySetInnerHTML" in txt and
                  re.search(r"localStorage", txt) is not None and
                  re.search(r"<script\b", txt) is not None)
    if not has_inline:
        issues.append({
            "id": "theme-flicker", "file": rel, "line": None,
            "reason": ("No blocking inline <script dangerouslySetInnerHTML> "
                       "reading localStorage in layout head; theme is applied "
                       "after first paint -> flicker."),
        })

    # ThemeProvider using a post-hydration effect to apply theme.
    for cand in find_files(root, (".tsx", ".jsx")):
        base = os.path.basename(cand)
        if "theme" not in base.lower():
            continue
        t = read(cand) or ""
        if re.search(r"use(Effect|LayoutEffect|Isomorphic)", t) and \
           "localStorage" in t:
            issues.append({
                "id": "theme-flicker", "file": os.path.relpath(cand, root),
                "line": None,
                "reason": ("Theme read from localStorage inside an effect hook "
                           "(runs after first paint). Keep for runtime toggle "
                           "but apply initial theme via inline head script."),
            })


def check_images(root, issues):
    for p in find_files(root, (".tsx", ".jsx")):
        txt = read(p) or ""
        rel = os.path.relpath(p, root)
        for m in re.finditer(r"<img\b[^>]*?>", txt, re.DOTALL):
            tag = m.group(0)
            has_w = re.search(r"\bwidth\b", tag) is not None
            has_h = re.search(r"\bheight\b", tag) is not None
            has_ar = "aspect-ratio" in tag or "aspectRatio" in tag
            # style= with width/height counts as a dimension too
            style_wh = re.search(r"style=\{?[^}]*(width|height)", tag) is not None
            ok = (has_w and has_h) or (has_ar and (has_w or has_h or style_wh))
            if not ok:
                issues.append({
                    "id": "img-dimensions", "file": rel,
                    "line": lineno(txt, m.start()),
                    "reason": ("<img> without both width and height (or "
                               "aspect-ratio + one dimension); causes shift "
                               "when the image loads."),
                })


def check_font_display(root, issues):
    for p in find_files(root, (".css", ".scss")):
        txt = read(p) or ""
        rel = os.path.relpath(p, root)
        for m in re.finditer(r"@font-face\s*\{[^}]*\}", txt, re.DOTALL):
            block = m.group(0)
            if "font-display" not in block:
                issues.append({
                    "id": "font-display", "file": rel,
                    "line": lineno(txt, m.start()),
                    "reason": ("@font-face without font-display; defaults to "
                               "block (FOIT). Add font-display: swap;"),
                })
            elif not re.search(r"font-display\s*:\s*swap", block):
                issues.append({
                    "id": "font-display", "file": rel,
                    "line": lineno(txt, m.start()),
                    "reason": ("@font-face font-display is not 'swap'; swap "
                               "keeps text visible during load."),
                })


def check_null_loading(root, issues):
    # Components that render nothing while loading then insert content.
    for p in find_files(root, (".tsx", ".jsx")):
        txt = read(p) or ""
        rel = os.path.relpath(p, root)
        # heuristic: a conditional early-return of null / empty fragment that
        # is tied to a loading/visible/data gate.
        for m in re.finditer(
                r"if\s*\([^)]*\)\s*return\s*(null|<>\s*</>)\s*;?", txt):
            # look back a little for a loading-ish guard
            start = max(0, m.start() - 120)
            ctx = txt[start:m.end()]
            if re.search(r"(loading|visible|show|data|mounted|ready|loaded)",
                         ctx, re.IGNORECASE):
                issues.append({
                    "id": "reserve-space", "file": rel,
                    "line": lineno(txt, m.start()),
                    "reason": ("Component returns null/empty while loading, "
                               "then inserts content -> layout shift. Render a "
                               "same-sized placeholder instead."),
                })


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    root = payload.get("app_root") or "/app"
    root = os.path.abspath(root)

    issues = []
    notes = []
    if not os.path.isdir(root):
        print(json.dumps({"app_root": root, "issues": [],
                          "summary": {},
                          "notes": ["app_root is not a directory"]}))
        return

    check_theme_flicker(root, issues, notes)
    check_images(root, issues)
    check_font_display(root, issues)
    check_null_loading(root, issues)

    summary = {}
    for it in issues:
        summary[it["id"]] = summary.get(it["id"], 0) + 1

    print(json.dumps({
        "app_root": root,
        "issues": issues,
        "summary": summary,
        "notes": notes,
    }, indent=2))


if __name__ == "__main__":
    main()
