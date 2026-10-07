---
name: fix-python-ci-build-with-persisted-patches
description: Diagnose and minimally fix a failing Python CI/BugSwarm repository when the task requires a written root-cause analysis, valid unified-diff patch artifact(s), and those patches applied to the editable source tree.
---

# Fix Python CI builds and persist reproducible patches

Use this Skill for build-repair tasks whose repository is beneath a supplied failed-workspace root and which explicitly require an analysis file, `patch_*.diff` artifacts, and applied source changes.

## Inputs and required outputs

Read the task request for the failed-workspace root, repository layout, exact analysis-file path, required patch-file naming, and any declared build timeout. Do not assume a particular repository name, interpreter, test runner, or CI provider.

For the supplied task, the executor must produce all of the following:

1. An analysis and repair plan at the requested analysis path (for example, `<failed-root>/failed_reasons.txt`).
2. One or more standard unified-diff patch files inside the editable repository, named exactly as requested (for example, `patch_1.diff`).
3. Source/configuration edits in the repository which are the result of applying those patch files.

The patch artifact and applied source edit are separate obligations. Do not put the patch only in an analysis file or leave changes applied without saving a patch.

## Method

1. **Locate the editable repository.** Inspect the immediate descendants of the declared failed-workspace root and identify the repository at `<failed-root>/<repo>/<id>`. Confirm its root using its project files and, where available, `git rev-parse --show-toplevel`. Never retrieve, compare against, or copy a passing snapshot, hidden patch, or reference solution.
2. **Inspect the CI contract.** Read the available workflow and build entry points before choosing a command: CI YAML, `tox.ini`, `pyproject.toml`, `setup.cfg`, `setup.py`, Makefiles, and repository documentation. Locate the exact reproduction script if the artifact supplies one. Note the selected interpreter, environment, dependency install process, and test command.
3. **Reproduce the original failing workflow.** Run the actual available entry point from the repository with the needed documented environment variables. Capture the first non-cascading failure, including command, exit status, interpreter/environment, traceback, file, and line. Do not substitute a convenient direct pytest invocation for a tox/CI entry point that performs additional setup.
4. **Classify and investigate.** Distinguish environment creation/dependency resolution failures, collection/import/syntax failures, and test-execution failures. Trace the first concrete failure to a supported cause. For a version issue, establish both the interpreter/dependency version and the incompatible construct/API. Search only for semantically equivalent occurrences on the confirmed affected path; avoid broad speculative rewrites.
5. **Write the analysis file before editing.** State: repository and invoked entry point; first observed failure and evidence; whether the fault is source code, dependency/build configuration, or infrastructure; a minimal repair plan; and validation commands. If reproduction is blocked by a missing external prerequisite, record the exact blocker and only make a change when repository evidence establishes a fix.
6. **Make a minimal contract-preserving repair.** Do not bypass the failure by skipping tests, weakening assertions, removing supported interpreter environments, or modifying CI merely to avoid execution. Change the narrowest source or legitimate configuration layer justified by the evidence.
7. **Create a patch from the actual pre-edit state.** After edits, generate a git-style patch against the current repository baseline, for example with `git diff -- <edited paths> > patch_1.diff`. Ensure the output contains `---`/`+++` headers and `@@` hunks. Do not include generated build products, virtual environments, logs, or unrelated local changes. If git baseline operations are unavailable, create a `diff -u` patch from a saved original copy and use paths that apply from the repository root.
8. **Ensure the patch was applied, not merely generated.** A reliable sequence is: edit files, generate the patch, validate it, restore only the edited tracked files to their original contents, then apply `patch_1.diff` from the repository root. If the repository state must be preserved for safety, first copy the patch outside the edited paths, then use `git apply --check patch_1.diff` followed by `git apply patch_1.diff`. Confirm `git diff --check` and inspect `git diff` afterward. Do not accidentally include `patch_1.diff` itself in the patch.
9. **Validate.** Run `python3 scripts/validate_patch.py` from this Skill with the repository and every patch path. Then rerun the original CI/build entry point, or all feasible affected CI environments, after the patch is applied. Record the exact validation result in the analysis file. If unavailable interpreters or network services prevent full execution, document that limitation honestly while still performing syntax/diff checks and any runnable relevant checks.
10. **Final artifact check.** Verify the analysis file exists at its requested location, each patch exists under the repository with the requested name, each patch is nonempty and parseable, and the edited files remain changed/applied in the source tree.

## Patch validation helper

`scripts/validate_patch.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{"repo": "/absolute/repository/root", "patches": ["/absolute/repository/root/patch_1.diff"]}
```

`repo` is optional; when provided and `git` is available, the helper also runs `git apply --check` for each patch. `patches` must be a nonempty list of paths. Output has `ok`, `patches`, and `errors`; each patch result includes structural findings and optional git applicability findings. A nonzero exit status means validation failed.

Example:

```sh
printf '%s\n' '{"repo":"/home/github/build/failed/REPO/ID","patches":["/home/github/build/failed/REPO/ID/patch_1.diff"]}' \
  | python3 /app/environment/skills/current/scripts/validate_patch.py
```

A successful structural check does not prove semantic correctness; always use the original CI entry point for behavioral validation.
