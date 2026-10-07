# Completion checklist (derived from the public task)

For the configured root (default `/app`):

- [ ] Listing file (default `/app/libraries.txt`) exists; one path per library;
      every path resolves to a directory. Expect 5 entries for this task.
- [ ] For each `<lib>`:
  - [ ] `<lib>/notes_for_testing.txt` lists the analyzed functions under test.
  - [ ] `<lib>/fuzz.py` is an Atheris driver with `TestOneInput`,
        `FuzzedDataProvider`, instrumentation (`atheris.instrument_imports()`
        around the real target import + `@atheris.instrument_func`),
        `atheris.Setup(sys.argv, TestOneInput)`, and `atheris.Fuzz()`.
  - [ ] The driver imports and calls the real target library (not just stdlib).
  - [ ] `<lib>/.venv/bin/python` can `import <pkg>` and `import atheris`.
  - [ ] `<lib>/fuzz.log` is non-empty and shows libFuzzer coverage activity
        (`INITED cov:`, `NEW cov:`/`NEW_FUNC`, pulses, `Done ... runs`).

# Reading results

- libFuzzer writes to **stderr**; the log must come from stderr redirection.
- A crash finding (`ERROR: libFuzzer` / `DEADLYSIGNAL` + reproducer) is a
  SUCCESS, not a setup error — the normal `Done` line will be absent then.
- An empty log => stderr was not redirected, or the driver exited immediately
  (missing `atheris.Fuzz()` or import error). Inspect and fix.
- No coverage events => check that the target import is inside
  `atheris.instrument_imports()` and that the called function reaches target
  code; the `@atheris.instrument_func` decorator guarantees a minimal surface.

# Common fixes

- `pip install atheris` needing a compiler: install clang via the system
  package manager, then re-run `setup_and_run.py` for that library.
- Heavy/slow package import: narrow `fuzz.py` to a specific leaf submodule.
- Function needs non-str input: the broad `except` keeps the loop alive; pick a
  better str/bytes/dict entry point if coverage stays flat.
