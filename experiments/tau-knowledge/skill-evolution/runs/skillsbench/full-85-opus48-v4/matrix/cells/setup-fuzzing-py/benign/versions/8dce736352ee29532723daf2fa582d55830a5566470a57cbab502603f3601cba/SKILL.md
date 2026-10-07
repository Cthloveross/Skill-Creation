---
name: setup-fuzzing-py
description: >-
  Set up coverage-guided fuzzing (Atheris + libFuzzer) for a set of Python
  libraries that live as sub-projects in a working directory. Use when a task
  asks you to list libraries under test, analyze their important/parser
  functions, write Atheris fuzz drivers (fuzz.py), create per-library .venv
  environments, install the project plus Atheris, and run a short timed fuzzing
  smoke test with the libFuzzer log captured from stderr.
---

# Setup Python Fuzzing (Atheris / libFuzzer)

## When to use

The task gives a working directory (e.g. `/app/`) that contains several Python
library projects and asks you to:

1. Discover the libraries and list their paths in a listing file
   (e.g. `/app/libraries.txt`).
2. For each library, analyze important functions and write
   `/<lib>/notes_for_testing.txt`.
3. Write an Atheris fuzz driver `/<lib>/fuzz.py` that imports and calls the
   real target library inside instrumented scope.
4. Create `/<lib>/.venv`, install the project + its deps + `atheris`.
5. Run the fuzzer for a short budget (e.g. 10s) and redirect libFuzzer's
   **stderr** to `/<lib>/fuzz.log`.

Read the actual task text each run for the exact root directory, listing-file
path, filenames, and the time budget. Do **not** hardcode library names.

## Method (what the scripts do)

All deterministic work is in `scripts/`. Each script reads a JSON object on
stdin and writes a JSON object on stdout. They import the shared helper
`scripts/fuzzlib.py`.

- `scripts/discover.py` — finds the library project directories under the root
  (dirs that contain a `pyproject.toml`/`setup.py`/`setup.cfg` or an importable
  Python package) and writes one absolute path per line to the listing file.
  Skips the skill/environment dir, dotfiles, and non-project dirs.
- `scripts/analyze.py` — for one library, locates the importable top-level
  package (handles `src/` layout), AST-scans it for public, single-required-arg
  functions whose names look like parsers/loaders/decoders/formatters
  (`loads`, `load`, `parse`, `decode`, `read`, `dumps`, `format`, `compile`,
  `tokenize`, …), ranks them, writes a human-readable
  `notes_for_testing.txt`, and emits the chosen targets as JSON.
- `scripts/gen_driver.py` — writes `fuzz.py` from the chosen targets. The
  driver imports the specific submodules inside `atheris.instrument_imports()`,
  decorates `TestOneInput` with `atheris.instrument_func`, uses
  `FuzzedDataProvider` to make a unicode string, and calls each target inside a
  broad-but-named `except` so only unexpected failures surface. Importing the
  specific submodule (not the whole package) keeps startup fast.
- `scripts/setup_and_run.py` — for one library: creates `.venv`, upgrades pip,
  installs the project (`pip install -e .` then fallback `pip install .`),
  installs any `requirements*.txt`, installs `atheris`, verifies both the
  package and `atheris` import, then runs
  `python fuzz.py -max_total_time=<N>` with **stderr redirected to fuzz.log**.
  It returns import/run status plus detected success markers.
- `scripts/run_all.py` — orchestrates everything end-to-end: discover → (per
  library) analyze → gen_driver → setup_and_run. Runs libraries sequentially to
  respect memory limits. Returns a per-library summary.

## How to run (executor)

Resolve the skill scripts dir (the task's skill directory, e.g.
`/app/environment/skills/current/scripts`). End-to-end:

```bash
SK=/app/environment/skills/current/scripts
echo '{"root":"/app","listing":"/app/libraries.txt","max_total_time":10}' \
  | python3 "$SK/run_all.py"
```

Or step-by-step (useful for debugging one library):

```bash
echo '{"root":"/app","listing":"/app/libraries.txt"}' | python3 "$SK/discover.py"
echo '{"library":"/app/LIB"}' | python3 "$SK/analyze.py"
echo '{"library":"/app/LIB"}' | python3 "$SK/gen_driver.py"   # reads analyze output cache
echo '{"library":"/app/LIB","max_total_time":10}' | python3 "$SK/setup_and_run.py"
```

`run_all.py` is the recommended entry point. If it reports that a library
failed, read the returned step logs, fix the specific library (see below), and
re-run `setup_and_run.py` for just that library.

## Interpreting results / validation

A fuzzing run is healthy when `fuzz.log` (stderr) contains libFuzzer markers:
`INITED cov:`, `NEW_FUNC`/`NEW cov:`, periodic `#... cov:` pulses, and a final
`Done <n> runs in <t> second(s)` line. **A crash is a successful finding**, not
a setup error: if the log instead ends with a libFuzzer fatal-signal /
`ERROR: libFuzzer` block and a reproducer artifact, that counts as working.
`setup_and_run.py` reports these markers in `success_markers`.

After running, verify (the scripts also check these):
- the listing file exists and has one resolvable path per library;
- each `<lib>/notes_for_testing.txt`, `<lib>/fuzz.py`, `<lib>/.venv`, and
  `<lib>/fuzz.log` exist;
- the venv Python can `import <pkg>` and `import atheris`;
- `fuzz.log` is non-empty and shows coverage activity (not merely a process
  that stayed alive). An empty log usually means stderr was not redirected.

## Failure handling

- **Atheris won't install**: `pip install atheris` normally fetches a
  manylinux wheel (internet is allowed). If it needs a compiler, install clang
  via the system package manager, then re-run `setup_and_run.py`.
- **Target import is slow / heavy package**: the driver already imports only the
  specific submodule. If a package still initializes heavy subsystems on import,
  narrow the target in `notes_for_testing.txt`/`fuzz.py` to a leaf submodule.
- **Chosen function needs non-str input**: the driver feeds a unicode string;
  functions needing other types just raise and are caught. If a library has no
  str/bytes parser, pick a `dict`/bytes entry point and adjust the driver call.
- **No coverage events**: check import order — the target import must be inside
  `atheris.instrument_imports()` — and confirm the called function reaches
  target-library code. The `@atheris.instrument_func` on `TestOneInput`
  guarantees a minimal Python coverage surface.
- **Local source shadows installed package**: scripts run the fuzzer from the
  library root (editable install), which is intended; for pure-Python libs this
  is fine.

Do not create placeholder venvs or drivers that never call the real library.
Do not copy library names or path conventions from examples — discover them at
runtime and verify each listing entry resolves.
