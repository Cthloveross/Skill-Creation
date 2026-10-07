---
name: ppdev-syzlang-support
description: Install and validate syzkaller syzlang descriptions for the Linux ppdev (/dev/parportN) driver, including its open resource, complete ioctl surface, mode/driver flags, and decimal constants. Use when a syzkaller checkout needs ppdev support.
---

# ppdev syzlang support

Use `scripts/install_ppdev.py` to create `sys/linux/dev_ppdev.txt` and
`sys/linux/dev_ppdev.txt.const` in a supplied syzkaller checkout.  The generator
contains the ppdev UAPI ioctl specification and computes ioctl encodings rather
than copying precomputed command numbers.  It emits the 23 ppdev ioctls defined
by the stable ppdev UAPI:

- Four no-argument claim/access ioctls.
- Mode, phase, flags, timing, data, status/control, IRQ, and negotiation ioctls.
- Correct user-space data-flow directions (`in` for `_IOW`, `out` for `_IOR`).
- A two-byte `ppdev_frob_struct` and IEEE1284/ppdev flag sets.

The generated constants target the ioctl layout specified in the task: 32-bit
`int`, one-byte `unsigned char`, two-byte frob struct, and the amd64 16-byte
`timeval` encoding.  The constants file declares `amd64, 386` as requested;
all non-`timeval` values are identical between those ABIs.  If a checkout needs
a runtime-correct 32-bit `PPGETTIME`/`PPSETTIME` encoding, obtain an
architecture-specific constants file using that checkout's supported syzkaller
constant-generation workflow before fuzzing 32-bit kernels.

## Input and output

The script reads one JSON object from standard input and writes one JSON result
to standard output.

Input schema:

```json
{
  "syzkaller_root": "/opt/syzkaller",
  "action": "install"
}
```

- `syzkaller_root` is required and must contain `sys/linux`.
- `action` is optional: `install` (default) writes both files atomically and
  validates the generated content; `validate` validates the two already present
  files without changing them.

A successful result includes `ok: true`, the file paths, and the ioctl count.
Malformed input, a missing checkout directory, a missing/incorrect description,
or a broken constants mapping causes a JSON result with `ok: false` and a
nonzero exit status.

## Execution procedure

1. Run the installer with the intended checkout root:

   ```sh
   python3 scripts/install_ppdev.py <<'JSON'
   {"syzkaller_root":"/opt/syzkaller","action":"install"}
   JSON
   ```

2. Confirm its JSON reports 23 ioctls and both generated paths.
3. Build with the task-required commands from the checkout root:

   ```sh
   cd /opt/syzkaller
   make descriptions
   make all TARGETOS=linux TARGETARCH=amd64
   ```

4. If a build fails, retain the full compiler/build diagnostic.  First check
   that the checkout's syzlang syntax and its generic `ioctl`/`syz_open_dev`
   declarations support the emitted forms.  Do not silently replace decimal
   constants with hexadecimal or change pointer directions to suppress a
   failure: both would alter the ppdev UAPI contract.

## Validation performed by the helper

The helper verifies the exact named 23-ioctl set, all no-data versus pointer
arities, pointer directions, frob field widths, required includes/resource/open
specialization, required flag members, decimal-only constant values, every
symbolic constant reference, and recomputed ioctl command values.  This is
structural/UAPI validation; the two `make` commands remain the authoritative
syzkaller parser and build validation.
