"""Shared helpers for the weighted-GDP net-exports Skill.

Nothing here is task-instance specific: all coordinates and keys are passed in
by the caller after runtime discovery.
"""
import os
import shutil
import subprocess
import tempfile

from openpyxl.utils import get_column_letter, column_index_from_string  # noqa: F401


def norm_val(v):
    """Normalize a cell value for key comparison.

    Integers-as-floats collapse to int; strings strip whitespace.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip()
    return v


def as_key(v):
    """Hashable comparable key for codes/years."""
    nv = norm_val(v)
    if isinstance(nv, str):
        return nv.casefold()
    return nv


def cl(idx):
    return get_column_letter(idx)


def fill_signature(cell):
    """A small, stable signature of a cell fill for format-preservation checks."""
    try:
        f = cell.fill
        fg = getattr(f.fgColor, "rgb", None)
        return (f.patternType, str(fg))
    except Exception:
        return None


def find_soffice():
    for name in ("libreoffice", "soffice"):
        p = shutil.which(name)
        if p:
            return p
    return None


def recalc_with_libreoffice(src_path):
    """Recalculate an xlsx by round-tripping through LibreOffice with
    recalc-on-load forced. Returns path to a recalculated copy, or None.
    Does NOT modify src_path.
    """
    soffice = find_soffice()
    if not soffice:
        return None
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    outdir = tempfile.mkdtemp(prefix="lo_out_")
    # Force "Always recalculate" on OOXML/ODF load so cached values are fresh.
    reg_dir = os.path.join(profile, "user")
    os.makedirs(reg_dir, exist_ok=True)
    reg = os.path.join(reg_dir, "registrymodifications.xcu")
    xcu = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
        'xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        '<item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
        '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
        '<item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
        '<prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
        '</oor:items>\n'
    )
    try:
        with open(reg, "w", encoding="utf-8") as fh:
            fh.write(xcu)
    except Exception:
        pass
    cmd = [
        soffice,
        "-env:UserInstallation=file://%s" % profile,
        "--headless",
        "--calc",
        "--convert-to",
        "xlsx:Calc MS Excel 2007 XML",
        "--outdir",
        outdir,
        src_path,
    ]
    try:
        subprocess.run(cmd, timeout=180, capture_output=True)
    except Exception:
        return None
    base = os.path.splitext(os.path.basename(src_path))[0] + ".xlsx"
    out = os.path.join(outdir, base)
    return out if os.path.exists(out) else None


ERROR_MARKERS = ("#DIV/0!", "#N/A", "#REF!", "#VALUE!", "#NAME?", "#NUM!", "#NULL!")


def is_error_value(v):
    return isinstance(v, str) and v.strip() in ERROR_MARKERS
