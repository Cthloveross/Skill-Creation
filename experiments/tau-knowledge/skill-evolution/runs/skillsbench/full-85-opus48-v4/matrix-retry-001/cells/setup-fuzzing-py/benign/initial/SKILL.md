---
name: setup-fuzzing-py
description: Set up Atheris/libFuzzer coverage-guided fuzzing for several Python libraries sitting side-by-side in a working directory. Use when a task asks you to (1) list library paths, (2) write per-library testing notes, (3) generate an Atheris fuzz driver, (4) create a per-library virtualenv with dependencies + atheris, and (5) run a short (e.g. 10s) smoke fuzz capturing the libFuzzer log. Discovers libraries, import names and parser entry points at runtime; nothing about the specific libraries is hardcoded.
---

# setup-fuzzing-py

## What the task requires (public contract)

For each library found under the working directory (the opening says 5 live in `/app`):

1. **`/app/libraries.txt`** — one absolute path per library under test.
2. **`/app/<lib>/notes_for_testing.txt`** — analysis of important functions to fuzz
   (import name + candidate parser/loader/formatter entry points).
3. **`/app/<lib>/fuzz.py`** — an Atheris/libFuzzer fuzz driver that actually imports
   and calls the target library's API inside instrumented scope.
4. **`/app/<lib>/.venv`** — a Python virtualenv with the project's dependencies and
   `atheris` installed.
5. **`/app/<lib>/fuzz.log`** — libFuzzer stderr from a ~10s run (stderr, not stdout).

A valid run shows coverage progression (`INITED cov:`, `NEW cov:`, `pulse cov:`) and a
`Done N runs in 10 second(s)` completion line, OR a crash diagnostic + reproducer
(a crash is a successful finding, not a setup error).

## Method (assumptions)

- Each library is a Python project directory containing `pyproject.toml`/`setup.py`/
  `setup.cfg` and/or an importable package dir (`<pkg>/__init__.py`, possibly under
  `src/`). The import name is the top-level package dir, which can differ from the
  project name.
- Good fuzz targets are shallow public functions whose name contains a parser verb
  (`loads/load/parse/decode/read/dumps/format/...`) and that accept one argument.
  The driver feeds a `FuzzedDataProvider` string (falling back to bytes on `TypeError`).
- The generated driver inserts the package's source parent dir on `sys.path`, so it
  imports the target even if `pip install .` only partially succeeds. Native-extension
  libraries still need their build toolchain; diagnose from the log.
- The driver decorates `TestOneInput` with `atheris.instrument_func` and imports the
  target inside `atheris.instrument_imports()` so coverage is always observable.
- Exceptions are caught broadly: the goal here is a working, coverage-producing smoke
  run, not immediate crash triage.

## Fastest path: one entrypoint

Run the orchestrator; it discovers libraries, writes `libraries.txt`, and for each
library writes `notes_for_testing.txt`, `fuzz.py`, builds `.venv`, installs deps +
atheris, and runs the fuzzer ~10s into `fuzz.log`.

```
echo '{"root":"/app","duration":10}' | \
  python3 /app/environment/skills/current/scripts/orchestrate.py
```

Stdin JSON: `{"root": <workdir, default "/app">, "duration": <seconds, default 10>}`.
Stdout JSON: `{"libraries":[...], "results":[{"lib","import_name","module","func",
"install_ok","import_ok","fuzz_ran","log_markers","errors":[...]}...]}`.

The orchestrator runs real subprocesses (venv/pip/fuzzer). If the environment lacks a
build toolchain for `atheris` or a native library, inspect `errors` and the per-lib
`fuzz.log`, then fix with the manual steps below.

## Manual / per-step control

Use these when a single library needs special handling:

- **Discover libraries only:**
  `echo '{"root":"/app"}' | python3 .../scripts/discover.py` → `{"libraries":[...]}`.
- **Analyze + write notes and driver for one lib:**
  `echo '{"lib":"/app/<lib>"}' | python3 .../scripts/build_driver.py`
  → writes `notes_for_testing.txt` + `fuzz.py`, returns `{import_name,module,func,candidates}`.
- **Build the venv and run (shell):**
  ```
  cd /app/<lib>
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install .            # or: ./.venv/bin/pip install -r requirements.txt
  ./.venv/bin/pip install atheris
  ./.venv/bin/python -c "import atheris, <import_name>"   # sanity
  ./.venv/bin/python fuzz.py -max_total_time=10 2> fuzz.log
  ```
  Note the `2>` — libFuzzer writes to **stderr**; redirecting stdout yields an empty log.

For a slow-to-import framework, prefer importing the specific submodule holding the
target (the driver already imports `module` via `importlib`, not the whole package by
name when a submodule was chosen).

## Validating the output

After running, confirm the contract:

```
wc -l /app/libraries.txt                       # expect one path per library (5)
for d in $(cat /app/libraries.txt); do
  ls "$d"/notes_for_testing.txt "$d"/fuzz.py "$d"/.venv/bin/python "$d"/fuzz.log
  grep -E 'cov:|Done .* runs|INITED|NEW_FUNC|ERROR: libFuzzer|Uncaught' "$d"/fuzz.log | head
done
```

A `fuzz.log` is healthy if it contains `cov:` progression and either a `Done ... runs`
line or a crash/reproducer diagnostic. An empty log means stderr was not captured or the
driver exited before `atheris.Fuzz()` (check import order / target import failure near the
top of the log). A process that merely stayed alive with no `cov:` events is not
coverage-guided — recheck the import name and instrumentation.

## Handling missing data / unsupported cases

- No parser-verb function found: the analyzer falls back to the first public callable in
  `__init__` and records this in the notes; the driver still exercises real library code.
- `pip install .` fails but the package is pure Python: the driver's `sys.path` insertion
  lets it import from source — the fuzzer can still run. Record the install error in notes.
- `atheris` build fails or a native dependency is missing: this is a real environment
  limitation; capture the diagnostic and report it rather than fabricating a passing log.
