#!/usr/bin/env python3
"""Recalculate an .xlsx in place with LibreOffice headless so cached values are
fresh (openpyxl only writes formula strings; it does not evaluate them).

Forces 'always recalculate' for OOXML/ODF via a throwaway user profile so no
interactive prompt blocks the conversion.

stdin JSON:  {"path": str, "timeout": int?}
stdout JSON: {"ok": bool, "path": str?, "error": str?, "stdout": str?, "stderr": str?}
"""
import sys
import os
import json
import glob
import shutil
import tempfile
import subprocess

XCU = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
    '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
    ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
    '<prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
    '</oor:items>\n'
)


def find_soffice():
    for cand in ("soffice", "libreoffice"):
        p = shutil.which(cand)
        if p:
            return p
    return None


def main():
    req = json.load(sys.stdin)
    path = os.path.abspath(req["path"])
    if not os.path.exists(path):
        json.dump({"ok": False, "error": "path not found: %s" % path}, sys.stdout)
        return

    soffice = find_soffice()
    if not soffice:
        json.dump({"ok": False, "error": "soffice not found"}, sys.stdout)
        return

    profile = tempfile.mkdtemp(prefix="loprof_")
    userdir = os.path.join(profile, "user")
    os.makedirs(userdir, exist_ok=True)
    with open(os.path.join(userdir, "registrymodifications.xcu"), "w") as f:
        f.write(XCU)

    outdir = tempfile.mkdtemp(prefix="loout_")
    env = dict(os.environ)
    env["HOME"] = profile
    cmd = [
        soffice, "--headless", "--nologo", "--norestore", "--nofirststartwizard",
        "-env:UserInstallation=file://" + profile,
        "--convert-to", "xlsx:Calc MS Excel 2007 XML",
        "--outdir", outdir, path,
    ]
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True,
                           timeout=int(req.get("timeout", 180)))
    except subprocess.TimeoutExpired:
        json.dump({"ok": False, "error": "soffice timeout"}, sys.stdout)
        return

    produced = glob.glob(os.path.join(outdir, "*.xlsx"))
    if not produced:
        json.dump({"ok": False, "error": "no output produced",
                   "stdout": r.stdout[-800:], "stderr": r.stderr[-800:]}, sys.stdout)
        return

    try:
        shutil.copyfile(produced[0], path)
    except Exception as e:
        json.dump({"ok": False, "error": "copyback failed: %s" % e}, sys.stdout)
        return

    json.dump({"ok": True, "path": path, "stdout": r.stdout[-400:]}, sys.stdout)


if __name__ == "__main__":
    main()
