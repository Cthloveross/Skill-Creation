"""Shared helpers for the setup-fuzzing-py skill.

All functions are task-independent: they discover libraries, analyze packages,
and generate Atheris fuzz drivers at runtime. No instance-specific values are
hardcoded.
"""
import ast
import os
import re

ROOT_SKIP = {"environment", "skills", "__pycache__", ".git", ".venv", "venv"}
PKG_SKIP = {
    "tests", "test", "testing", "docs", "doc", "examples", "example",
    "benchmarks", "benchmark", "scripts", "__pycache__",
}
PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")

# verb -> priority score (substring match on the function name)
VERB_SCORES = [
    ("loads", 10), ("parse_string", 10), ("parse", 10), ("fromstring", 9),
    ("from_string", 9), ("deserialize", 9), ("decode", 9), ("load", 8),
    ("read", 7), ("tokenize", 7), ("lex", 7), ("format", 7), ("scan", 6),
    ("compile", 6), ("dumps", 6), ("dump", 5), ("render", 5), ("convert", 5),
    ("process", 4), ("validate", 4),
]


def normalize(name):
    return re.sub(r"[-.\s]+", "_", (name or "").strip().lower())


def has_project_marker(d):
    return any(os.path.exists(os.path.join(d, m)) for m in PROJECT_MARKERS)


def project_name(libdir):
    """Best-effort extraction of the distribution name from project files."""
    pp = os.path.join(libdir, "pyproject.toml")
    if os.path.exists(pp):
        try:
            txt = open(pp, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            txt = ""
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
        if m:
            return normalize(m.group(1))
    sc = os.path.join(libdir, "setup.cfg")
    if os.path.exists(sc):
        try:
            txt = open(sc, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            txt = ""
        m = re.search(r'(?m)^\s*name\s*=\s*([^\n]+)', txt)
        if m:
            return normalize(m.group(1))
    return None


def discover_libraries(root):
    """Return sorted absolute paths of library projects under *root*."""
    libs = []
    try:
        names = sorted(os.listdir(root))
    except Exception:
        return libs
    for name in names:
        if name.startswith(".") or name in ROOT_SKIP:
            continue
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        if has_project_marker(p) or find_package(p) is not None:
            libs.append(os.path.abspath(p))
    return libs


def find_package(libdir):
    """Locate the importable top-level package/module for a library.

    Returns dict {pkg, base, is_module} or None. *base* is the directory that
    should be on sys.path (the lib root or its src/ dir).
    """
    pname = project_name(libdir)
    bases = [libdir, os.path.join(libdir, "src")]
    best = None
    for base in bases:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.startswith(".") or name.startswith("_"):
                continue
            if name in PKG_SKIP:
                continue
            p = os.path.join(base, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "__init__.py")):
                cand = {"pkg": name, "base": base, "is_module": False}
                if pname and normalize(name) == pname:
                    return cand
                if best is None:
                    best = cand
    if best is not None:
        return best
    # single-module library fallback
    for base in bases:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.endswith(".py") and not name.startswith("_"):
                if name == "setup.py":
                    continue
                return {"pkg": name[:-3], "base": base, "is_module": True}
    return None


def _verb_score(fname):
    low = fname.lower()
    best = 0
    for verb, score in VERB_SCORES:
        if verb in low and score > best:
            best = score
    return best


def _required_args(funcdef):
    a = funcdef.args
    posonly = getattr(a, "posonlyargs", [])
    num_pos = len(posonly) + len(a.args)
    num_def = len(a.defaults)
    required = num_pos - num_def
    return required, (a.vararg is not None)


def _module_dotted(path, base):
    rel = os.path.relpath(path, base)
    rel = rel[:-3] if rel.endswith(".py") else rel
    parts = [p for p in rel.split(os.sep) if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def find_candidates(libdir, pkginfo, limit=5):
    """Return a ranked list of {module, func, score, required, kind}."""
    base = pkginfo["base"]
    if pkginfo["is_module"]:
        files = [os.path.join(base, pkginfo["pkg"] + ".py")]
    else:
        pkgdir = os.path.join(base, pkginfo["pkg"])
        files = []
        for dp, dns, fns in os.walk(pkgdir):
            dns[:] = [d for d in dns if d not in PKG_SKIP and not d.startswith(".")]
            for fn in fns:
                if fn.endswith(".py"):
                    files.append(os.path.join(dp, fn))
    func_cands = []
    class_cands = []
    for f in files:
        try:
            src = open(f, "r", encoding="utf-8", errors="ignore").read()
            tree = ast.parse(src)
        except Exception:
            continue
        module = _module_dotted(f, base)
        if not module:
            continue
        depth = module.count(".")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name.startswith("_"):
                    continue
                required, has_var = _required_args(node)
                callable_one = required == 1 or (required == 0 and has_var)
                if not callable_one:
                    continue
                score = _verb_score(name)
                func_cands.append({
                    "module": module, "func": name, "score": score,
                    "required": required, "kind": "function", "depth": depth,
                })
            elif isinstance(node, ast.ClassDef):
                name = node.name
                if name.startswith("_"):
                    continue
                init = None
                for b in node.body:
                    if isinstance(b, ast.FunctionDef) and b.name == "__init__":
                        init = b
                        break
                if init is None:
                    continue
                required, has_var = _required_args(init)
                required -= 1  # drop self
                if not (required == 1 or (required == 0 and has_var)):
                    continue
                class_cands.append({
                    "module": module, "func": name, "score": _verb_score(name),
                    "required": max(required, 0), "kind": "class", "depth": depth,
                })

    def rank(c):
        return (-c["score"], c["depth"], len(c["func"]))

    func_cands.sort(key=rank)
    # Prefer verb-matching functions; keep others as fallback.
    verb = [c for c in func_cands if c["score"] > 0]
    chosen = verb if verb else func_cands
    if not chosen:
        class_cands.sort(key=rank)
        chosen = class_cands
    # de-duplicate by (module, func)
    seen = set()
    out = []
    for c in chosen:
        key = (c["module"], c["func"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def write_notes(libdir, pkginfo, candidates):
    path = os.path.join(libdir, "notes_for_testing.txt")
    lines = []
    lines.append("# Fuzzing analysis notes")
    lines.append("library_dir: %s" % os.path.abspath(libdir))
    lines.append("import_package: %s" % pkginfo["pkg"])
    lines.append("source_base: %s" % pkginfo["base"])
    lines.append("")
    if candidates:
        lines.append("Selected functions under test (parser/loader/formatter")
        lines.append("entry points, single required argument, public API):")
        for c in candidates:
            lines.append(
                "  - %s.%s  [kind=%s score=%d required_args=%d]"
                % (c["module"], c["func"], c["kind"], c["score"], c["required"])
            )
        lines.append("")
        lines.append("Rationale: these accept str/bytes-like structured input")
        lines.append("(large input space, rich branching) and are fed by the")
        lines.append("Atheris FuzzedDataProvider in fuzz.py.")
    else:
        lines.append("No single-argument public parser-like function was found")
        lines.append("automatically. Inspect __init__.py manually and point")
        lines.append("fuzz.py at a str/bytes entry point.")
    content = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def generate_driver(libdir, pkginfo, candidates):
    """Write fuzz.py and return its path."""
    path = os.path.join(libdir, "fuzz.py")
    imports = []
    if candidates:
        for c in candidates:
            imports.append(
                "    try:\n"
                "        from %s import %s as _c\n"
                "        _TARGETS.append(_c)\n"
                "    except Exception:\n"
                "        pass\n" % (c["module"], c["func"])
            )
    else:
        # fall back to importing the package itself so the driver still
        # instruments target code; executor should refine the call.
        imports.append(
            "    try:\n"
            "        import %s as _pkg\n"
            "        _TARGETS.append(lambda s: getattr(_pkg, 'loads', getattr(_pkg, 'parse', str))(s))\n"
            "    except Exception:\n"
            "        pass\n" % pkginfo["pkg"]
        )
    import_block = "".join(imports)
    base = pkginfo["base"]
    content = '''#!/usr/bin/env python3
"""Atheris coverage-guided fuzz driver (auto-generated).

Targets public parser/loader entry points of the library. See
notes_for_testing.txt for the selected functions.
Run: python fuzz.py -max_total_time=10 2> fuzz.log
"""
import os
import sys

# Ensure the library source base is importable even without an install.
_BASE = %r
if _BASE and _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import atheris

_TARGETS = []
with atheris.instrument_imports():
%s

@atheris.instrument_func
def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    s = fdp.ConsumeUnicodeNoSurrogates(sys.maxsize)
    for fn in _TARGETS:
        try:
            fn(s)
        except (
            ValueError, TypeError, KeyError, IndexError, AttributeError,
            UnicodeError, OverflowError, RecursionError, ArithmeticError,
            LookupError, AssertionError, RuntimeError, NotImplementedError,
            StopIteration,
        ):
            pass


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
''' % (os.path.abspath(base), import_block)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
