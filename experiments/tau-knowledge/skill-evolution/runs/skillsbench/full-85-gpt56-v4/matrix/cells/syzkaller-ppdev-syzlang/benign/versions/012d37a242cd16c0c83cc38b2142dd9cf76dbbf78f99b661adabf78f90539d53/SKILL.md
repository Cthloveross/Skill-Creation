---
name: syzkaller-ppdev-syzlang
summary: Create and validate syzlang support for Linux ppdev (/dev/parport#), including its 23 ioctl descriptions and decimal constants.
---

# Syzkaller ppdev syzlang support

Use this Skill when a syzkaller checkout needs `sys/linux/dev_ppdev.txt` and its companion constants file for the Linux ppdev UAPI.

## Method

1. Inspect the checkout's `include/uapi/linux/ppdev.h` (or installed `linux/ppdev.h`) before writing. The canonical interface contains 23 ppdev commands: four no-argument port-ownership commands and 19 pointer-argument commands.
2. Generate the two files with the packaged script. It deliberately uses a private `ppdev_timeval` syzlang struct with two `intptr` fields, so its description has the target ABI's correct 16-byte amd64 / 8-byte 386 layout.
3. Confirm that every `const[...]` symbol and every flag member in the `.txt` has a decimal assignment in `.txt.const`. Ioctl values must use the actual `_IO`, `_IOR`, and `_IOW` direction and payload size.
4. Run the required syzkaller build commands from the checkout. Treat compiler or sysgen failures as evidence to inspect the local syzlang conventions and UAPI header; do not silently omit commands.

The packaged generator targets the explicitly requested `amd64, 386` constants-file declaration. Its runtime numeric ioctl calculation uses the executing Python ABI's `long` size for timeval commands; run it in the target build environment (the supplied task builds amd64). If a checkout's constants-file parser supports per-architecture values, use its local convention when also validating 386, because timeval ioctl encodings differ between the two ABIs.

## Generate files

The script reads one JSON object from stdin and emits one JSON result to stdout:

- `root` (string, default `/opt/syzkaller`): syzkaller checkout root.
- `write` (bool, default `true`): write `sys/linux/dev_ppdev.txt` and `.txt.const`.
- `build` (bool, default `false`): after writing, run `make descriptions` and `make all TARGETOS=linux TARGETARCH=amd64` in `root`.

Example:

```bash
printf '%s\n' '{"root":"/opt/syzkaller","write":true,"build":false}' | \
  python3 scripts/install_ppdev.py
cd /opt/syzkaller
make descriptions
make all TARGETOS=linux TARGETARCH=amd64
```

The JSON result reports output paths, the 23 generated ioctl names, the timeval byte size used in command encoding, and any build return codes. A successful build is the meaningful validation: it verifies syzlang grammar, constant coverage, and generated-description compilation.

## Interface details preserved by the generator

- `_IO` ownership ioctls have exactly `(fd, cmd)` and no pointer argument.
- `_IOW` arguments are `ptr[in, ...]`; `_IOR` arguments are `ptr[out, ...]`.
- `ppdev_frob_struct` has two `int8` fields, matching two one-byte UAPI fields.
- The opener returns `fd_ppdev` and uses `/dev/parport#`.
- IEEE 1284 mode values and ppdev fast-I/O flags are declared as syzlang flag sets and are included in the decimal constants file.

If the installed header has materially changed, update the generator's command table from that header, retaining these direction, size, and constants-coverage checks.
