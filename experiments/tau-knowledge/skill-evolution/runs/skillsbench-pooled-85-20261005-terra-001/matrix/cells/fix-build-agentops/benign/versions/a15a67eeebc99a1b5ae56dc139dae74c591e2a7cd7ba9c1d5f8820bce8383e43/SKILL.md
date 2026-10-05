---
name: bugswarm-python-build-repair
description: Diagnose and repair a Python CI failure in an editable BugSwarm-style repository. Use this skill when the required deliverables are a factual failure analysis, one or more applicable unified-diff patch files, and the matching changes applied to the failed checkout.
---

# BugSwarm Python build repair

## Scope and guardrails

Work only in the editable failed checkout selected by the task, normally one
repository below `/home/github/build/failed/<repo>/<id>`. Do not inspect or use
passing snapshots, hidden solutions, golden patches, or repositories outside
that designated checkout as a source of a fix.

The required artifacts are all independent deliverables:

1. `/home/github/build/failed/failed_reasons.txt`, containing the observed
   diagnosis and plan;
2. `patch_{i}.diff` file(s) in the selected repository; and
3. source/configuration changes in that repository which are exactly represented
   by the patch file(s).

Do not evade a source failure by disabling tests, narrowing the CI matrix,
skipping a tox environment, or changing a workflow merely to avoid execution.
A configuration change is appropriate only when evidence establishes that the
configuration itself is defective (for example, incorrect dependency metadata
or a genuinely invalid command).

## Procedure

### 1. Establish the target and baseline

1. Discover the single editable checkout below `/home/github/build/failed` and
   set `REPO` to its absolute path. Do not guess `<repo>` or `<id>`.
2. Record the baseline with `git -C "$REPO" status --short` when it is a Git
   checkout. If unrelated pre-existing changes exist, preserve them and scope
   every later diff to the files changed for this repair. Do not use a destructive
   reset or checkout to erase unknown work.
3. Inspect the project’s build entry points and configuration: CI workflow files,
   tox configuration, `pyproject.toml`, setup metadata, dependency lock files,
   test configuration, and documented/reproduction scripts. Find the script or
   command that actually reproduces the declared CI build.

### 2. Reproduce and diagnose

1. Run the available CI reproduction entry point from the appropriate working
   directory, preserving its relevant environment and command structure. Apply
   the task timeout when available. Do not substitute an arbitrary `pytest`
   invocation for a build that actually invokes tox or another wrapper.
2. Save or carefully transcribe the command, interpreter/environment, first
   non-cascading failure, traceback/file location, and failing phase:
   environment setup, package installation, collection/import, or test execution.
3. Inspect the named source and its immediate callers/configuration. Correlate a
   version-specific error with the interpreter actually used; do not infer a
   version incompatibility merely because a modern feature exists somewhere in
   the tree.
4. Write `/home/github/build/failed/failed_reasons.txt` before making the final
   repair. It must state:
   - selected checkout and reproduction entry point/command;
   - observed first failure and relevant interpreter/dependency facts;
   - root cause, including whether it is code or build configuration;
   - minimal proposed files and behavioral rationale; and
   - validation command(s) to run after applying the patch.

Keep the report factual. If reproduction cannot run because a prerequisite is
missing, record the exact prerequisite and failure rather than fabricating a
root cause.

### 3. Make the smallest evidence-based repair

Change only the confirmed faulty code or configuration. Preserve behavior across
all versions that the project declares it supports. For a compatibility issue,
replace only the confirmed unsupported construct/API/dependency constraint with
an equivalent supported implementation; do not mechanically rewrite unrelated
uses.

Before generating artifacts, review the changed files and ensure no credentials,
logs, virtual environments, generated caches, or unrelated formatting changes
will enter a patch.

### 4. Create, validate, and apply patches

Prefer Git-generated patches from the actual original checkout state:

```sh
# Run from a clean baseline, or list only the intentional changed paths.
git -C "$REPO" diff --binary -- path/to/file1 path/to/file2 > "$REPO/patch_1.diff"
python3 scripts/validate_unified_diff.py <<JSON
{"patches":["$REPO/patch_1.diff"],"repo_root":"$REPO","check_apply":false}
JSON
```

A patch must have standard `---`/`+++` file headers, correctly counted `@@`
hunks, and prefixed context/removal/addition lines. Generate it from the real
file state rather than hand-calculating hunk ranges. Keep multiple patches
non-overlapping unless their ordering is explicitly necessary.

To honor the required ordering (write patch first, then apply it), generate the
patch from the proposed working-tree edit, then reverse that same patch without
discarding unrelated work and apply it forward again:

```sh
git -C "$REPO" apply -R -- "$REPO/patch_1.diff"
git -C "$REPO" apply --check -- "$REPO/patch_1.diff"
git -C "$REPO" apply -- "$REPO/patch_1.diff"
```

Only use this sequence when the patch contains solely the intentional repair
and the checkout state matches the patch’s preimage. If Git is unavailable or
the repository is not Git-managed, retain pristine copies of each changed file,
use `diff -u` to create the patch, validate against pristine files with the
standard patch tooling, then apply the saved patch rather than leaving a manual
edit as the final state.

Run the validator with `check_apply: true` only while the source tree is at the
patch preimage; it invokes `git apply --check` and does not modify files:

```sh
python3 scripts/validate_unified_diff.py <<JSON
{"patches":["$REPO/patch_1.diff"],"repo_root":"$REPO","check_apply":true}
JSON
```

After application, inspect `git -C "$REPO" diff --check` and verify the final
working-tree changes are the intended ones. Finally rerun the original CI
reproduction entry point, not a replacement test command. Update
`failed_reasons.txt` with the resulting validation status and any remaining
blocker. Confirm the report, every `patch_{i}.diff`, and applied changes exist
before completion.

## Patch validator interface

`scripts/validate_unified_diff.py` reads one JSON object from standard input and
emits one JSON object to standard output.

Input schema:

```json
{
  "patches": ["/absolute/or/relative/patch.diff"],
  "repo_root": "/optional/git/repository",
  "check_apply": false
}
```

`patches` must be a nonempty list of readable text patch paths. The script
checks unified-diff file/header/hunk structure and hunk line counts. It rejects
unsafe patch header paths. With `check_apply: true`, `repo_root` is required and
the script additionally runs `git -C REPO apply --check` on all supplied
patches. This checks applicability but never applies a patch. Output contains
`ok`, per-patch summaries, and errors; the process exits nonzero on failure.
