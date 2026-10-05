#!/usr/bin/env python3
"""Recalculate an xlsx in LibreOffice and require cached numeric model results.
stdin: {"workbook_path":"/path/file.xlsx"}
stdout: {"ok":bool,"workbook_path":"...","error":"..."}
"""
import json, os, shutil, subprocess, sys, tempfile
import openpyxl


def recalculate(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        raise ValueError("workbook_path must identify an existing .xlsx file")
    executable = next((shutil.which(x) for x in ("libreoffice", "soffice") if shutil.which(x)), None)
    if not executable:
        raise RuntimeError("No LibreOffice/soffice executable is available for required workbook recalculation")
    with tempfile.TemporaryDirectory(prefix="xlsx_recalc_") as root:
        source_dir = os.path.join(root, "source")
        output_dir = os.path.join(root, "output")
        profile_dir = os.path.join(root, "profile")
        os.makedirs(source_dir)
        os.makedirs(output_dir)
        staged = os.path.join(source_dir, "workbook.xlsx")
        shutil.copy2(path, staged)
        command = [
            executable, "--headless", "--nologo", "--nodefault", "--nolockcheck",
            "-env:UserInstallation=file://" + profile_dir,
            "--convert-to", "xlsx", "--outdir", output_dir, staged,
        ]
        run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, timeout=180)
        calculated = os.path.join(output_dir, "workbook.xlsx")
        if run.returncode != 0 or not os.path.isfile(calculated):
            detail = (run.stderr or run.stdout or "conversion produced no workbook").strip()
            raise RuntimeError("LibreOffice recalculation failed: " + detail[:500])
        # Validate the calculated copy before replacing the requested artifact.
        values = openpyxl.load_workbook(calculated, data_only=True)
        if "SUT Calc" not in values.sheetnames:
            raise RuntimeError("recalculated workbook lacks SUT Calc")
        share = values["SUT Calc"]["C46"].value
        if not isinstance(share, (int, float)) or not 0 <= share <= 1:
            raise RuntimeError("recalculation did not produce a numeric [0,1] SUT Calc!C46 result")
        shutil.copy2(calculated, path)
    return os.path.abspath(path)


def main(payload):
    return {"ok": True, "workbook_path": recalculate(payload.get("workbook_path"))}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)
