#!/usr/bin/env python3
"""Install or validate Linux ppdev syzlang support in a syzkaller checkout.

Reads JSON on stdin:
  {"syzkaller_root": "/opt/syzkaller", "action": "install" | "validate"}
Writes a JSON result on stdout.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# (name, ioctl direction, request number, argument byte size)
# Direction names here are Linux ioctl encoding directions, not syzlang ptr
# directions.  "none" means _IO, "read" means _IOR, "write" means _IOW.
IOCTLS: Sequence[Tuple[str, str, int, int]] = (
    ("PPCLAIM", "none", 0x8B, 0),
    ("PPRELEASE", "none", 0x8C, 0),
    ("PPYIELD", "none", 0x8D, 0),
    ("PPEXCL", "none", 0x8F, 0),
    ("PPRSTATUS", "read", 0x81, 1),
    ("PPRCONTROL", "read", 0x83, 1),
    ("PPWCONTROL", "write", 0x84, 1),
    ("PPFCONTROL", "write", 0x8E, 2),
    ("PPRDATA", "read", 0x85, 1),
    ("PPWDATA", "write", 0x86, 1),
    ("PPDATADIR", "write", 0x90, 4),
    ("PPNEGOT", "write", 0x91, 4),
    ("PPWCTLONIRQ", "write", 0x92, 1),
    ("PPCLRIRQ", "read", 0x93, 4),
    ("PPSETTIME", "write", 0x96, 16),
    ("PPGETTIME", "read", 0x95, 16),
    ("PPGETMODES", "read", 0x97, 4),
    ("PPGETMODE", "read", 0x98, 4),
    ("PPSETMODE", "write", 0x80, 4),
    ("PPGETPHASE", "read", 0x99, 4),
    ("PPSETPHASE", "write", 0x94, 4),
    ("PPGETFLAGS", "read", 0x9A, 4),
    ("PPSETFLAGS", "write", 0x9B, 4),
)

MODE_FLAGS: Sequence[Tuple[str, int]] = (
    ("IEEE1284_MODE_NIBBLE", 0),
    ("IEEE1284_MODE_BYTE", 1 << 0),
    ("IEEE1284_MODE_COMPAT", 1 << 8),
    ("IEEE1284_MODE_BECP", 1 << 9),
    ("IEEE1284_MODE_ECP", 1 << 4),
    ("IEEE1284_MODE_ECPRLE", 1 << 5),
    ("IEEE1284_MODE_ECPSWE", 1 << 10),
    ("IEEE1284_MODE_EPP", 1 << 6),
    ("IEEE1284_MODE_EPPSL", 1 << 11),
    ("IEEE1284_MODE_EPPSWE", 1 << 12),
    ("IEEE1284_DEVICEID", 1 << 2),
    ("IEEE1284_EXT_LINK", 1 << 14),
    ("IEEE1284_ADDR", 1 << 13),
    ("IEEE1284_DATA", 0),
)

PPDEV_FLAGS: Sequence[Tuple[str, int]] = (
    ("PP_FASTWRITE", 1 << 2),
    ("PP_FASTREAD", 1 << 3),
    ("PP_W91284PIC", 1 << 4),
)


def ioctl_value(direction: str, nr: int, size: int) -> int:
    """Encode a ppdev ioctl for the Linux generic 32-bit ioctl layout."""
    direction_bits = {"none": 0, "write": 0x40000000, "read": 0x80000000}
    if direction not in direction_bits:
        raise ValueError("unknown ioctl direction: %s" % direction)
    return direction_bits[direction] | (size << 16) | (ord("p") << 8) | nr


def syz_arg_type(name: str) -> str:
    """Return the pointee type for the named ioctl."""
    if name in {"PPRSTATUS", "PPRCONTROL", "PPWCONTROL", "PPRDATA", "PPWDATA", "PPWCTLONIRQ"}:
        return "int8"
    if name == "PPFCONTROL":
        return "ppdev_frob_struct"
    if name in {"PPSETTIME", "PPGETTIME"}:
        return "timeval"
    if name in {"PPNEGOT", "PPSETMODE", "PPGETMODE", "PPGETMODES"}:
        return "flags[ieee1284_modes, int32]"
    if name in {"PPSETFLAGS", "PPGETFLAGS"}:
        return "flags[ppdev_flags, int32]"
    return "int32"


def description() -> str:
    lines: List[str] = [
        "# Linux parallel-port user device (ppdev).",
        "include <linux/ppdev.h>",
        "include <linux/parport.h>",
        "",
        "resource fd_ppdev[fd]",
        "",
        'syz_open_dev$ppdev(dev ptr[in, string["/dev/parport#"]], id intptr, flags flags[open_flags]) fd_ppdev',
        "",
        "# _IO access-control operations have no data argument.",
    ]
    for name, direction, _nr, _size in IOCTLS:
        if direction == "none":
            lines.append("ioctl$%s(fd fd_ppdev, cmd const[%s])" % (name, name))
    lines.extend([
        "",
        "ppdev_frob_struct {",
        "\tmask\tint8",
        "\tval\tint8",
        "}",
        "",
        "ieee1284_modes = " + ", ".join(name for name, _value in MODE_FLAGS),
        "ppdev_flags = " + ", ".join(name for name, _value in PPDEV_FLAGS),
        "",
        "# _IOR is output to user space; _IOW is input from user space.",
    ])
    for name, direction, _nr, _size in IOCTLS:
        if direction == "none":
            continue
        ptr_direction = "out" if direction == "read" else "in"
        lines.append(
            "ioctl$%s(fd fd_ppdev, cmd const[%s], arg ptr[%s, %s])"
            % (name, name, ptr_direction, syz_arg_type(name))
        )
    return "\n".join(lines) + "\n"


def constants() -> str:
    lines = [
        "# Linux ppdev constants; ioctl values use the amd64 timeval ABI.",
        "arches = amd64, 386",
    ]
    for name, direction, nr, size in IOCTLS:
        lines.append("%s = %d" % (name, ioctl_value(direction, nr, size)))
    for name, value in MODE_FLAGS:
        lines.append("%s = %d" % (name, value))
    for name, value in PPDEV_FLAGS:
        lines.append("%s = %d" % (name, value))
    return "\n".join(lines) + "\n"


def parse_constants(text: str) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("arches"):
            continue
        match = re.fullmatch(r"([A-Z0-9_]+) = ([0-9]+)", line)
        if not match:
            raise ValueError("non-decimal or malformed constants line: %r" % line)
        name, value = match.groups()
        if name in values:
            raise ValueError("duplicate constant: %s" % name)
        values[name] = int(value)
    return values


def validate(desc: str, const: str) -> None:
    expected_names = {name for name, _direction, _nr, _size in IOCTLS}
    if len(IOCTLS) != 23 or len(expected_names) != 23:
        raise ValueError("internal ppdev ioctl specification is not exactly 23 unique ioctls")
    for include in ("include <linux/ppdev.h>", "include <linux/parport.h>"):
        if include not in desc:
            raise ValueError("missing required include: %s" % include)
    if "resource fd_ppdev[fd]" not in desc:
        raise ValueError("missing fd_ppdev resource")
    opener = 'syz_open_dev$ppdev(dev ptr[in, string["/dev/parport#"]], id intptr, flags flags[open_flags]) fd_ppdev'
    if opener not in desc:
        raise ValueError("missing or malformed ppdev device opener")
    if not re.search(r"ppdev_frob_struct \{\s+mask\s+int8\s+val\s+int8\s+\}", desc, re.S):
        raise ValueError("ppdev_frob_struct must contain two int8 fields")

    described = set(re.findall(r"^ioctl\$(PP[A-Z0-9]+)\(", desc, re.M))
    if described != expected_names:
        missing = sorted(expected_names - described)
        extra = sorted(described - expected_names)
        raise ValueError("ioctl set mismatch; missing=%s extra=%s" % (missing, extra))
    for name, direction, _nr, _size in IOCTLS:
        if direction == "none":
            expected = "ioctl$%s(fd fd_ppdev, cmd const[%s])" % (name, name)
        else:
            user_direction = "out" if direction == "read" else "in"
            expected = "ioctl$%s(fd fd_ppdev, cmd const[%s], arg ptr[%s, %s])" % (
                name, name, user_direction, syz_arg_type(name))
        if expected not in desc:
            raise ValueError("missing incorrect-arity or incorrect-direction ioctl: %s" % name)

    for flag_set, members in (("ieee1284_modes", MODE_FLAGS), ("ppdev_flags", PPDEV_FLAGS)):
        match = re.search(r"^%s = (.+)$" % flag_set, desc, re.M)
        if not match:
            raise ValueError("missing flag set: %s" % flag_set)
        actual = {part.strip() for part in match.group(1).split(",")}
        wanted = {name for name, _value in members}
        if actual != wanted:
            raise ValueError("incorrect members for flag set: %s" % flag_set)

    if not re.search(r"^arches = amd64, 386$", const, re.M):
        raise ValueError("constants file must declare arches = amd64, 386")
    values = parse_constants(const)
    expected_values = {name: ioctl_value(direction, nr, size) for name, direction, nr, size in IOCTLS}
    expected_values.update(dict(MODE_FLAGS))
    expected_values.update(dict(PPDEV_FLAGS))
    if values != expected_values:
        missing = sorted(set(expected_values) - set(values))
        extra = sorted(set(values) - set(expected_values))
        wrong = sorted(name for name in set(values) & set(expected_values)
                       if values[name] != expected_values[name])
        raise ValueError("constant mapping mismatch; missing=%s extra=%s wrong=%s" % (missing, extra, wrong))

    referenced = set(re.findall(r"const\[([A-Z0-9_]+)\]", desc))
    for match in re.finditer(r"^(?:ieee1284_modes|ppdev_flags) = (.+)$", desc, re.M):
        referenced.update(part.strip() for part in match.group(1).split(","))
    absent = sorted(referenced - set(values))
    if absent:
        raise ValueError("description references constants absent from .const: %s" % absent)


def atomic_write(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(content)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        root_value = request.get("syzkaller_root")
        if not isinstance(root_value, str) or not root_value:
            raise ValueError("syzkaller_root must be a nonempty string")
        action = request.get("action", "install")
        if action not in {"install", "validate"}:
            raise ValueError("action must be install or validate")
        linux_dir = Path(root_value).expanduser().resolve() / "sys" / "linux"
        if not linux_dir.is_dir():
            raise ValueError("syzkaller_root does not contain sys/linux: %s" % linux_dir)
        txt_path = linux_dir / "dev_ppdev.txt"
        const_path = linux_dir / "dev_ppdev.txt.const"
        if action == "install":
            txt, const = description(), constants()
            validate(txt, const)
            atomic_write(txt_path, txt)
            atomic_write(const_path, const)
        else:
            if not txt_path.is_file() or not const_path.is_file():
                raise ValueError("both ppdev files must exist for validate action")
            txt = txt_path.read_text(encoding="utf-8")
            const = const_path.read_text(encoding="utf-8")
            validate(txt, const)
        print(json.dumps({
            "ok": True,
            "action": action,
            "ioctl_count": len(IOCTLS),
            "description": str(txt_path),
            "constants": str(const_path),
        }, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
