---
name: fix-python-build-bugswarm
description: >-
  Diagnose and repair a failing Python CI build inside a BugSwarm artifact
  (tox / pytest / GitHub Actions), then persist the three required deliverables:
  a root-cause analysis note, unified-diff patch files, and the applied source
  changes. Use when the task hands you an editable failed repository under
  /home/github/build/failed/<repo>/<id> and asks you to write failed_reasons.txt,
  write patch_{i}.diff files in git/GNU unified-diff format, and apply the fix so
  the original CI build command passes. The Skill supplies helper scripts for
  locating the repo, reproducing the build, generating/validating diffs, and
  checking that every required artifact exists; the diagnosis and the actual code
  fix are performed by the executor following the method below.
---

# Fix a failing Python build in a BugSwarm artifact

## What the task requires

The public task (see the opening text in the live inputs) has three steps and
three independently-verified deliverables:

1. **Analysis** — write your diagnosis and plan to
   `/home/github/build/failed/failed_reasons.txt`.
2. **Patches** — write the proposed changes as standard unified-diff files to
   `/home/github/build/failed/<repo>/<id>/patch_{i}.diff` (one or more,
   numbered from 1). They must be parseable/applicable by `git apply` and GNU
   `patch`.
3. **Applied fix** — apply those diffs so the source tree is actually modified
   and the original CI build command passes.

All three are checked. Passing the build alone is **not** sufficient if the
`patch_*.diff` files are missing, and standalone patches are not sufficient if
the source is not actually modified. Verify every artifact exists before you
finish (`scripts/check_outputs.py`).

## Hard constraints (from the frozen background)

- Work **only** in the editable failed repo the task designates. Do **not** look
  for or copy a passing snapshot, hidden/golden patch, or reference solution as
  the source of a fix. Derive the fix from the observed error.
- Fix the **code or project configuration**, not the CI contract. Do not edit
  the build/tox/workflow scripts to skip, disable, or remove failing tests or to
  drop Python versions from the matrix. The code must pass under the existing
  build configuration.
- Make the **smallest** change that follows the evidence. For a confirmed
  version-incompatible construct, make it backward-compatible across the
  project's supported interpreter range; search for semantically equivalent
  occurrences on the same failing path, but do not perform a broad mechanical
  rewrite of guarded or unrelated code.
- Diagnose from the **first failing step/traceback**. Later errors are often
  cascading consequences. Distinguish the layer: tox env creation (config/
  interpreter), pytest collection (import/syntax → usually code compatibility),
  or pytest execution (logic bug).
- Do not assume the cause. The background lists example version-sensitive
  constructs (walrus `:=`, `match`, `typing.TypeAlias`, 3.12 f-strings, new
  stdlib APIs) only as illustrations — identify the actual interpreter, failing
  phase, source construct or dependency named in **this** build's logs.

## Method

Run helpers with: `echo '<json>' | python3 scripts/<name>.py`. Each reads one
JSON object on stdin and prints one JSON object on stdout. Paths default to the
task layout but can be overridden. These scripts never edit source and never
skip tests; they only locate, reproduce, generate diffs, and validate.

1. **Locate the repo.** `scripts/locate_repo.py` with `{}` returns the
   `<repo>/<id>` directory under `/home/github/build/failed`, its project
   markers (`tox.ini`, `pyproject.toml`, `setup.py`, `setup.cfg`, `.github/
   workflows`), and whether it is a git checkout. Use the returned `path` as
   `<repo>/<id>` for every later step.

2. **Understand the build contract.** Inspect `tox.ini`, `pyproject.toml`,
   `setup.py/cfg`, and `.github/workflows/*.yml` in that path. Identify the
   interpreter version(s) and the exact command CI runs (e.g. `tox`, `tox -e
   pyXY`, `pytest ...`).

3. **Reproduce the failure.** `scripts/reproduce.py` discovers the BugSwarm
   reproduction entry points (e.g. `run_failed.sh` and similar under
   `/usr/local/bin`, `/home/github/build`, `/home/github`) and, with
   `{"auto": true}`, runs the discovered failed-build script, redirecting output
   to a log and returning the exit code, the log path, and the tail. Reproduce
   with the **real CI entry point** (which may invoke tox with extra config) —
   do not substitute a different ad-hoc command. If no script is found, run the
   CI command you identified in step 2 yourself and read the first failing
   traceback. Capture: interpreter version, failing phase, file:line, and the
   exact error (`SyntaxError`, `ImportError`, `TypeError`, `AttributeError`,
   assertion, dependency metadata, missing path, etc.).

4. **Diagnose and write `failed_reasons.txt`.** Correlate the first failing
   traceback with the interpreter/dependency versions. State the root cause,
   the layer, the affected file(s)/line(s), and the minimal planned fix. Write
   this to `/home/github/build/failed/failed_reasons.txt` (not inside the repo).

5. **Apply the minimal source fix.** Edit the source file(s) in
   `<repo>/<id>` to make the construct/behavior compatible with the supported
   interpreter range while preserving intended behavior. Do not touch build
   scripts, tox config to skip tests, or the version matrix.

6. **Generate the patch files from the real diff.** With the edits in place,
   run `scripts/gen_patches.py` `{"repo": "<repo>/<id>"}`. In a git checkout it
   writes one `patch_{i}.diff` per changed file (git-style headers `--- a/...`
   `+++ b/...`, `@@` hunks) generated from the actual HEAD→working-tree diff, so
   the diffs match the real file state. It leaves your applied changes in place.
   For a non-git tree, keep an untouched copy of each original file and pass
   `{"repo": "<repo>/<id>", "originals": "<backup_dir>"}` so diffs are produced
   with `difflib` against the originals. Never hand-write hunk headers or counts.

7. **Validate the patches.** `gen_patches.py` already checks each patch with a
   reverse `git apply --check -R` (confirms the forward patch applies cleanly to
   HEAD and matches your applied changes). You can re-check anytime with
   `scripts/validate_patches.py` `{"repo": "<repo>/<id>"}`, which verifies every
   `patch_*.diff` is non-empty, has the `---`/`+++`/`@@` structure, and is
   consistent with the current tree. Fix any malformed diff before continuing.

8. **Re-run the original CI command** (repeat step 3) across the relevant
   environment(s) and confirm the build now passes end-to-end under the exact
   original conditions. If it still fails, read the new first failure and
   iterate from step 4 — do not broaden the patch blindly.

9. **Confirm all deliverables exist.** Run `scripts/check_outputs.py`
   `{"repo": "<repo>/<id>"}`. It verifies `failed_reasons.txt` is present and
   non-empty, at least one parseable `patch_*.diff` exists in the repo, and the
   source tree actually carries uncommitted changes (the fix is applied). Only
   finish when it reports `ok: true`.

## Interpreting results and failure modes

- `locate_repo.py` returns `candidates: []` → the failed repo is not where
  expected; widen the search `base` or inspect `/home/github/build` manually.
- `reproduce.py` returns `scripts: []` → no reproduction script; use the CI
  command from the project config directly. A non-zero exit before the fix is
  the failure you must diagnose; a non-zero exit after the fix means the build
  still fails — inspect the log tail, read more of the log via the terminal in
  sections, and iterate.
- `gen_patches.py` reporting `applies: false` for a patch means the working tree
  and HEAD disagree with what was written (e.g. you edited then reverted, or the
  tree is not git): regenerate after re-applying your edits, or supply
  `originals`.
- `check_outputs.py` `ok: false` lists exactly which deliverable is missing;
  address that specific item rather than redoing everything.

The scripts recommend and validate; they do not perform the diagnosis or decide
the fix. Keep the correction scoped to the confirmed root cause.
