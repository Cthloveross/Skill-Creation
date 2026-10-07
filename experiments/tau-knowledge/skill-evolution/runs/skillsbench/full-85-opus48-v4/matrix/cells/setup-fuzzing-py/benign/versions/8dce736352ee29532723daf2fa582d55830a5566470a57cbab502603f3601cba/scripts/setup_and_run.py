#!/usr/bin/env python3
"""Create .venv, install project + atheris, verify imports, run the fuzzer for
a short budget, and capture libFuzzer stderr to fuzz.log.

stdin JSON: {"library": "/app/LIB", "max_total_time": 10}
stdout JSON: {status fields, success_markers, log_tail}
"""
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuzzlib

MARKERS = ["INITED cov:", "NEW_FUNC", "NEW cov:", " cov: ", "Done ",
           "ERROR: libFuzzer", "DEADLYSIGNAL", "pulse"]


def _run(cmd, cwd=None, timeout=600):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return {"cmd": cmd, "rc": p.returncode,
                "out": p.stdout[-2000:], "err": p.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "rc": -1, "out": "", "err": "timeout"}
    except Exception as e:  # pragma: no cover
        return {"cmd": cmd, "rc": -2, "out": "", "err": str(e)}


def main():
    req = json.load(sys.stdin)
    lib = req["library"]
    budget = int(req.get("max_total_time", 10))
    result = {"library": lib, "steps": []}

    venv = os.path.join(lib, ".venv")
    py = os.path.join(venv, "bin", "python")
    pip = os.path.join(venv, "bin", "pip")

    if not os.path.exists(py):
        result["steps"].append(("venv", _run([sys.executable, "-m", "venv",
                                               ".venv"], cwd=lib, timeout=180)))
    result["steps"].append(("pip_upgrade",
                            _run([py, "-m", "pip", "install", "-q",
                                  "--upgrade", "pip"], cwd=lib, timeout=180)))

    # install the project itself (editable, then non-editable fallback)
    if fuzzlib.has_project_marker(lib):
        inst = _run([pip, "install", "-q", "-e", "."], cwd=lib, timeout=480)
        if inst["rc"] != 0:
            inst = _run([pip, "install", "-q", "."], cwd=lib, timeout=480)
        result["steps"].append(("install_project", inst))

    # install requirements files if present
    for reqf in glob.glob(os.path.join(lib, "requirements*.txt")):
        result["steps"].append(("install_reqs:" + os.path.basename(reqf),
                                _run([pip, "install", "-q", "-r", reqf],
                                     cwd=lib, timeout=480)))

    result["steps"].append(("install_atheris",
                            _run([pip, "install", "-q", "atheris"], cwd=lib,
                                 timeout=480)))

    # verify imports
    pkg = None
    cache = os.path.join(lib, ".fuzz_targets.json")
    if os.path.exists(cache):
        try:
            pkg = json.load(open(cache)).get("package", {}).get("pkg")
        except Exception:
            pkg = None
    if pkg is None:
        pi = fuzzlib.find_package(lib)
        pkg = pi["pkg"] if pi else None
    v_atheris = _run([py, "-c", "import atheris"], cwd=lib, timeout=60)
    result["import_atheris_ok"] = v_atheris["rc"] == 0
    if pkg:
        v_pkg = _run([py, "-c", "import %s" % pkg], cwd=lib, timeout=120)
        result["import_package_ok"] = v_pkg["rc"] == 0
        result["import_package_err"] = v_pkg["err"][-500:]

    # run the fuzzer, stderr -> fuzz.log
    log = os.path.join(lib, "fuzz.log")
    fuzz_py = os.path.join(lib, "fuzz.py")
    run_info = {"rc": None}
    if os.path.exists(fuzz_py):
        with open(log, "wb") as lf:
            try:
                p = subprocess.run([py, "fuzz.py",
                                    "-max_total_time=%d" % budget],
                                   cwd=lib, stdout=subprocess.DEVNULL,
                                   stderr=lf, timeout=budget + 90)
                run_info["rc"] = p.returncode
            except subprocess.TimeoutExpired:
                run_info["rc"] = -1
                run_info["note"] = "timeout (process killed)"
            except Exception as e:  # pragma: no cover
                run_info["rc"] = -2
                run_info["note"] = str(e)
    else:
        run_info["note"] = "fuzz.py missing"
    result["fuzz_run"] = run_info

    tail = ""
    markers = []
    if os.path.exists(log):
        try:
            data = open(log, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            data = ""
        tail = data[-3000:]
        markers = [m for m in MARKERS if m in data]
        result["log_bytes"] = os.path.getsize(log)
    result["log_tail"] = tail
    result["success_markers"] = markers
    result["fuzzing_ok"] = bool(markers)
    # convert step tuples to serializable form
    result["steps"] = [{"name": n, "rc": s["rc"], "err": s["err"][-400:]}
                        for (n, s) in result["steps"]]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
