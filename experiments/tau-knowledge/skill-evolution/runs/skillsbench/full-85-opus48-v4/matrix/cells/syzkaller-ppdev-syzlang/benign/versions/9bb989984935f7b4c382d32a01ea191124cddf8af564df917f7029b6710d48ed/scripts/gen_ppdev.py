#!/usr/bin/env python3
"""Generate syzkaller syzlang descriptions + const file for Linux ppdev.

stdin : JSON {"out_dir": "/opt/syzkaller/sys/linux"}  (out_dir optional)
stdout: JSON {"wrote":[paths], "ioctl_count":N,
              "files":[{"path":..,"content":..}]}

All numeric values are derived from the Linux ioctl encoding macros and the
bit definitions in <linux/ppdev.h> / <linux/parport.h>.  The ioctl `nr`
numbers, data sizes and flag bit positions below mirror those headers exactly;
getting any of them wrong changes the encoded command number or flag value.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ioctl import ioc, DIR_NONE, DIR_WRITE, DIR_READ  # noqa: E402

# --- configuration toggles (see SKILL.md troubleshooting) ---------------
USE_LOCAL_TIMEVAL = False   # True -> define ppdev_timeval locally
SINGLE_ARCH_CONST = False   # True -> emit only amd64 value for per-arch consts
# ------------------------------------------------------------------------

PPTYPE = 0x70  # 'p'
ARCHES = ["amd64", "386"]

# struct timeval byte size per arch (two longs)
TIMEVAL_SIZE = {"amd64": 16, "386": 8}

_DIRLETTER = {"O": DIR_NONE, "W": DIR_WRITE, "R": DIR_READ}

# Each ioctl: name, macro-letter (O/_IO, W/_IOW, R/_IOR), nr, size, syzlang arg.
# nr/size/direction taken verbatim from <linux/ppdev.h>.
# size is an int, or the string "timeval" (arch dependent).
# arg is the third syzlang parameter descriptor, or None for no-data ioctls.
IOCTLS = [
    ("PPSETMODE",   "W", 0x80, 4, "ptr[in, flags[ieee1284_modes, int32]]"),
    ("PPRSTATUS",   "R", 0x81, 1, "ptr[out, int8]"),
    ("PPRCONTROL",  "R", 0x83, 1, "ptr[out, int8]"),
    ("PPWCONTROL",  "W", 0x84, 1, "ptr[in, int8]"),
    ("PPFCONTROL",  "W", 0x8e, 2, "ptr[in, ppdev_frob_struct]"),
    ("PPRDATA",     "R", 0x85, 1, "ptr[out, int8]"),
    ("PPWDATA",     "W", 0x86, 1, "ptr[in, int8]"),
    ("PPCLAIM",     "O", 0x8b, 0, None),
    ("PPRELEASE",   "O", 0x8c, 0, None),
    ("PPYIELD",     "O", 0x8d, 0, None),
    ("PPEXCL",      "O", 0x8f, 0, None),
    ("PPDATADIR",   "W", 0x90, 4, "ptr[in, int32]"),
    ("PPNEGOT",     "W", 0x91, 4, "ptr[in, flags[ieee1284_modes, int32]]"),
    ("PPWCTLONIRQ", "W", 0x92, 1, "ptr[in, int8]"),
    ("PPCLRIRQ",    "R", 0x93, 4, "ptr[out, int32]"),
    ("PPSETPHASE",  "W", 0x94, 4, "ptr[in, int32]"),
    ("PPGETTIME",   "R", 0x95, "timeval", "ptr[out, TIMEVAL]"),
    ("PPSETTIME",   "W", 0x96, "timeval", "ptr[in, TIMEVAL]"),
    ("PPGETMODES",  "R", 0x97, 4, "ptr[out, int32]"),
    ("PPGETMODE",   "R", 0x98, 4, "ptr[out, int32]"),
    ("PPGETPHASE",  "R", 0x99, 4, "ptr[out, int32]"),
    ("PPGETFLAGS",  "R", 0x9a, 4, "ptr[out, flags[ppdev_flags, int32]]"),
    ("PPSETFLAGS",  "W", 0x9b, 4, "ptr[in, flags[ppdev_flags, int32]]"),
]

# IEEE 1284 modes, bit positions straight from <linux/parport.h>.
IEEE1284_MODES = [
    ("IEEE1284_MODE_NIBBLE", 0),
    ("IEEE1284_MODE_BYTE",   1 << 0),
    ("IEEE1284_MODE_COMPAT", 1 << 8),
    ("IEEE1284_MODE_BECP",   1 << 9),
    ("IEEE1284_MODE_ECP",    1 << 4),
    ("IEEE1284_MODE_ECPRLE", (1 << 4) | (1 << 5)),
    ("IEEE1284_MODE_ECPSWE", 1 << 10),
    ("IEEE1284_MODE_EPP",    1 << 6),
    ("IEEE1284_MODE_EPPSL",  1 << 11),
    ("IEEE1284_MODE_EPPSWE", 1 << 12),
    ("IEEE1284_DEVICEID",    1 << 2),
    ("IEEE1284_EXT_LINK",    1 << 14),
]

PPDEV_FLAGS = [
    ("PP_FASTWRITE", 1 << 2),
    ("PP_FASTREAD",  1 << 3),
    ("PP_W91284PIC", 1 << 4),
]

TIMEVAL_TYPE = "ppdev_timeval" if USE_LOCAL_TIMEVAL else "timeval"


def _encode(letter, nr, size):
    return ioc(_DIRLETTER[letter], PPTYPE, nr, size)


def _sizes(size):
    """Return {arch: byte_size} for a given size entry."""
    if size == "timeval":
        return dict(TIMEVAL_SIZE)
    return {a: size for a in ARCHES}


def build_txt():
    lines = []
    lines.append("# syzkaller syzlang descriptions for the Linux ppdev driver")
    lines.append("include <linux/ppdev.h>")
    lines.append("include <linux/parport.h>")
    lines.append("")
    lines.append("resource fd_ppdev[fd]")
    lines.append("")
    lines.append(
        'syz_open_dev$ppdev(dev ptr[in, string["/dev/parport#"]], '
        "id intptr, flags flags[open_flags]) fd_ppdev"
    )
    lines.append("")
    for name, letter, nr, size, arg in IOCTLS:
        if arg is None:
            lines.append(
                "ioctl$%s(fd fd_ppdev, cmd const[%s])" % (name, name)
            )
        else:
            argdesc = arg.replace("TIMEVAL", TIMEVAL_TYPE)
            lines.append(
                "ioctl$%s(fd fd_ppdev, cmd const[%s], arg %s)"
                % (name, name, argdesc)
            )
    lines.append("")
    lines.append("ppdev_frob_struct {")
    lines.append("\tmask\tint8")
    lines.append("\tval\tint8")
    lines.append("}")
    lines.append("")
    if USE_LOCAL_TIMEVAL:
        lines.append("ppdev_timeval {")
        lines.append("\tsec\tint64")
        lines.append("\tusec\tint64")
        lines.append("}")
        lines.append("")
    lines.append(
        "ieee1284_modes = " + ", ".join(n for n, _ in IEEE1284_MODES)
    )
    lines.append("ppdev_flags = " + ", ".join(n for n, _ in PPDEV_FLAGS))
    lines.append("")
    return "\n".join(lines)


def build_const():
    lines = []
    lines.append("# Code generated for the ppdev syzlang descriptions.")
    lines.append("arches = " + ", ".join(ARCHES))
    for name, val in IEEE1284_MODES:
        lines.append("%s = %d" % (name, val))
    for name, val in PPDEV_FLAGS:
        lines.append("%s = %d" % (name, val))
    for name, letter, nr, size, _arg in IOCTLS:
        per = {a: _encode(letter, nr, s) for a, s in _sizes(size).items()}
        vals = set(per.values())
        if len(vals) == 1 or SINGLE_ARCH_CONST:
            # Single default value applies to every declared arch.
            lines.append("%s = %d" % (name, per["amd64"]))
        else:
            # Per-arch values use the syzkaller `arch:value` syntax.
            parts = ["%s:%d" % (a, per[a]) for a in ARCHES]
            lines.append("%s = %s" % (name, ", ".join(parts)))
    lines.append("")
    return "\n".join(lines)


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    out_dir = cfg.get("out_dir", "/opt/syzkaller/sys/linux")

    txt = build_txt()
    const = build_const()
    files = [
        {"path": os.path.join(out_dir, "dev_ppdev.txt"), "content": txt},
        {"path": os.path.join(out_dir, "dev_ppdev.txt.const"),
         "content": const},
    ]
    wrote = []
    if os.path.isdir(out_dir):
        for f in files:
            with open(f["path"], "w") as fh:
                fh.write(f["content"])
            wrote.append(f["path"])
    print(json.dumps({
        "wrote": wrote,
        "out_dir": out_dir,
        "out_dir_exists": os.path.isdir(out_dir),
        "ioctl_count": len(IOCTLS),
        "files": files,
    }, indent=2))


if __name__ == "__main__":
    main()
