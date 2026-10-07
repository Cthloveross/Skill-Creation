#!/usr/bin/env python3
"""Generate syzkaller's Linux ppdev syzlang files.

Input: JSON object on stdin: {"root": str, "write": bool, "build": bool}.
Output: JSON object describing generated paths, command names, and optional builds.
"""
import ctypes
import json
import pathlib
import subprocess
import sys

# (name, ioctl direction, command number, argument kind).  This is the 23-command
# ppdev UAPI surface in linux/ppdev.h; PPSETCHAR/PPGETCHAR are not ppdev ioctls.
COMMANDS = [
    ("PPSETMODE", "w", 0x80, "mode"),
    ("PPGETMODE", "r", 0x81, "mode"),
    ("PPGETPHASE", "r", 0x82, "int"),
    ("PPSETPHASE", "w", 0x83, "int"),
    ("PPGETMODES", "r", 0x84, "mode"),
    ("PPSETFLAGS", "w", 0x9b, "ppflags"),
    ("PPGETFLAGS", "r", 0x9a, "ppflags"),
    ("PPSETTIME", "w", 0x95, "timeval"),
    ("PPGETTIME", "r", 0x95, "timeval"),
    ("PPWCONTROL", "w", 0x83, "byte"),
    ("PPRCONTROL", "r", 0x84, "byte"),
    ("PPFCONTROL", "w", 0x8e, "frob"),
    ("PPRSTATUS", "r", 0x81, "byte"),
    ("PPDATADIR", "w", 0x90, "int"),
    ("PPNEGOT", "w", 0x91, "mode"),
    ("PPWDATA", "w", 0x86, "byte"),
    ("PPRDATA", "r", 0x85, "byte"),
    ("PPCLRIRQ", "r", 0x93, "int"),
    ("PPWCTLONIRQ", "w", 0x92, "byte"),
    ("PPCLAIM", "none", 0x8b, None),
    ("PPRELEASE", "none", 0x8c, None),
    ("PPYIELD", "none", 0x8d, None),
    ("PPEXCL", "none", 0x8f, None),
]

MODE_CONSTANTS = [
    ("IEEE1284_MODE_NIBBLE", 0),
    ("IEEE1284_MODE_BYTE", 1),
    ("IEEE1284_MODE_COMPAT", 1 << 8),
    ("IEEE1284_MODE_BECP", 1 << 9),
    ("IEEE1284_MODE_ECP", 1 << 4),
    ("IEEE1284_MODE_ECPRLE", (1 << 4) | (1 << 5)),
    ("IEEE1284_MODE_ECPSWE", (1 << 4) | (1 << 6)),
    ("IEEE1284_MODE_EPP", 1 << 2),
    ("IEEE1284_MODE_EPPSL", (1 << 2) | (1 << 3)),
]
PP_FLAG_CONSTANTS = [
    ("PP_FASTWRITE", 1 << 2),
    ("PP_FASTREAD", 1 << 3),
    ("PP_W91284PIC", 1 << 4),
]


def ioctl_value(direction, nr, size):
    """Linux x86 _IOC encoding for type 'p' (112)."""
    direction_bits = {"none": 0, "w": 0x40000000, "r": 0x80000000}[direction]
    return direction_bits | (size << 16) | (ord("p") << 8) | nr


def syz_argument(kind, direction):
    ptr_direction = "in" if direction == "w" else "out"
    types = {
        "mode": "flags[ieee1284_modes, int32]",
        "ppflags": "flags[ppdev_flags, int32]",
        "int": "int32",
        "timeval": "ppdev_timeval",
        "byte": "int8",
        "frob": "ppdev_frob_struct",
    }
    return "arg ptr[%s, %s]" % (ptr_direction, types[kind])


def descriptor_text():
    lines = [
        "# Linux ppdev (/dev/parport*) interface.",
        "include <linux/ppdev.h>",
        "include <linux/parport.h>",
        "",
        "resource fd_ppdev[fd]",
        "",
        "syz_open_dev$ppdev(dev ptr[in, string[\"/dev/parport#\"]], id intptr, flags flags[open_flags]) fd_ppdev",
        "",
        "# timeval uses long fields and hence follows the target intptr width.",
        "ppdev_timeval {",
        "\ttv_sec intptr",
        "\ttv_usec intptr",
        "}",
        "",
        "ppdev_frob_struct {",
        "\tmask int8",
        "\tval int8",
        "}",
        "",
        "ieee1284_modes = " + ", ".join(name for name, _ in MODE_CONSTANTS),
        "ppdev_flags = " + ", ".join(name for name, _ in PP_FLAG_CONSTANTS),
        "",
    ]
    for name, direction, _nr, kind in COMMANDS:
        if direction == "none":
            lines.append("ioctl$%s(fd fd_ppdev, cmd const[%s])" % (name, name))
        else:
            lines.append("ioctl$%s(fd fd_ppdev, cmd const[%s], %s)" %
                         (name, name, syz_argument(kind, direction)))
    return "\n".join(lines) + "\n"


def constants_text(timeval_size):
    sizes = {"mode": 4, "ppflags": 4, "int": 4, "timeval": timeval_size,
             "byte": 1, "frob": 2}
    constants = []
    for name, direction, nr, kind in COMMANDS:
        size = 0 if kind is None else sizes[kind]
        constants.append((name, ioctl_value(direction, nr, size)))
    constants.extend(MODE_CONSTANTS)
    constants.extend(PP_FLAG_CONSTANTS)
    names = [name for name, _ in constants]
    if len(names) != len(set(names)) or len(COMMANDS) != 23:
        raise ValueError("internal command/constants coverage error")
    lines = [
        "# Linux ppdev constants; ioctl values are decimal.",
        "arches = amd64, 386",
    ]
    lines.extend("%s = %d" % pair for pair in constants)
    return "\n".join(lines) + "\n"


def run_build(root):
    results = []
    for command in (["make", "descriptions"],
                    ["make", "all", "TARGETOS=linux", "TARGETARCH=amd64"]):
        completed = subprocess.run(command, cwd=str(root), text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({"command": command, "returncode": completed.returncode,
                        "output_tail": completed.stdout[-4000:]})
        if completed.returncode:
            break
    return results


def main():
    request = json.load(sys.stdin)
    root = pathlib.Path(request.get("root", "/opt/syzkaller"))
    write = request.get("write", True)
    timeval_size = ctypes.sizeof(ctypes.c_long) * 2
    output_dir = root / "sys" / "linux"
    txt = output_dir / "dev_ppdev.txt"
    const = output_dir / "dev_ppdev.txt.const"
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        txt.write_text(descriptor_text(), encoding="utf-8")
        const.write_text(constants_text(timeval_size), encoding="utf-8")
    result = {
        "root": str(root),
        "written": write,
        "paths": [str(txt), str(const)],
        "ioctl_count": len(COMMANDS),
        "ioctls": [name for name, _, _, _ in COMMANDS],
        "timeval_size_used": timeval_size,
    }
    if request.get("build", False):
        result["build"] = run_build(root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
