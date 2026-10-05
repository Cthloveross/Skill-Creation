#!/usr/bin/env python3
"""Create, install, and run Atheris fuzzing artifacts for Python projects.

JSON stdin schema:
{
  "root": "/app",                 # optional; defaults to /app
  "expected_libraries": 5,         # optional positive integer; defaults to 5
  "run_builder_if_needed": true    # optional; defaults to true
}

JSON stdout schema:
{
  "root": "/app",
  "libraries": [{"path": str, "target": {"module": str, "function": str},
                 "log": str, "valid_run": bool}],
  "failures": [str]
}

The script intentionally uses subprocess argument arrays rather than shell commands.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", "build", "dist", "node_modules",
}
PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")
PARSER_WORDS = (
    "parse", "load", "decode", "deserialize", "unmarshal", "from_",
    "format", "validate", "convert", "read",
)
INPUT_WORDS = ("data", "text", "string", "str", "input", "source", "raw", "value", "content", "json", "xml", "yaml", "code", "payload", "bytes")


def run_checked(args: list[str], cwd: Path, label: str) -> None:
    """Run a bounded command and raise an actionable error on failure."""
    completed = subprocess.run(
        args, cwd=str(cwd), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if completed.returncode:
        tail = completed.stdout[-4000:]
        raise RuntimeError("%s failed (exit %s):\n%s" % (label, completed.returncode, tail))


def is_project(path: Path) -> bool:
    return path.is_dir() and path.name not in EXCLUDED_DIRS and any((path / x).is_file() for x in PROJECT_MARKERS)


def discover_projects(root: Path) -> list[Path]:
    return sorted((p.resolve() for p in root.iterdir() if is_project(p)), key=lambda p: p.name.lower())


def maybe_build_dataset(root: Path, projects: list[Path], allowed: bool) -> list[Path]:
    """Use the supplied builder only as a fallback for an otherwise empty workspace."""
    builder = root / "build_dataset.sh"
    if projects or not allowed or not builder.is_file():
        return projects
    run_checked(["bash", str(builder)], root, "dataset builder")
    return discover_projects(root)


def source_roots(project: Path) -> list[Path]:
    src = project / "src"
    return [src] if src.is_dir() else [project]


def module_name(root: Path, source: Path) -> str | None:
    rel = source.relative_to(root)
    if any(part in EXCLUDED_DIRS or part in {"tests", "test", "docs", "examples"} for part in rel.parts):
        return None
    if source.name == "__init__.py":
        parts = rel.parent.parts
    else:
        parts = rel.with_suffix("").parts
    if not parts or any(not p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def annotation_text(node: ast.arg) -> str:
    if node.annotation is None:
        return ""
    try:
        return ast.unparse(node.annotation)
    except Exception:
        return ""


def signature_text(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        return "%s%s" % (node.name, ast.unparse(node.args))
    except Exception:
        return node.name + "(...)"


def required_argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    positional = list(node.args.posonlyargs) + list(node.args.args)
    required_count = len(positional) - len(node.args.defaults)
    names = [a.arg for a in positional[:required_count]]
    names.extend(a.arg for a, default in zip(node.args.kwonlyargs, node.args.kw_defaults) if default is None)
    return names


def candidate_score(node: ast.FunctionDef | ast.AsyncFunctionDef, module: str, is_init: bool) -> int:
    name = node.name.lower()
    if name.startswith("_") or name in {"main", "setup", "test"}:
        return -10000
    score = 0
    for index, word in enumerate(PARSER_WORDS):
        if word in name:
            score += 120 - index * 3
    args = required_argument_names(node)
    if args:
        score += 20
    if any(any(word in arg.lower() for word in INPUT_WORDS) for arg in args):
        score += 40
    if is_init:
        score += 15
    if module.count(".") <= 1:
        score += 5
    # A public callable with one likely input is still preferable to no driver.
    return score


def analyze_project(project: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for root in source_roots(project):
        for source in root.rglob("*.py"):
            mod = module_name(root, source)
            if not mod or source.name in {"setup.py", "conftest.py", "fuzz.py"}:
                continue
            try:
                tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            except (OSError, UnicodeError, SyntaxError):
                continue
            for item in tree.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                score = candidate_score(item, mod, source.name == "__init__.py")
                if score < 0:
                    continue
                candidates.append({
                    "module": mod,
                    "function": item.name,
                    "signature": signature_text(item),
                    "arguments": required_argument_names(item),
                    "score": score,
                    "source": str(source.relative_to(project)),
                    "rationale": "name/input heuristic score %d" % score,
                })
    candidates.sort(key=lambda c: (-int(c["score"]), str(c["module"]), str(c["function"])))
    return (candidates[0] if candidates else None), candidates[:12]


def write_notes(project: Path, selected: dict[str, Any] | None, alternatives: list[dict[str, Any]]) -> None:
    out = project / "notes_for_testing.txt"
    lines = ["Atheris fuzzing analysis", "=" * 24, ""]
    if selected is None:
        lines += [
            "No importable public Python function could be selected by static inspection.",
            "This project must be reviewed manually; no standard-library substitute is appropriate.",
        ]
    else:
        lines += [
            "Selected concrete target: %s.%s" % (selected["module"], selected["function"]),
            "Source: %s" % selected["source"],
            "Signature: %s" % selected["signature"],
            "Reason: %s. The generated driver feeds structured string/bytes-derived values",
            "through this actual library API and catches ordinary malformed-input exceptions.",
            "",
            "Other statically discovered callable candidates:",
        ]
        for item in alternatives:
            lines.append("- %s.%s — %s (%s)" % (item["module"], item["function"], item["signature"], item["source"]))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def driver_text(target: dict[str, Any]) -> str:
    module = json.dumps(target["module"])
    function = json.dumps(target["function"])
    # Generated values are deliberately local and deterministic for each raw input.
    return '''#!/usr/bin/env python3
"""Atheris driver generated from notes_for_testing.txt.
Target: %s.%s
"""
import asyncio
import importlib
import inspect
import sys

import atheris

# Importing inside this scope lets Atheris instrument Python code loaded by the target.
with atheris.instrument_imports():
    TARGET_MODULE = importlib.import_module(%s)
    TARGET_FUNCTION = getattr(TARGET_MODULE, %s)


def _value_for(parameter, provider, text, raw):
    """Make a small deterministic value appropriate for a common parser signature."""
    name = parameter.name.lower()
    annotation = str(parameter.annotation).lower()
    if "bytes" in annotation or name in {"bytes", "blob", "buffer", "raw"}:
        return raw
    if "bool" in annotation or name.startswith(("is_", "has_", "allow_", "strict")):
        return provider.ConsumeBool()
    if "float" in annotation:
        return float(provider.ConsumeIntInRange(-100000, 100000)) / 100.0
    if "int" in annotation or name in {"index", "count", "limit", "size", "version"}:
        return provider.ConsumeIntInRange(-100000, 100000)
    if "dict" in annotation or name in {"options", "config", "mapping", "headers"}:
        return {"input": text, "flag": provider.ConsumeBool()}
    if "list" in annotation or "tuple" in annotation or name in {"items", "values", "parts"}:
        return [text, provider.ConsumeUnicodeNoSurrogates(128)]
    return text


def _invoke(provider, raw):
    text = provider.ConsumeUnicodeNoSurrogates(4096)
    signature = inspect.signature(TARGET_FUNCTION)
    positional = []
    keywords = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.default is not inspect.Parameter.empty and not provider.ConsumeBool():
            continue
        value = _value_for(parameter, provider, text, raw)
        if parameter.kind is parameter.KEYWORD_ONLY:
            keywords[parameter.name] = value
        else:
            positional.append(value)
    result = TARGET_FUNCTION(*positional, **keywords)
    if inspect.isawaitable(result):
        asyncio.run(result)


@atheris.instrument_func
def TestOneInput(data):
    provider = atheris.FuzzedDataProvider(data)
    try:
        _invoke(provider, data)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        # Parser APIs commonly reject malformed fuzz data. Such rejections are not findings.
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
''' % (target["module"], target["function"], module, function)


def create_venv_and_install(project: Path, target: dict[str, Any]) -> Path:
    venv = project / ".venv"
    python = venv / "bin" / "python"
    if not python.is_file():
        run_checked([sys.executable, "-m", "venv", str(venv)], project, "virtualenv creation")
    run_checked([str(python), "-m", "pip", "install", "--upgrade", "pip"], project, "pip upgrade")
    # Requirement files are installed before the editable package so local project metadata
    # remains authoritative while legacy projects still receive their declared dependencies.
    for filename in ("requirements.txt", "requirements-dev.txt", "requirements_test.txt"):
        req = project / filename
        if req.is_file():
            run_checked([str(python), "-m", "pip", "install", "-r", str(req)], project, "install " + filename)
    run_checked([str(python), "-m", "pip", "install", "-e", "."], project, "editable project install")
    run_checked([str(python), "-m", "pip", "install", "atheris"], project, "Atheris install")
    probe = "import atheris, importlib; importlib.import_module(%r)" % target["module"]
    run_checked([str(python), "-c", probe], project, "Atheris/target import verification")
    return python


def run_fuzzer(project: Path, python: Path) -> tuple[Path, bool]:
    log = project / "fuzz.log"
    with log.open("wb") as handle:
        completed = subprocess.run(
            [str(python), "fuzz.py", "-max_total_time=10"], cwd=str(project),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=handle,
            timeout=45,
        )
    data = log.read_bytes() if log.exists() else b""
    lowered = data.lower()
    coverage = b"cov:" in lowered
    completed_normally = b"done " in lowered
    crash_finding = any(token in lowered for token in (
        b"deadly signal", b"fatal signal", b"test unit written", b"error: libfuzzer",
        b"crash-", b"leak-",
    ))
    valid = coverage and (completed_normally or crash_finding)
    if not valid:
        status = "return code %s, coverage=%s, completion=%s, crash=%s" % (completed.returncode, coverage, completed_normally, crash_finding)
        raise RuntimeError("fuzzer log did not demonstrate a coverage-guided completion or finding (%s)" % status)
    return log, valid


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        root = Path(request.get("root", "/app")).resolve()
        expected = request.get("expected_libraries", 5)
        if not isinstance(expected, int) or expected <= 0:
            raise ValueError("expected_libraries must be a positive integer")
        allow_builder = bool(request.get("run_builder_if_needed", True))
        if not root.is_dir():
            raise ValueError("root does not exist: %s" % root)
        projects = maybe_build_dataset(root, discover_projects(root), allow_builder)
        if len(projects) != expected:
            raise RuntimeError("expected exactly %d Python project directories, found %d: %s" % (expected, len(projects), ", ".join(str(p) for p in projects)))
        (root / "libraries.txt").write_text("".join(str(p) + "\n" for p in projects), encoding="utf-8")
        summary: dict[str, Any] = {"root": str(root), "libraries": [], "failures": []}
        for project in projects:
            selected, alternatives = analyze_project(project)
            write_notes(project, selected, alternatives)
            entry: dict[str, Any] = {"path": str(project), "target": None, "log": str(project / "fuzz.log"), "valid_run": False}
            summary["libraries"].append(entry)
            if selected is None:
                summary["failures"].append("%s: no analyzable public Python callable" % project)
                continue
            entry["target"] = {"module": selected["module"], "function": selected["function"]}
            try:
                (project / "fuzz.py").write_text(driver_text(selected), encoding="utf-8")
                os.chmod(project / "fuzz.py", 0o755)
                python = create_venv_and_install(project, selected)
                log, valid = run_fuzzer(project, python)
                entry["log"] = str(log)
                entry["valid_run"] = valid
            except Exception as exc:
                summary["failures"].append("%s: %s" % (project, exc))
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1 if summary["failures"] else 0
    except Exception as exc:
        print(json.dumps({"libraries": [], "failures": [str(exc)]}, indent=2), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
