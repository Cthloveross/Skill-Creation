---
name: python-atheris-continuous-fuzzing
summary: Set up and validate Atheris/libFuzzer fuzzing for a fixed set of local Python projects. Use when a task requires a library list, per-project target notes, .venv environments, runnable fuzz.py drivers, and captured short-run fuzz logs.
---

# Python Atheris Continuous Fuzzing

This Skill creates real, coverage-guided fuzzing artifacts for local Python libraries. It does not substitute a standard-library-only driver for a target-library driver.

## Inputs and helper interfaces

All packaged helpers use JSON on stdin and emit a JSON result on stdout.

* `scripts/discover_projects.py`: `{ "root": "/app", "expected_count": 5, "write_libraries_file": "/app/libraries.txt" }`. It discovers immediate Python project directories, optionally writes absolute paths one per line, and reports source/test files and parser-like candidate definitions.
* `scripts/generate_driver.py`: `{ "library_root": "/app/project", "module": "package.parser", "callable": "loads", "arguments": ["text"], "output": "/app/project/fuzz.py" }`. It writes an Atheris driver. `arguments` may contain `text`, `bytes`, `int`, `float`, `bool`, or `json_value`.
* `scripts/validate_artifacts.py`: `{ "libraries_file": "/app/libraries.txt", "expected_count": 5 }`. It performs structural checks and reports per-library diagnostics. It does not claim that fuzzing was run merely because files exist.

Run helpers with the selected environment's normal Python or another available Python with the standard library. They have no third-party dependencies.

## Workflow

1. **Materialize and inventory projects.** Inspect `/app` first. If the task environment supplies a dataset-building script and the five project directories are not yet present, inspect that script and use it only to materialize the task dataset, then inventory again. Do not list unrelated directories, virtual environments, or the Skill package itself. Run `discover_projects.py` with the required count and write `/app/libraries.txt`. The list must contain exactly five unambiguous absolute project-directory paths, one per line. A count mismatch is a prerequisite failure to resolve before continuing.

2. **Analyze every listed library before writing its driver.** Read its `pyproject.toml`, `setup.py`, `setup.cfg`, requirement/lock files, package `__init__.py`, relevant implementation modules, and focused tests. Choose one concrete public input-facing callable that can be invoked without external services. Prefer parsing, loading, decoding, formatting, validation, or deserialization APIs accepting text, bytes, or a simple structured value. Avoid targets needing databases, sockets, subprocesses, GUI state, or substantial framework initialization.

   Create `<library>/notes_for_testing.txt` for every library. Include the package/module, exact callable, signature/call pattern, chosen fuzzed argument kinds, why it is a useful target, expected malformed-input exceptions, any setup constraints, and the command/result of the quick run once known. This is target-specific evidence, not a generic checklist.

3. **Create the isolated environment.** For each root, use that root's `.venv`; for example create it with the selected compatible interpreter and install according to the project metadata. Install the project itself (normally editable installation is appropriate for a local project), all declared runtime/test dependencies required for import, and `atheris` in that same environment. Respect the project's declared Python-version and package-manager constraints rather than assuming a lockfile format or tool. Verify both the target module and `atheris` import using `<library>/.venv/bin/python` before running fuzzing. If native dependencies cannot be installed, record the concrete blocker rather than creating a placeholder driver/environment.

4. **Generate and review `fuzz.py`.** Use `generate_driver.py` only after determining a valid module, callable, and argument pattern from the notes. It produces a driver with `TestOneInput(data: bytes)`, `FuzzedDataProvider`, import-scoped instrumentation before the target import, explicit fuzz-target instrumentation, `atheris.Setup(sys.argv, TestOneInput)`, and `atheris.Fuzz()`.

   Review the generated call against the actual signature. If the public API needs a supported simple argument combination, change the generator input accordingly. If it needs nontrivial construction, hand-edit the generated `TestOneInput` while preserving the required Atheris structure and keeping construction deterministic and in-process. The driver must import and call the actual selected library API inside `TestOneInput`; importing only a standard module is invalid. Replace the default broad expected-input exception handling with a narrow documented tuple where practical. Do not catch `BaseException`, `SystemExit`, or `KeyboardInterrupt`.

5. **Run and log each driver.** From each library root, invoke its environment's Python with a real libFuzzer 10-second budget, e.g. `./.venv/bin/python fuzz.py -max_total_time=10 2> fuzz.log`. Do not redirect only stdout: libFuzzer operational output is on stderr. Preserve `fuzz.log` even if the process terminates for a discovered crash; a crash and its reproducer are findings, not evidence that no fuzzing occurred. For ordinary completion, inspect for startup/coverage/status and a completion marker. A log with no coverage progression warrants investigation of import order, selected module, and driver setup.

6. **Validate deliverables.** Run `validate_artifacts.py`, inspect each reported issue, and manually inspect logs. Successful ordinary runs normally contain libFuzzer initialization plus `NEW`/`pulse` coverage or a `Done` line. A fatal crash diagnostic/reproducer is also a meaningful run outcome. Update each notes file with what actually ran and any crash or setup limitation.

## Failure handling

Do not fabricate a target, a successful import, coverage, or a completed run. If a library has no viable one-argument public entry point, document the API constraint and implement a deterministic adapter only when it still calls a real library public API. If installation fails, retain notes and the specific diagnostic, but resolve it before representing Step 4 or Step 5 as complete. Never reuse one library's module/callable in another library's fuzz driver.
