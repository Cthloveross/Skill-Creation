#!/usr/bin/env python3
"""Recalculate an .xlsx with LibreOffice so formulas gain fresh cached values.

openpyxl writes formula strings but never evaluates them; this converts the
file with the spreadsheet engine, which recomputes formulas that lack cached
values and stores the results while KEEPING the formulas.

stdin : {"path":"<file.xlsx>", "outdir":"/tmp/recalc"?, "timeout":180?}
stdout: {"ok":bool, "returncode":int, "outfile":"<path or null>",
         "stdout":..., "stderr":...}
After ok=true, copy outfile back over the deliverable if recalc was done to a
separate outdir.
"""
import sys, json, os, shutil, subprocess


def main():
    req = json.load(sys.stdin)
    path = os.path.abspath(req["path"])
    outdir = req.get("outdir") or (os.path.dirname(path) or ".")
    os.makedirs(outdir, exist_ok=True)
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        print(json.dumps({"ok": False, "returncode": -1, "outfile": None,
                          "stdout": "", "stderr": "libreoffice/soffice not found"}))
        return
    env = dict(os.environ)
    env.setdefault("HOME", "/tmp")
    cmd = [soffice, "--headless", "--calc", "--convert-to",
           "xlsx:Calc MS Excel 2007 XML", "--outdir", outdir, path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=int(req.get("timeout", 180)), env=env)
    except Exception as e:
        print(json.dumps({"ok": False, "returncode": -2, "outfile": None,
                          "stdout": "", "stderr": str(e)}))
        return
    outfile = os.path.join(outdir, os.path.basename(path))
    ok = r.returncode == 0 and os.path.exists(outfile)
    print(json.dumps({"ok": ok, "returncode": r.returncode,
                      "outfile": outfile if ok else None,
                      "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]}))


if __name__ == "__main__":
    main()
