#!/usr/bin/env python3
"""Scan a Next.js/React source tree for performance anti-patterns.

Input  (stdin JSON):  {"app_root": "/app"}
    app_root optional; defaults to current working directory.
Output (stdout JSON): {
    "app_root": str,
    "files_scanned": int,
    "findings": [ {"file": str, "category": str, "detail": str,
                   "suggestion": str} ],
    "dependencies": [str]   # from package.json, to spot heavy libs
}

Findings are heuristic leads. The executor must confirm each by reading the
code before editing. The script never modifies files.
"""
import json
import os
import re
import sys

TEXT_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs")


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def iter_source_files(root):
    src = os.path.join(root, "src")
    base = src if os.path.isdir(src) else root
    for dirpath, dirnames, filenames in os.walk(base):
        if "node_modules" in dirpath or "/.next" in dirpath:
            continue
        for name in filenames:
            if name.endswith(TEXT_EXT):
                yield os.path.join(dirpath, name)


def load_dependencies(root):
    pkg = read(os.path.join(root, "package.json"))
    deps = []
    try:
        data = json.loads(pkg)
        for key in ("dependencies", "devDependencies"):
            deps.extend(sorted((data.get(key) or {}).keys()))
    except Exception:
        pass
    return deps


# Independent-looking sequential awaits: separate `const x = await ...` lines.
AWAIT_ASSIGN = re.compile(r"(?:const|let|var)\s+\w+\s*=\s*await\s+", re.M)
# Non-critical awaited side effects.
SIDE_EFFECT = re.compile(
    r"await\s+[\w$.]*(analytics|telemetry|track|logEvent|logger|audit|metric|report)",
    re.I,
)
PROMISE_ALL = re.compile(r"Promise\.all\s*\(")
DYNAMIC = re.compile(r"\bdynamic\s*\(|React\.lazy\s*\(|\bimport\s*\(")
MEMO = re.compile(r"React\.memo|\bmemo\s*\(")
USECALLBACK = re.compile(r"useCallback\s*\(")
USEMEMO = re.compile(r"useMemo\s*\(")
HANDLER = re.compile(r"const\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
IMPORT_FROM = re.compile(r"import\s+(?:[^;]+?)\s+from\s+['\"]([^'\"]+)['\"]")


def is_route(path):
    return os.path.basename(path) in ("route.ts", "route.js")


def is_client(text):
    head = text.lstrip()[:40]
    return head.startswith('"use client"') or head.startswith("'use client'")


def is_async_server_page(path, text):
    name = os.path.basename(path)
    return name in ("page.tsx", "page.jsx", "page.ts", "page.js") and \
        not is_client(text) and re.search(r"export\s+default\s+async\s+function", text)


def analyze(path, text, deps):
    out = []
    rel = path
    n_await = len(AWAIT_ASSIGN.findall(text))
    has_all = bool(PROMISE_ALL.search(text))

    if (is_route(path) or is_async_server_page(path, text)):
        if n_await >= 2 and not has_all:
            out.append({
                "file": rel, "category": "fetch-waterfall",
                "detail": "%d sequential awaited assignments and no Promise.all" % n_await,
                "suggestion": "Start independent async calls together and await Promise.all([...]); keep genuine dependency chains sequential.",
            })
        if SIDE_EFFECT.search(text):
            out.append({
                "file": rel, "category": "awaited-side-effect",
                "detail": "analytics/telemetry/logging call appears to be awaited on the request path",
                "suggestion": "Fire-and-forget non-critical side effects: call without await and attach .catch(); keep awaiting anything the response depends on.",
            })

    if is_client(text):
        exports_component = re.search(r"export\s+default", text)
        uses_map = re.search(r"\.map\s*\(", text)
        passes_handler = re.search(r"on[A-Z]\w*\s*=\s*{", text) or HANDLER.search(text)
        if uses_map and passes_handler and not USECALLBACK.search(text):
            out.append({
                "file": rel, "category": "unstable-handler",
                "detail": "renders a list and defines/passes handlers without useCallback",
                "suggestion": "Wrap handlers in useCallback (functional state updaters allow empty deps) so memoized children are not re-rendered.",
            })
        # derived data recomputed each render
        if (re.search(r"\.filter\s*\(", text) or re.search(r"\.sort\s*\(", text)) \
                and not USEMEMO.search(text):
            out.append({
                "file": rel, "category": "unmemoized-derived-data",
                "detail": "filter/sort on render path without useMemo",
                "suggestion": "Wrap derived data and lookup maps in useMemo keyed on their inputs.",
            })
        if exports_component and not MEMO.search(text) and \
                re.search(r"(Card|Item|Row|Cell)\.tsx$", path):
            out.append({
                "file": rel, "category": "unmemoized-list-item",
                "detail": "list-item style component is not wrapped in React.memo",
                "suggestion": "Export the component wrapped in React.memo so stable props let it skip re-renders.",
            })

    # Heavy static imports in a page/tab that could be dynamic.
    for m in IMPORT_FROM.finditer(text):
        spec = m.group(1)
        if spec.startswith(".") or spec.startswith("/"):
            continue
        top = spec.split("/")[0]
        if top.startswith("@"):
            top = "/".join(spec.split("/")[:2])
        if top in deps and top not in ("react", "react-dom", "next"):
            is_barrel = "/" not in spec or (spec.startswith("@") and spec.count("/") == 1)
            if is_barrel and not DYNAMIC.search(text):
                out.append({
                    "file": rel, "category": "heavy-static-import",
                    "detail": "static barrel import of third-party package '%s'" % spec,
                    "suggestion": "If large and only used behind interaction, move its consumer to a separate module and load with next/dynamic. If only a few functions are used and the package publishes subpaths, use a verified direct subpath import.",
                })
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    root = payload.get("app_root") or os.getcwd()
    deps = load_dependencies(root)
    findings = []
    count = 0
    for path in iter_source_files(root):
        text = read(path)
        count += 1
        findings.extend(analyze(path, text, deps))
    json.dump({
        "app_root": root,
        "files_scanned": count,
        "findings": findings,
        "dependencies": deps,
    }, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
