---
name: syzkaller-ppdev-syzlang
description: >
  Generate syzkaller syzlang descriptions for the Linux parallel-port user
  device driver (ppdev, /dev/parport*). Produces /opt/syzkaller/sys/linux/
  dev_ppdev.txt (resource, syz_open_dev opener, all 23 ppdev ioctls with
  correct in/out directions, the ppdev_frob_struct, IEEE1284 mode flags and
  ppdev flags) and the companion dev_ppdev.txt.const (arches declaration plus
  decimal ioctl numbers and flag values computed from the Linux _IO/_IOR/_IOW
  encoding). Use when a task asks to add syzkaller syzlang support for ppdev
  and to verify it with `make descriptions` and `make all`.
---

# syzkaller ppdev syzlang descriptions

## What this Skill does

It writes two files that make the syzkaller fuzzer understand the Linux ppdev
parallel-port driver:

* `dev_ppdev.txt` – syzlang descriptions.
* `dev_ppdev.txt.const` – the symbolic-name → decimal-value table syzkaller
  needs to compile the descriptions.

The numeric ioctl values are **computed** from the Linux ioctl encoding macros
(not hardcoded), so the generator stays correct and auditable.

## Background facts baked into the generator

* ioctl encoding (bits): `dir<<30 | size<<16 | type<<8 | nr`.
  * `_IO` dir=0, `_IOW` dir=1 (`0x40000000`), `_IOR` dir=2 (`0x80000000`).
* ppdev type character `'p'` = `0x70`.
* Pointer direction is from the **user-space** perspective and is the opposite
  of the macro letter: `_IOR` → `ptr[out, ...]`, `_IOW` → `ptr[in, ...]`,
  `_IO` → no third argument.
* Argument sizes: `int`/`unsigned int` = 4, `unsigned char` = 1,
  `struct ppdev_frob_struct` = 2 (two `unsigned char`), `struct timeval`
  = 16 on amd64 and 8 on 386 (so PPGETTIME/PPSETTIME differ per arch).
* Flag values come from `<linux/parport.h>` (IEEE1284 modes) and
  `<linux/ppdev.h>` (PP_FAST* / PP_W91284PIC).

The 23 ppdev ioctls and their directions/sizes are enumerated in
`references/ppdev_ioctls.md` and encoded in `scripts/gen_ppdev.py`.

## How to run (executor steps)

1. Generate the files into the syzkaller tree (default out dir
   `/opt/syzkaller/sys/linux`):

   ```bash
   python3 /app/environment/skills/current/scripts/gen_ppdev.py <<< '{}'
   ```

   To target a different directory pass JSON on stdin, e.g.
   `{"out_dir": "/opt/syzkaller/sys/linux"}`.
   The script prints JSON: `{"wrote": [paths], "ioctl_count": 23,
   "files": [{"path":..,"content":..}]}`.

2. Structurally validate what was written (counts, arches line, every
   referenced const present):

   ```bash
   python3 /app/environment/skills/current/scripts/check.py \
     <<< '{"out_dir": "/opt/syzkaller/sys/linux"}'
   ```

   It prints `{"ok": true, ...}` or lists problems in `errors`.

3. Build and verify as the task requires:

   ```bash
   cd /opt/syzkaller
   make descriptions
   make all TARGETOS=linux TARGETARCH=amd64
   ```

   Both must finish with exit code 0. `make descriptions` compiles the
   `.txt`+`.txt.const` for every declared arch; `make all` builds the binaries
   for amd64. Inspect any non-zero exit / error output and fix the files.

## Input / output schema of the scripts

* `gen_ppdev.py`: stdin JSON `{"out_dir": <dir>}` (optional, default
  `/opt/syzkaller/sys/linux`). Writes the two files and emits the JSON above.
* `check.py`: stdin JSON `{"out_dir": <dir>}`. Reads the two generated files
  and reports structural validity. It does not run make.

## Design choices and troubleshooting

* `timeval` is **reused** from syzkaller's global definitions (it is defined in
  the shared sys/linux descriptions); the Skill does not redefine it to avoid a
  redefinition error. If a build error reports `timeval` is undefined, add a
  local struct instead (two `int64` fields) and point PPGETTIME/PPSETTIME at it
  — see the commented fallback in `gen_ppdev.py` (`USE_LOCAL_TIMEVAL`).
* PPGETTIME/PPSETTIME use per-arch const values with the
  `VALUE:amd64, VALUE:386` syntax because `struct timeval` is 16 bytes on amd64
  and 8 on 386. If `make descriptions` rejects that syntax, set
  `SINGLE_ARCH_CONST = True` in `gen_ppdev.py` to emit one amd64 value per
  const (compiles for the amd64 target).
* Every symbolic name used in the `.txt` has a matching decimal entry in the
  `.txt.const`; missing entries make `syz-sysgen` fail. `check.py` guards this.
* Values in the `.const` file are decimal, never hex.
* Do not copy generated numbers into the Skill as literals — the script derives
  them from the encoding rules so they stay correct across arches.
