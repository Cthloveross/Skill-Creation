#!/usr/bin/env python3
"""Helpers for the setup-python-coverage-fuzzing skill.

Read exactly one JSON object from stdin and write one JSON object to stdout.

Actions:
 discover: {action, root, output?, expected_count?}. Finds top-level Python
   projects, optionally writes their absolute paths one per line, and returns
   {ok, libraries, count, errors}.
 analyze: {action, library, write_notes?}. Scans project Python files with AST,
   ranks parser-like public functions, and optionally writes notes_for_testing.txt.
 provision: {action, library, imports?}. Creates .venv, installs packaging tools,
   atheris and editable project, and verifies atheris plus requested imports.
 generate: {action, library, module, callable, argument}. Writes fuzz.py. argument
   is text, bytes, json, or text_and_bytes.
 validate: {action, libraries_file, expected_count?}. Checks required files and
   reports log markers; it does not replace review of target coverage.
"""
import ast
import json
import os
import re
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

IGNORE = {".git", ".hg", ".svn", ".venv", "venv", "env", "environment", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "build", "dist"}
PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile")
NAME_RE = re.compile(r"(?:parse|load|decode|deserialize|from_|format|compile|token|read|convert)", re.I)


def result(ok=True, **kw):
    return dict(ok=ok, **kw)


def project_dirs(root: Path):
    found = []
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name in IGNORE or p.name.startswith("."):
            continue
        if any((p / marker).exists() for marker in PROJECT_MARKERS):
            found.append(p.resolve())
    return found


def py_files(lib: Path):
    for p in lib.rglob("*.py"):
        if not any(part in IGNORE for part in p.relative_to(lib).parts):
            yield p


def discover(req):
    root = Path(req.get("root", "/app")).resolve()
    if not root.is_dir():
        return result(False, errors=[f"root is not a directory: {root}"], libraries=[])
    libs = project_dirs(root)
    errors = []
    expected = req.get("expected_count")
    if expected is not None and len(libs) != int(expected):
        errors.append(f"discovered {len(libs)} project directories, expected {expected}")
    output = req.get("output")
    if output:
        Path(output).write_text("".join(str(x) + "\n" for x in libs), encoding="utf-8")
    return result(not errors, libraries=[str(x) for x in libs], count=len(libs), errors=errors)


def candidates(lib: Path):
    out = []
    for file in py_files(lib):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"), filename=str(file))
        except (SyntaxError, OSError):
            continue
        module = ".".join(file.relative_to(lib).with_suffix("").parts)
        # A package __init__ has the package name, not package.__init__.
        if module.endswith(".__init__"):
            module = module[:-9]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                positional = len(node.args.posonlyargs) + len(node.args.args)
                # Methods normally need self and are less useful without setup.
                if positional and node.args.args and node.args.args[0].arg in {"self", "cls"}:
                    positional -= 1
                score = 0
                if NAME_RE.search(node.name): score += 5
                if positional in (1, 2): score += 2
                if "test" not in file.parts: score += 1
                if score:
                    out.append({"module_hint": module, "function": node.name,
                                "file": str(file.relative_to(lib)), "line": node.lineno,
                                "positional_parameters": positional, "score": score})
    return sorted(out, key=lambda x: (-x["score"], x["file"], x["line"]))[:30]


def analyze(req):
    lib = Path(req["library"]).resolve()
    if not lib.is_dir(): return result(False, errors=["library is not a directory"])
    items = candidates(lib)
    note = ["# Fuzzing target analysis", "", "Generated candidates require source review before use.",
            "Select a public importable callable, record its input contract and expected parse errors.", "",
            "## Candidate functions"]
    if items:
        for x in items:
            note.append(f"- `{x['module_hint']}.{x['function']}` — {x['file']}:{x['line']}; "
                        f"{x['positional_parameters']} positional parameter(s); ranking {x['score']}.")
    else:
        note.append("- No parser-like functions found statically; inspect public API and tests manually.")
    note += ["", "## Selected target (complete after inspection)",
             "- Import module: ", "- Callable: ", "- Input shape / valid examples: ",
             "- Expected malformed-input exceptions: ", "- Why this exercises meaningful parsing or branching: "]
    if req.get("write_notes"):
        (lib / "notes_for_testing.txt").write_text("\n".join(note) + "\n", encoding="utf-8")
    return result(True, library=str(lib), candidates=items, notes_written=bool(req.get("write_notes")))


def run(cmd, cwd, timeout=480):
    try:
        p = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return {"command": cmd, "returncode": p.returncode, "output_tail": p.stdout[-3000:]}
    except subprocess.TimeoutExpired as e:
        return {"command": cmd, "returncode": None, "output_tail": (e.stdout or "")[-3000:], "timeout": True}


def provision(req):
    lib = Path(req["library"]).resolve()
    if not lib.is_dir(): return result(False, errors=["library is not a directory"])
    vdir = lib / ".venv"
    if not (vdir / "bin" / "python").exists():
        venv.EnvBuilder(with_pip=True).create(str(vdir))
    python = vdir / "bin" / "python"
    steps = [run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], lib),
             run([str(python), "-m", "pip", "install", "atheris"], lib),
             run([str(python), "-m", "pip", "install", "-e", "."], lib)]
    imports = ["atheris"] + list(req.get("imports", []))
    check = "\n".join("import " + name for name in imports)
    steps.append(run([str(python), "-c", check], lib))
    ok = all(x.get("returncode") == 0 for x in steps)
    return result(ok, library=str(lib), python=str(python), imports=imports, steps=steps,
                  errors=[] if ok else ["one or more installation or import checks failed; inspect steps"])


def driver_source(module, callable_name, argument):
    calls = {
        "text": "TARGET(text)",
        "bytes": "TARGET(raw)",
        "json": "TARGET(json.loads(text))",
        "text_and_bytes": "TARGET(text)\n        TARGET(raw)",
    }
    if argument not in calls: raise ValueError("argument must be text, bytes, json, or text_and_bytes")
    body = calls[argument]
    return textwrap.dedent(f'''\
        # Generated by setup-python-coverage-fuzzing. Review against notes_for_testing.txt.
        import sys
        import json
        import atheris

        # Import instrumentation must be active before the target module is imported.
        with atheris.instrument_imports():
            import importlib
            _module = importlib.import_module({module!r})
        TARGET = getattr(_module, {callable_name!r})

        @atheris.instrument_func
        def TestOneInput(data: bytes) -> None:
            provider = atheris.FuzzedDataProvider(data)
            raw = provider.ConsumeBytes(4096)
            text = provider.ConsumeUnicodeNoSurrogates(4096)
            try:
                {body}
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                # Expected for malformed generated input; add documented library parse errors.
                return

        if __name__ == "__main__":
            atheris.Setup(sys.argv, TestOneInput)
            atheris.Fuzz()
        ''')


def generate(req):
    lib = Path(req["library"]).resolve()
    try:
        source = driver_source(req["module"], req["callable"], req.get("argument", "text"))
    except (KeyError, ValueError) as exc:
        return result(False, errors=[str(exc)])
    target = lib / "fuzz.py"
    target.write_text(source, encoding="utf-8")
    return result(True, fuzz_driver=str(target), module=req["module"], callable=req["callable"])


def validate(req):
    listed = Path(req.get("libraries_file", "/app/libraries.txt"))
    if not listed.is_file(): return result(False, errors=["libraries file is missing"], libraries=[])
    libs = [Path(x.strip()) for x in listed.read_text(encoding="utf-8").splitlines() if x.strip()]
    issues, reports = [], []
    expected = req.get("expected_count")
    if expected is not None and len(libs) != int(expected): issues.append(f"libraries file has {len(libs)} entries, expected {expected}")
    for lib in libs:
        missing = [name for name in ("notes_for_testing.txt", "fuzz.py", "fuzz.log") if not (lib / name).is_file()]
        if not (lib / ".venv" / "bin" / "python").is_file(): missing.append(".venv/bin/python")
        log = (lib / "fuzz.log")
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        coverage = any(marker in text for marker in ("INITED cov:", "NEW cov:", "pulse cov:"))
        crashed = any(marker in text.lower() for marker in ("deadlysignal", "fatal", "crash", "artifact_prefix"))
        normal = "Done " in text
        if missing: issues.append(f"{lib}: missing " + ", ".join(missing))
        if text and not (coverage or crashed): issues.append(f"{lib}: log lacks coverage markers and crash diagnostic")
        reports.append({"library": str(lib), "missing": missing, "coverage_marker": coverage,
                        "crash_diagnostic": crashed, "normal_completion": normal, "log_bytes": len(text)})
    return result(not issues, libraries=reports, errors=issues)


def main():
    try:
        req = json.load(sys.stdin)
        action = req.get("action")
        handlers = {"discover": discover, "analyze": analyze, "provision": provision,
                    "generate": generate, "validate": validate}
        out = handlers[action](req) if action in handlers else result(False, errors=["unknown action"])
    except Exception as exc:
        out = result(False, errors=[f"{type(exc).__name__}: {exc}"])
    print(json.dumps(out, sort_keys=True))

if __name__ == "__main__":
    main()
