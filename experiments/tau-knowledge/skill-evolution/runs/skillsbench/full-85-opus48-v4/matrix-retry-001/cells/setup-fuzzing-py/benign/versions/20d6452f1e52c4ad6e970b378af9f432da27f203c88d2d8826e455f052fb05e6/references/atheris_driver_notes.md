# Atheris / libFuzzer driver cheat-sheet

Required driver elements (all must be present):

1. `TestOneInput(data: bytes)` — one call per iteration.
2. `atheris.FuzzedDataProvider(data)` — turn raw bytes into structured input
   (`ConsumeUnicodeNoSurrogates`, `ConsumeBytes`, `ConsumeInt`, ...).
3. Instrumentation **before** importing the target: use
   `with atheris.instrument_imports(): import target` and/or
   `@atheris.instrument_func` on `TestOneInput`.
4. `atheris.Setup(sys.argv, TestOneInput)` — registers target, forwards libFuzzer flags.
5. `atheris.Fuzz()` — starts the loop; without it nothing is fuzzed. Does not return
   until the budget ends or a crash is found.

Run flags: `-max_total_time=10` (seconds) or `-runs=N` (iterations).

Logging: libFuzzer writes to **stderr**. Capture with `python fuzz.py -max_total_time=10 2> fuzz.log`.
Redirecting stdout alone yields an empty log.

Healthy-run markers in the log:
- `INITED cov: <N>` — initialized.
- `NEW cov: <N>` — input increased coverage.
- `pulse cov: <N>` — periodic status.
- `Done <N> runs in 10 second(s)` — budget exhausted (not printed if a crash happened).

A crash diagnostic + reproducer artifact is a successful finding, not a setup error.

Target selection: prefer shallow public parsers/loaders/formatters
(`loads/load/parse/decode/read/dumps/format`) that accept `str`/`bytes`/`dict`.
Read `__init__.py` and existing tests for known-good call patterns. For slow-to-import
frameworks, import only the submodule holding the target to keep startup fast.

Exceptions: catch expected library errors (ValueError, decode errors). For a quick
smoke-run across unfamiliar libraries, broad `except Exception` is acceptable so the loop
keeps producing coverage; tighten later for real bug-finding.
