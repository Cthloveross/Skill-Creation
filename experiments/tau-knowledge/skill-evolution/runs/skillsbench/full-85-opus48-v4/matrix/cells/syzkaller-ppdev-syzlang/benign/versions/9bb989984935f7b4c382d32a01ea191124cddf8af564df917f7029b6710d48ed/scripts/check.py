#!/usr/bin/env python3
"""Structural validation of generated dev_ppdev.txt / .txt.const.

stdin : JSON {"out_dir": "/opt/syzkaller/sys/linux"}
stdout: JSON {"ok": bool, "errors": [...], "ioctl_count": N}

Checks (does NOT run make):
  * both files exist
  * .const begins with an `arches =` declaration
  * exactly 23 ioctl$ lines and matching const entries
  * every const name referenced in the .txt has a .const entry
  * all const values are decimal (optionally arch-tagged)
"""
import json
import os
import re
import sys


def parse_const(text):
    names = {}
    arches = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("arches"):
            arches = line
            continue
        if "=" not in line:
            continue
        name, val = line.split("=", 1)
        names[name.strip()] = val.strip()
    return arches, names


def referenced_consts(txt):
    refs = set()
    for m in re.finditer(r"const\[([A-Za-z0-9_]+)\]", txt):
        refs.add(m.group(1))
    for m in re.finditer(r"flags\[([A-Za-z0-9_]+)", txt):
        pass  # flag set names are defined in the txt, not consts
    # members of flag sets (RHS of `name = A, B, C`) must be consts
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        lhs, rhs = s.split("=", 1)
        if "[" in lhs or "(" in lhs:
            continue
        for tok in rhs.split(","):
            tok = tok.strip()
            if re.fullmatch(r"[A-Z][A-Z0-9_]+", tok):
                refs.add(tok)
    return refs


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    out_dir = cfg.get("out_dir", "/opt/syzkaller/sys/linux")
    txt_p = os.path.join(out_dir, "dev_ppdev.txt")
    const_p = os.path.join(out_dir, "dev_ppdev.txt.const")
    errors = []

    if not os.path.exists(txt_p):
        errors.append("missing %s" % txt_p)
    if not os.path.exists(const_p):
        errors.append("missing %s" % const_p)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return

    txt = open(txt_p).read()
    const = open(const_p).read()
    arches, const_names = parse_const(const)

    if arches is None:
        errors.append("const file lacks an `arches =` declaration")

    ioctl_lines = re.findall(r"^ioctl\$([A-Za-z0-9_]+)\(", txt, re.M)
    if len(ioctl_lines) != 23:
        errors.append("expected 23 ioctl$ lines, found %d" % len(ioctl_lines))

    refs = referenced_consts(txt)
    for r in sorted(refs):
        if r not in const_names:
            errors.append("const referenced in .txt missing from .const: %s" % r)

    # value sanity: decimal, optionally arch tagged like `N:amd64, M:386`
    for name, val in const_names.items():
        for part in val.split(","):
            part = part.strip()
            # Per-arch entries use syzkaller `arch:value` syntax, so the
            # numeric value is the last colon-separated field.
            num = part.split(":")[-1].strip()
            if not re.fullmatch(r"-?\d+", num):
                errors.append("non-decimal const value: %s = %s" % (name, val))
                break

    if "resource fd_ppdev[fd]" not in txt:
        errors.append("missing `resource fd_ppdev[fd]`")
    if "syz_open_dev$" not in txt or "/dev/parport#" not in txt:
        errors.append("missing syz_open_dev opener for /dev/parport#")

    print(json.dumps({
        "ok": not errors,
        "errors": errors,
        "ioctl_count": len(ioctl_lines),
        "arches": arches,
    }, indent=2))


if __name__ == "__main__":
    main()
