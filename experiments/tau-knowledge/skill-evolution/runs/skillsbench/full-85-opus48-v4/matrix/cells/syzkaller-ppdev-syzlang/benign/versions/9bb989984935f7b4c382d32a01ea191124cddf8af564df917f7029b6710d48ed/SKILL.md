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
(not hand-typed), so the generator stays correct and auditable. The per-ioctl
`nr`, data size and direction, and the flag bit positions, are taken verbatim
from `<linux/ppdev.h>` and `<linux/parport.h>` (enumerated in
`references/ppdev_ioctls.md`). If those headers are present in the environment
(`/usr/include/linux/ppdev.h`, `/usr/include/linux/parport.h`), verify the
tables against them before trusting the output.

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
* Watch the non-obvious `nr` values from the header: PPRDATA=0x85,
  PPWDATA=0x86, PPFCONTROL=0x8e (they are not sequential with the surrounding
  ioctls). The IEEE1284 mode bits are likewise not a simple ascending run:
  ECPSWE=1<<10, EPP=1<<6, EPPSL=1<<11, EPPSWE=1<<12.
* Flag values come from `<linux/parport.h>` (IEEE1284 modes) and
  `<linux/ppdev.h>` (PP_FAST* / PP_W91284PIC).

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
   referenced const present, decimal/arch-tagged values):

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

   Both must finish with exit code 0. `make descriptions` runs `syz-sysgen`,
   which fully parses the `.txt`+`.txt.const` for every declared arch and
   checks that each ioctl's embedded size matches its struct's per-arch size;
   `make all` builds the binaries for amd64. Inspect any non-zero exit / error
   output and fix the files. `make all` is large (several minutes) — run it in
   the background and poll if your shell has a short timeout.

### Build-environment workarounds (apply only if the plain commands fail)

These are environment quirks, not part of the deliverable, but the build must
succeed to satisfy the task:

* If `go` is older than syzkaller's `go.mod` (`go 1.24.4`) and the Go toolchain
  auto-download is blocked (TLS sinkhole on `proxy.golang.org`), fetch the
  toolchain directly from Google and use it with `GOTOOLCHAIN=local`:
  `curl -sSL -o /tmp/go.tgz https://dl.google.com/go/go1.24.4.linux-amd64.tar.gz`,
  `tar -C /usr/local -xzf /tmp/go.tgz`, then prepend `/usr/local/go/bin` to PATH.
* If module downloads via `proxy.golang.org` fail with the same TLS error, use
  `GOPROXY=direct GOSUMDB=off` so modules come straight from their VCS
  (github.com / go.googlesource.com), which are reachable.
* If `make` fails with `go: parsing $GOFLAGS: unknown flag -X`, the shell's
  environment already defines `GOFLAGS`, so make re-exports its own `GOFLAGS`
  (the `-ldflags "... -X ..."` value) into the recipe environment where `go`
  rejects it. Run make with `env -u GOFLAGS make ...` to clear it.
* Putting it together:
  `cd /opt/syzkaller && PATH=/usr/local/go/bin:$PATH GOTOOLCHAIN=local
  GOPROXY=direct GOSUMDB=off env -u GOFLAGS make descriptions` and likewise for
  `make all TARGETOS=linux TARGETARCH=amd64`.

## Input / output schema of the scripts

* `gen_ppdev.py`: stdin JSON `{"out_dir": <dir>}` (optional, default
  `/opt/syzkaller/sys/linux`). Writes the two files and emits the JSON above.
* `check.py`: stdin JSON `{"out_dir": <dir>}`. Reads the two generated files
  and reports structural validity. It does not run make.

## Design choices and troubleshooting

* `timeval` is **reused** from syzkaller's global definitions (defined in
  `sys/linux/sys.txt` as `timeval { sec time_sec; usec time_usec }`, which is
  already per-arch sized); the Skill does not redefine it to avoid a
  redefinition error. If a build error reports `timeval` is undefined, set
  `USE_LOCAL_TIMEVAL = True` in `gen_ppdev.py` to emit a local 2×int64 struct.
* **Per-arch const syntax.** syzkaller's parser expects `arch:value` pairs
  (e.g. `PPGETTIME = amd64:2148561045, 386:2148036757`), NOT `value:arch`.
  A constant equal on all arches is a single bare decimal. Getting the order
  wrong makes `syz-sysgen` fail with `failed to parse int: parsing "amd64"`.
  If you ever need to target only amd64, set `SINGLE_ARCH_CONST = True` to emit
  one amd64 value per const.
* Every symbolic name used in the `.txt` has a matching decimal entry in the
  `.txt.const`; missing entries make `syz-sysgen` fail. `check.py` guards this.
* Values in the `.const` file are decimal, never hex.
* Do not copy generated numbers into the Skill as literals — the script derives
  them from the encoding rules so they stay correct across arches. The
  `references/ppdev_ioctls.md` decimal list is only a cross-check.
