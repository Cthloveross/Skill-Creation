---
name: setup-python-coverage-fuzzing
description: Set up and smoke-test Atheris/libFuzzer coverage-guided fuzzing for a fixed set of local Python library directories. Use when a task requires a library list, per-library target analysis notes, local virtual environments, fuzz.py drivers, and stderr fuzz logs.
---

# Python coverage-guided fuzzing setup

This skill operates on the libraries actually present at runtime. It does not assume package names, import paths, APIs, or dependency managers from another task.

## Required outcome

For every discovered target library, produce:

- an unambiguous line in `/app/libraries.txt`;
- `<library>/notes_for_testing.txt` describing real, inspected fuzz targets;
- `<library>/.venv` containing the project and Atheris;
- `<library>/fuzz.py`, which imports and invokes an actual library API under Atheris instrumentation;
- `<library>/fuzz.log`, capturing **stderr** from a ten-second libFuzzer run.

A fuzzer crash is a valid fuzzing finding. Preserve its log and do not rerun an operation whose result is unknown.

## Workflow

1. **Materialize and discover the dataset.** If `/app/build_dataset.sh` was supplied to construct the local test libraries, inspect it and run it once before discovery. Do not treat the build script itself, support directories, virtual environments, or generated cache directories as libraries.

   Run the discovery helper (it writes absolute POSIX paths, one per line):

   ```sh
   printf '%s' '{"action":"discover","root":"/app","output":"/app/libraries.txt","expected_count":5}' \
     | python /app/environment/skills/current/scripts/fuzz_setup.py
   ```

   Inspect `libraries.txt`. If the count is not five, stop and determine which top-level directories are the actual projects rather than guessing. The task's stated library count is a prerequisite.

2. **Inspect each library before generating a driver.** Read its `pyproject.toml`, `setup.py`, `setup.cfg`, requirements/lock files, package source, public `__init__.py`, and relevant tests. Favor shallow public parsers, loaders, decoders, formatters, or constructors accepting text, bytes, or dictionaries. Avoid a target requiring network, database, GUI, or persistent external state.

   The analyzer is an aid, not proof that a candidate is callable. It parses Python ASTs and writes a starting note:

   ```sh
   while IFS= read -r lib; do
     printf '{"action":"analyze","library":%s,"write_notes":true}\n' "$(python -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$lib")" \
       | python /app/environment/skills/current/scripts/fuzz_setup.py
   done < /app/libraries.txt
   ```

   Edit each `notes_for_testing.txt` after reviewing the source. It must name the selected importable module and callable, its expected argument shape, why it is a useful target, and expected malformed-input exceptions. This makes the selection auditable and provides the specification for the driver.

3. **Create isolated environments and install the actual projects.** Run this per library:

   ```sh
   printf '{"action":"provision","library":%s}\n' "$(python -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$lib")" \
     | python /app/environment/skills/current/scripts/fuzz_setup.py
   ```

   The helper creates `<library>/.venv`, upgrades packaging tools, installs Atheris, then attempts `pip install -e .` from the library root and verifies imports requested by its `imports` input. Review its JSON result and installation errors. If the project documents another supported installer or has extra dependencies, use that documented method in the same `.venv`, then verify both `import atheris` and the selected target-module import with that environment's Python. Do not leave a placeholder environment after failed installation.

4. **Generate and tailor `fuzz.py`.** The included generator produces a safe one-argument-driver skeleton. Supply only values established by the source inspection. For example, after selecting a module and a one-argument parser, invoke it with a JSON request like this (replace values with runtime findings):

   ```sh
   printf '%s' '{"action":"generate","library":"/actual/library","module":"actual_package.parser","callable":"parse","argument":"text"}' \
     | python /app/environment/skills/current/scripts/fuzz_setup.py
   ```

   Supported `argument` forms are `text`, `bytes`, `json`, and `text_and_bytes`. For APIs with a different signature, edit the generated call deliberately using `FuzzedDataProvider` to construct the documented arguments. Keep the driver stateless.

   Every final driver must:

   - import `atheris` and install import-scoped instrumentation **before** importing the target module;
   - define `TestOneInput(data: bytes)` and consume fuzz data deterministically;
   - invoke the selected real API on every iteration (not merely stdlib parsing);
   - catch only malformed-input exceptions that are expected for that API, expanding the documented tuple when the project exposes its own parse errors;
   - call `atheris.Setup(sys.argv, TestOneInput)` and `atheris.Fuzz()` at module entry.

   Prefer importing a narrow submodule for slow packages. Do not replace an unavailable dependency or difficult target with a standard-library-only driver.

5. **Run exactly a ten-second smoke fuzz.** From every library root, capture libFuzzer stderr, while retaining logs even when the fuzzer finds a crash:

   ```sh
   while IFS= read -r lib; do
     ( cd "$lib" && .venv/bin/python fuzz.py -max_total_time=10 > /dev/null 2> fuzz.log ) || rc=$?
     : "${rc:=0}"; rc=0
   done < /app/libraries.txt
   ```

   `fuzz.log` must be produced by stderr redirection. Inspect it for initialization/coverage progress such as `INITED cov:` and `NEW cov:`, or for a fatal crash/reproducer diagnostic. A normal non-crashing run usually ends with `Done ... in 10 second(s)`. A process merely remaining alive for ten seconds without target coverage is not sufficient: correct import order or target selection and rerun.

6. **Validate the complete artifact set.** Run:

   ```sh
   printf '%s' '{"action":"validate","libraries_file":"/app/libraries.txt","expected_count":5}' \
     | python /app/environment/skills/current/scripts/fuzz_setup.py
   ```

   Treat failed validation as a checklist for manual repair. It intentionally accepts either normal completion or a crash diagnostic, but it does not claim that a driver has exercised a meaningful target API; that is established by the inspection, driver review, and coverage log.

## Helper interface

`scripts/fuzz_setup.py` reads one JSON object from stdin and emits one JSON object on stdout. It never prints subprocess chatter to stdout. Actions are `discover`, `analyze`, `provision`, `generate`, and `validate`; each action's fields and result are documented in the script's module docstring. It uses only the Python standard library and performs filesystem/package-manager effects only for the selected action.
