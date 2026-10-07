#!/usr/bin/env python3
"""Force a full recalculation of an xlsx with LibreOffice headless.

stdin  : {"path": str, "out_dir": str?}
stdout : {"recalculated": str, "stdout": str, "returncode": int}
       | {"error": str, ...}

Creates a throwaway LibreOffice user profile whose registrymodifications.xcu
sets ODF/OOXML recalc-on-load to "Always" (value 0), so --convert-to recomputes
formula cells and stores fresh cached values. The converted file is written to
out_dir (default: same directory as the input) with the same base name.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
           xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load">
  <prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop>
 </item>
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load">
  <prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop>
 </item>
</oor:items>
"""


def _soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    return None


def main():
    req = json.load(sys.stdin)
    path = req["path"]
    out_dir = req.get("out_dir") or os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)
    exe = _soffice()
    if not exe:
        json.dump({"error": "libreoffice/soffice not found on PATH"}, sys.stdout)
        return
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    user_dir = os.path.join(profile, "user")
    os.makedirs(user_dir, exist_ok=True)
    with open(os.path.join(user_dir, "registrymodifications.xcu"), "w",
              encoding="utf-8") as fh:
        fh.write(XCU)
    cmd = [exe, "--headless", "--nologo", "--nofirststartwizard",
           f"-env:UserInstallation=file://{profile}",
           "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
           "--outdir", out_dir, path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:  # noqa: BLE001
        json.dump({"error": f"soffice run failed: {exc}"}, sys.stdout)
        return
    base = os.path.splitext(os.path.basename(path))[0] + ".xlsx"
    recalculated = os.path.join(out_dir, base)
    json.dump({"recalculated": recalculated,
               "stdout": (proc.stdout or "") + (proc.stderr or ""),
               "returncode": proc.returncode}, sys.stdout)


if __name__ == "__main__":
    main()
