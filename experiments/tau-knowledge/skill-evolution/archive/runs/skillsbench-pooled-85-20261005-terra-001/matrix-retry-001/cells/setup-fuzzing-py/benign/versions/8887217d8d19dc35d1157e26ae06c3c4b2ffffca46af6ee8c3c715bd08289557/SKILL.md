---
name: python-atheris-library-fuzzing
description: Set up and validate 10-second coverage-guided Atheris/libFuzzer fuzzing for Python projects placed in a workspace. Use when a task requires a library listing, per-library testing notes, generated fuzz drivers, isolated .venv environments, and stderr fuzz logs.
---

# Python Atheris Library Fuzzing

Run the packaged controller from an environment that can create virtual environments and install project dependencies:

```bash
python3 scripts/setup_fuzzing.py <<'JSON'
{"root":"/app","expected_libraries":5,"run_builder_if_needed":true}
JSON
```

The controller reads project files at runtime and emits a JSON summary to stdout. It performs the requested artifacts and execution directly:

1. Discovers exactly the requested number of Python project directories below `root`, writes absolute unambiguous paths to `root/libraries.txt`, and fails rather than silently using an ambiguous set.
2. Uses AST inspection to select a concrete public, parser-like Python function in every project. It writes the selected module, function, signature, rationale, and alternate candidates to `<library>/notes_for_testing.txt`.
3. Generates `<library>/fuzz.py`. Each driver imports the selected actual target module inside `atheris.instrument_imports()`, has a `TestOneInput(bytes)` target, uses `FuzzedDataProvider`, explicitly instruments the target function, calls the selected target API, invokes `atheris.Setup`, and enters `atheris.Fuzz()`.
4. Creates `<library>/.venv`, installs declared requirements where present, installs the project editable, and installs Atheris. It verifies that Atheris and the selected target module import with that interpreter.
5. Runs each driver with `-max_total_time=10`, redirects libFuzzer stderr to `<library>/fuzz.log`, and validates coverage plus either normal completion or a crash/reproducer indication.

`run_builder_if_needed` permits the supplied workspace dataset builder to run only when no Python projects are initially discoverable. Set it to `false` when the workspace must never be initialized by `/app/build_dataset.sh`.

The script exits nonzero for a missing/ambiguous project set, no analyzable callable, installation/import failure, missing log, or a run without expected coverage and termination/crash markers. Review its JSON `failures` field and the affected `fuzz.log`; do not replace failed drivers with standard-library-only placeholders.

The selected target is based on static source inspection. If a project has no importable Python public function (for example, it is only a native extension), that is explicitly reported as unsupported instead of generating a driver that does not exercise the library.
