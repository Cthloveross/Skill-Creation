---
name: setup-python-atheris-fuzzing
description: Set up and smoke-test coverage-guided Atheris/libFuzzer drivers for a fixed set of Python library directories. Use when a workspace requires libraries.txt, per-library testing notes, isolated virtual environments, fuzz.py drivers, and captured fuzz logs.
---

# Python Atheris fuzzing setup

## Scope and runtime inputs

Use this Skill in the supplied workspace. Discover the libraries at runtime; do not assume their names, package names, layouts, dependencies, or public APIs. The task requires exactly the library directories specified by its instructions (five in this task). Write paths in the representation requested by the task, and ensure every listed path resolves from `/app`.

The packaged scripts are helpers, not a replacement for library-specific analysis. They receive JSON on stdin and print JSON to stdout. Run them with the Python already available in the workspace (they use only the standard library).

## Procedure

1. **Prepare and discover.** Inspect `/app/build_dataset.sh` first when present, since it may create or identify the source libraries. Run it if necessary and inspect `/app` afterward. Identify the five library roots, excluding infrastructure directories/files such as `environment`, a Skill directory, virtual environments, caches, and task helper files. Confirm each candidate has Python project evidence (`pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, or package/test directories).

   Create `/app/libraries.txt` with one absolute library-root path per line unless the task explicitly requests another path convention. It must contain exactly the five intended library directories and no headings or commentary. Validate it with `scripts/validate_setup.py` once artifacts exist.

2. **Analyze every library before generating a driver.** For each path in `libraries.txt`, read its packaging metadata, source tree, README/API documentation, and focused tests. `scripts/inspect_library.py` can produce a quick AST-based inventory, but inspect its candidates manually because it cannot know runtime behavior.

   Select a concrete, importable public entry point that accepts untrusted structured data and reaches meaningful library logic. Prefer parsers, loaders, decoders, deserializers, format/string parsers, and shallow public APIs. Avoid an API needing network, database, a daemon, user interaction, or persistent writes. For slow frameworks import the narrow target submodule rather than the package root.

   Write `<library>/notes_for_testing.txt`. It must name the actual module and callable selected, state why it is valuable, describe the fuzzed input type (`str`, `bytes`, or JSON-like object), identify expected exception classes/invalid-input behavior, and record the installation approach inferred from project metadata. These notes must be library-specific and must agree with `fuzz.py`.

3. **Create isolated environments and install the actual projects.** For each library root, create `<library>/.venv` using its supported Python/package workflow. Install the project and its documented dependencies in that environment, then install `atheris`. A typical editable install is appropriate only where the project metadata supports it; otherwise use its documented installation command. Verify inside that exact environment that both `atheris` and the selected target module import.

   Do not leave a placeholder venv. If installation fails, inspect metadata and build errors, install the documented build/runtime prerequisites, and retry. Do not silently substitute a standard-library target.

4. **Generate each driver.** Use `scripts/write_driver.py` to emit a baseline driver after choosing the real target. Its `module` and `callable` must match the notes and the installed library. For example, from a library root:

   ```sh
   printf '%s' '{"library_dir":"/app/LIB","module":"package.parser","callable":"parse","input_kind":"str"}' \
     | python /app/environment/skills/current/scripts/write_driver.py
   ```

   Supported `input_kind` values are `str`, `bytes`, and `json_dict`. The helper writes `<library_dir>/fuzz.py` and returns its path. Review the generated file and adjust its target adapter only when required by the chosen API (for example, use a valid fixed required argument or construct a documented object). Keep raw fuzz-derived content as a main argument and call the real target API inside `TestOneInput` on every iteration.

   A valid driver must:
   - import `atheris` first;
   - import the target module inside `atheris.instrument_imports()`;
   - define a bytes-accepting `TestOneInput(data)`;
   - use `atheris.FuzzedDataProvider(data)` to derive the target input;
   - invoke the selected library callable, catching only expected malformed-input exceptions (a documented broad `Exception` catch is acceptable where the library hierarchy is unclear, but never catch `BaseException`);
   - use `@atheris.instrument_func` on `TestOneInput`;
   - call `atheris.Setup(sys.argv, TestOneInput)` and then `atheris.Fuzz()`.

   Never replace the target invocation with `json.loads`, another standard-library parser, or a no-op. Native-only coverage can be limited, but the driver must still instrument the Python import scope and fuzz the actual API.

5. **Run and capture a ten-second smoke fuzz.** From each library root, run its environment's interpreter with a libFuzzer ten-second maximum and redirect **stderr**:

   ```sh
   .venv/bin/python fuzz.py -max_total_time=10 2> fuzz.log
   ```

   Preserve `fuzz.log` even if a finding causes a nonzero process status. Inspect it. A healthy budget-exhaustion run normally contains libFuzzer startup/coverage events (such as `INITED`, `NEW`, or periodic status) and a `Done ... second(s)` line. A fatal crash and reproducer is a valid fuzzing finding rather than evidence that the driver was not run. If the process exits immediately, imports fail, logs have no fuzzer activity, or coverage is absent, repair the environment, import order, target adapter, or driver and rerun. Do not merely redirect stdout.

6. **Validate final artifacts.** Run the validator below after all libraries have been processed. It checks only observable structural obligations; additionally manually compare notes, chosen APIs, and log contents.

   ```sh
   printf '%s' '{"libraries_file":"/app/libraries.txt","expected_count":5,"require_logs":true}' \
     | python /app/environment/skills/current/scripts/validate_setup.py
   ```

   The result has `ok`, `errors`, and per-library reports. Resolve every reported error. Final required outputs are `/app/libraries.txt`, and in every listed library: `notes_for_testing.txt`, `.venv`, `fuzz.py`, and `fuzz.log`.

## Helper I/O

- `inspect_library.py`: input `{"library_dir":"/absolute/path"}`; output contains packaging files, Python files, AST-discovered candidate functions, and errors. It never changes the library.
- `write_driver.py`: input `{"library_dir":"...","module":"pkg.mod","callable":"parse.or.dotted","input_kind":"str|bytes|json_dict"}`; output says where it wrote the driver. It rejects invalid values.
- `validate_setup.py`: input `{"libraries_file":"/app/libraries.txt","expected_count":5,"require_logs":true}`; output reports structural and source-level checks. It does not execute fuzzers.
