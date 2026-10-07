#!/usr/bin/env python3
"""End-to-end: discover libraries, write libraries.txt, and for each library write
notes_for_testing.txt + fuzz.py, build .venv (deps + atheris), and run a short fuzz
capturing stderr into fuzz.log.

stdin : {"root": "/app", "duration": 10}
stdout: {"libraries":[...], "libraries_txt": path, "results":[per-lib summary]}

Runs real subprocesses. Each library is independent; one failing library does not stop
the others. Inspect per-lib "errors" and fuzz.log for environment limitations.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzz_helpers as H
import build_driver


def _run(cmd, cwd=None, timeout=600, stderr_path=None):
    try:
        if stderr_path:
            with open(stderr_path, "wb") as log:
                p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=log, timeout=timeout)
            return p.returncode, ""
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace")[-4000:]
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, "exception: %s" % e


def _find_requirements(libdir):
    found = []
    for name in os.listdir(libdir):
        low = name.lower()
        if low.startswith("requirements") and low.endswith(".txt"):
            found.append(os.path.join(libdir, name))
    return sorted(found)


def process_lib(libdir, duration):
    res = {"lib": libdir, "errors": [], "install_ok": False,
           "import_ok": False, "fuzz_ran": False, "log_markers": []}
    info = build_driver.build_one(libdir)
    res.update({"import_name": info["import_name"], "module": info["module"],
                "func": info["func"]})
    if info["func"] is None:
        res["errors"].append("no fuzz target discovered")
        return res

    venv = os.path.join(libdir, ".venv")
    py = os.path.join(venv, "bin", "python")
    pip = os.path.join(venv, "bin", "pip")

    if not os.path.exists(py):
        rc, out = _run([sys.executable, "-m", "venv", venv], timeout=180)
        if rc != 0:
            res["errors"].append("venv create failed: " + out[-500:])
            return res
    _run([pip, "install", "--upgrade", "pip"], timeout=180)

    has_proj = any(os.path.exists(os.path.join(libdir, m)) for m in H.PROJECT_MARKERS)
    reqs = _find_requirements(libdir)
    install_rc = 1
    if has_proj:
        install_rc, out = _run([pip, "install", "."], cwd=libdir, timeout=500)
        if install_rc != 0:
            res["errors"].append("pip install . failed: " + out[-500:])
    if install_rc != 0 and reqs:
        for r in reqs:
            rc, out = _run([pip, "install", "-r", r], cwd=libdir, timeout=500)
            if rc == 0:
                install_rc = 0
            else:
                res["errors"].append("pip install -r %s failed: %s" % (r, out[-300:]))
    res["install_ok"] = install_rc == 0

    rc, out = _run([pip, "install", "atheris"], timeout=500)
    if rc != 0:
        res["errors"].append("atheris install failed: " + out[-500:])
        return res

    rc, out = _run([py, "-c", "import atheris, %s" % info["import_name"]],
                   cwd=libdir, timeout=120)
    res["import_ok"] = rc == 0
    if rc != 0:
        res["errors"].append("import check failed: " + out[-500:])

    log_path = os.path.join(libdir, "fuzz.log")
    rc, _ = _run([py, "fuzz.py", "-max_total_time=%d" % int(duration)],
                 cwd=libdir, timeout=int(duration) + 60, stderr_path=log_path)
    res["fuzz_ran"] = os.path.exists(log_path) and os.path.getsize(log_path) > 0
    if res["fuzz_ran"]:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
        for marker in ("INITED", "NEW cov:", "pulse cov:", "cov:",
                        "Done", "ERROR: libFuzzer", "Uncaught"):
            if marker in text:
                res["log_markers"].append(marker)
    else:
        res["errors"].append("fuzz produced no log (rc=%s)" % rc)
    return res


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    root = os.path.abspath(req.get("root", "/app"))
    duration = req.get("duration", 10)

    libs = H.discover_libraries(root)
    libraries_txt = os.path.join(root, "libraries.txt")
    with open(libraries_txt, "w", encoding="utf-8") as fh:
        for lib in libs:
            fh.write(lib + "\n")

    results = []
    for lib in libs:
        try:
            results.append(process_lib(lib, duration))
        except Exception as e:  # noqa: BLE001
            results.append({"lib": lib, "errors": ["orchestration error: %s" % e]})

    json.dump({"libraries": libs, "libraries_txt": libraries_txt,
               "results": results}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
