"""Shared helpers for setup-fuzzing-py. Pure-Python, no third-party deps.

Discovers library projects, detects the importable package name, statically finds
parser-style entry points, and renders an Atheris fuzz driver. Nothing library-specific
is hardcoded; everything is derived from the directories present at runtime.
"""
import os
import re

# Directory names that are never a library under test.
EXCLUDE_DIRS = {
    "environment", "skills", "__pycache__", ".git", ".venv", "venv",
    "node_modules", ".idea", ".vscode", "build", "dist", ".tox",
}
PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")
PKG_SKIP = {"tests", "test", "testing", "docs", "doc", "examples", "example",
            "benchmarks", "scripts"}

# Parser-ish verbs, highest value first.
VERBS = [
    "loads", "load", "parse_string", "parsestring", "parse", "parses",
    "from_string", "fromstring", "read_string", "decode", "deserialize",
    "unmarshal", "read", "tokenize", "lex", "compile", "feed",
    "dumps", "dump", "render", "format",
]

DEF_RE = re.compile(r"^(def|class)\s+([A-Za-z_]\w*)\s*\(([^)]*)", re.MULTILINE)


def is_identifier(name):
    return name.isidentifier() and not name.startswith(".")


def looks_like_project(path):
    if not os.path.isdir(path):
        return False
    for m in PROJECT_MARKERS:
        if os.path.exists(os.path.join(path, m)):
            return True
    # or it directly contains an importable package
    for base in (path, os.path.join(path, "src")):
        if os.path.isdir(base):
            for name in os.listdir(base):
                sub = os.path.join(base, name)
                if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "__init__.py")):
                    return True
    return False


def discover_libraries(root):
    libs = []
    for name in sorted(os.listdir(root)):
        if name.startswith(".") or name in EXCLUDE_DIRS:
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path) and looks_like_project(path):
            libs.append(os.path.abspath(path))
    return libs


def detect_package(libdir):
    """Return (import_name, pkg_parent_dir, pkg_dir). pkg_dir may be a single module file."""
    for base in (os.path.join(libdir, "src"), libdir):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name in PKG_SKIP or not is_identifier(name):
                continue
            sub = os.path.join(base, name)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "__init__.py")):
                return name, base, sub
    # single-module project
    for name in sorted(os.listdir(libdir)):
        if name.endswith(".py") and name not in ("setup.py", "conf.py"):
            stem = name[:-3]
            if is_identifier(stem):
                return stem, libdir, os.path.join(libdir, name)
    # fallback: directory name itself
    base = os.path.basename(libdir.rstrip("/"))
    guess = base.replace("-", "_").replace(".", "_")
    return guess, libdir, os.path.join(libdir, guess)


def _module_dotted(import_name, pkg_parent, filepath):
    rel = os.path.relpath(filepath, pkg_parent)
    rel = rel[:-3] if rel.endswith(".py") else rel
    parts = [p for p in rel.split(os.sep) if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else import_name


def _verb_score(fname):
    low = fname.lower()
    for i, v in enumerate(VERBS):
        if low == v or low.startswith(v) or v in low:
            return i
    return len(VERBS) + 10


def find_candidates(import_name, pkg_parent, pkg_dir):
    """Return a ranked list of dicts: {module, func, kind, score, depth, from_init}."""
    files = []
    if os.path.isfile(pkg_dir):
        files = [pkg_dir]
    else:
        for dp, dns, fns in os.walk(pkg_dir):
            dns[:] = [d for d in dns if d not in PKG_SKIP and d != "__pycache__"]
            for fn in fns:
                if fn.endswith(".py"):
                    files.append(os.path.join(dp, fn))
    cands = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        module = _module_dotted(import_name, pkg_parent, fp)
        from_init = fp.endswith("__init__.py")
        depth = module.count(".")
        for kind, name, params in DEF_RE.findall(text):
            if name.startswith("_"):
                continue
            plist = [p.strip() for p in params.split(",") if p.strip()]
            # drop self/cls for the first param of a class/method
            effective = [p for p in plist if p not in ("self", "cls")]
            if not effective:
                continue  # needs at least one input argument
            score = _verb_score(name)
            cands.append({
                "module": module, "func": name, "kind": kind,
                "score": score, "depth": depth,
                "from_init": bool(from_init),
            })
    # rank: parser verbs first, then top-level __init__, then shallow, then name
    cands.sort(key=lambda c: (c["score"], 0 if c["from_init"] else 1,
                               c["depth"], c["func"]))
    # dedupe by (module, func)
    seen = set()
    uniq = []
    for c in cands:
        key = (c["module"], c["func"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def render_driver(pkg_parent, module, func):
    tmpl = '''import importlib
import os
import sys

import atheris

# Ensure the target library imports from source even if install was partial.
PKG_PARENT = {pkg_parent!r}
if PKG_PARENT and os.path.isdir(PKG_PARENT) and PKG_PARENT not in sys.path:
    sys.path.insert(0, PKG_PARENT)

MODULE = {module!r}
FUNC = {func!r}

# Instrument the target library as it is imported.
with atheris.instrument_imports():
    _mod = importlib.import_module(MODULE)

_target = getattr(_mod, FUNC)


@atheris.instrument_func
def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    s = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    try:
        _target(s)
    except TypeError:
        # Some targets want bytes rather than str.
        try:
            _target(s.encode("utf-8", "surrogatepass"))
        except Exception:
            pass
    except Exception:
        # Expected library errors on malformed input are not fuzzing failures.
        pass


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
'''
    return tmpl.format(pkg_parent=pkg_parent, module=module, func=func)


def render_notes(libdir, import_name, pkg_parent, candidates, chosen):
    lines = []
    lines.append("# Notes for fuzz testing: %s" % os.path.basename(libdir.rstrip("/")))
    lines.append("")
    lines.append("Library directory : %s" % libdir)
    lines.append("Import name       : %s" % import_name)
    lines.append("Package parent dir: %s" % pkg_parent)
    lines.append("")
    if chosen:
        lines.append("Chosen fuzz target: %s.%s" % (chosen["module"], chosen["func"]))
        lines.append("  (feed it fuzz-generated str/bytes via FuzzedDataProvider)")
    else:
        lines.append("Chosen fuzz target: NONE FOUND (inspect the API manually)")
    lines.append("")
    lines.append("Candidate entry points (parser/loader/formatter first):")
    if candidates:
        for c in candidates[:15]:
            tag = "[init]" if c["from_init"] else ""
            lines.append("  - %s.%s  (%s) %s" % (c["module"], c["func"], c["kind"], tag))
    else:
        lines.append("  (none discovered by static scan)")
    lines.append("")
    lines.append("Rationale: parsers/deserializers accept complex structured input and")
    lines.append("have large input spaces with many error paths -- high value for fuzzing.")
    lines.append("")
    return "\n".join(lines) + "\n"
