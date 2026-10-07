#!/usr/bin/env python3
"""Copy freshly built Druid module jars over the matching jars in the running
distribution's lib directory so the restarted server loads the patched code.

Stdin (JSON, all optional):
  {
    "druid_root": "/root/druid",   # source tree with built */target/*.jar
    "lib_dir":    "/opt/druid/lib" # distribution lib the server runs from
  }

Stdout (JSON):
  {
    "status": "ok" | "error",
    "copied": [ {"from": ..., "to": ...}, ... ],
    "core_deployed": true|false,
    "message": "..."
  }

Strategy: for every druid-*.jar already present in lib_dir, if a jar with the exact
same filename exists under <druid_root>/*/target/, copy it over. This guarantees the
rebuilt druid-core jar (which contains the GuiceAnnotationIntrospector fix) replaces
the shipped one, without renaming or guessing versions.
"""
import glob
import json
import os
import shutil
import sys


def out(d):
    sys.stdout.write(json.dumps(d))
    sys.exit(0 if d.get("status") != "error" else 1)


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}

    root = cfg.get("druid_root", "/root/druid")
    lib = cfg.get("lib_dir", "/opt/druid/lib")

    if not os.path.isdir(lib):
        out({"status": "error", "copied": [], "core_deployed": False,
             "message": "lib_dir not found: %s" % lib})

    # Map built jar basename -> built path (prefer module/target, skip shaded dirs if dup).
    built = {}
    for p in glob.glob(os.path.join(root, "*", "target", "*.jar")):
        base = os.path.basename(p)
        # Ignore sources/javadoc/original jars.
        if base.endswith("-sources.jar") or base.endswith("-javadoc.jar"):
            continue
        if base.startswith("original-"):
            continue
        built.setdefault(base, p)

    copied = []
    core_deployed = False
    for lp in glob.glob(os.path.join(lib, "druid-*.jar")):
        base = os.path.basename(lp)
        src = built.get(base)
        if src and os.path.abspath(src) != os.path.abspath(lp):
            shutil.copy2(src, lp)
            copied.append({"from": src, "to": lp})
            if base.startswith("druid-core-"):
                core_deployed = True

    if not copied:
        out({"status": "error", "copied": [], "core_deployed": False,
             "message": "no matching built jars copied; confirm the Maven build "
                        "succeeded and jar names in %s match <module>/target/" % lib})

    msg = "deployed %d jar(s)" % len(copied)
    if not core_deployed:
        msg += " (WARNING: druid-core jar was not among them \u2014 verify the fix is in core)"
    out({"status": "ok", "copied": copied, "core_deployed": core_deployed, "message": msg})


if __name__ == "__main__":
    main()
