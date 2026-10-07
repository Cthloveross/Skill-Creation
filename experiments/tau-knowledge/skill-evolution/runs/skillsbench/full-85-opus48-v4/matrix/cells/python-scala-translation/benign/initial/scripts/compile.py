#!/usr/bin/env python3
"""Compile the translated Scala file using the project's build.

stdin JSON: {"workdir": str (default '/root'), "scala_path": str (default workdir/Tokenizer.scala)}
stdout JSON: {"ok", "tool", "returncode", "has_error_lines", "output_tail", "cmd"}
"""
import json
import os
import shutil
import subprocess
import sys


def which(name):
    return shutil.which(name) is not None


def run(cmd, cwd, timeout):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") if hasattr(e, 'stdout') else ""
        return 124, (out or "") + "\n[timeout]"
    except Exception as e:
        return 1, "[exec error] %s" % e


def main():
    try:
        req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        req = {}
    workdir = req.get("workdir") or "/root"
    scala_path = req.get("scala_path") or os.path.join(workdir, "Tokenizer.scala")
    build_sbt = os.path.join(workdir, "build.sbt")

    result = {"ok": False, "tool": "none", "returncode": -1,
              "has_error_lines": False, "output_tail": "", "cmd": ""}

    if not os.path.isfile(scala_path):
        result["output_tail"] = "scala file not found: %s" % scala_path
        print(json.dumps(result))
        return

    if os.path.isfile(build_sbt) and which("sbt"):
        cmd = "sbt -batch -no-colors compile"
        rc, out = run(cmd, workdir, 600)
        result["tool"] = "sbt"
    elif which("scalac"):
        cmd = "scalac %s -d /tmp/scala_out" % scala_path
        os.makedirs("/tmp/scala_out", exist_ok=True)
        rc, out = run(cmd, workdir, 600)
        result["tool"] = "scalac"
    else:
        result["output_tail"] = "no sbt or scalac available; compilation not verified"
        print(json.dumps(result))
        return

    result["cmd"] = cmd
    result["returncode"] = rc
    has_err = any(line.strip().startswith("[error]") or " error:" in line or line.strip().startswith("error:")
                  for line in out.splitlines())
    result["has_error_lines"] = has_err
    result["ok"] = (rc == 0 and not has_err)
    tail = out[-4000:]
    result["output_tail"] = tail
    print(json.dumps(result))


if __name__ == "__main__":
    main()
