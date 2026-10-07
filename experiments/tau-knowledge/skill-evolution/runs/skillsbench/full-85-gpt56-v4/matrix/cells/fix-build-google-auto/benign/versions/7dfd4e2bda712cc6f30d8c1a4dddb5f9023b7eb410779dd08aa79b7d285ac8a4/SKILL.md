---
name: fix-java-maven-bugswarm-build
version: 1.0.0
description: Diagnose and repair a Java/Maven BugSwarm CI build in /home/travis/build/failed, document the observed root cause, produce valid minimal unified-diff patch files, apply them, and verify with the original reproduction entry point.
---

# Java/Maven BugSwarm build repair

Use this Skill when a task requires fixing the failing checkout under
`/home/travis/build/failed/<repo>/<id>`, writing `failed_reasons.txt`, creating
`patch_{i}.diff` files before application, and retaining the existing CI build
contract.

## Required outcome

1. Write `/home/travis/build/failed/failed_reasons.txt` with the observed
   failure analysis and a concrete repair plan.
2. Put one or more minimal, standard unified patches at
   `<repository-root>/patch_{i}.diff`.
3. Apply those patches to the failing checkout.
4. Re-run the same CI reproduction entry point and Maven invocation that
   originally failed. Do not replace it with a convenient standalone Maven
   command.

The repository, its CI scripts, Maven POM, modules, JDK, and fault must be
found at runtime. Never use a passing/reference checkout as the source of a
fix, and do not hardcode an artifact name, ID, source path, or expected error.

## Procedure

### 1. Discover the editable checkout and CI contract

Run the discovery helper from the installed Skill directory:

```sh
python3 scripts/discover_repositories.py <<'JSON'
{"base":"/home/travis/build/failed"}
JSON
```

Select the checkout that corresponds to the task, rather than a generated
subdirectory or a patch baseline. Inspect its top-level files, Git status, POM
files, `.travis.yml` if present, and executable/reproduction scripts. Trace
what command actually invokes Maven, including `-f`, profiles, properties,
JDK switching, and setup hooks. Existing reproduction scripts are evidence of
the contract; do not edit one merely to skip compilation, tests, or a failing
phase.

Run the identified failing workflow with its original environment and capture
its complete output to a file outside the checkout when practical. If it times
out or cannot start, retain its command, exit/timeout condition, and the
specific blocker as evidence. For Maven failures, identify the earliest
upstream error rather than downstream module failures caused by it.

### 2. Record the analysis before editing

Create `/home/travis/build/failed/failed_reasons.txt`. It must state:

- selected repository root and the reproduction entry point/actual Maven
  command;
- relevant JDK and build flags if the scripts expose them;
- observed failure phase, module, source/configuration location, and exact
  root diagnostic (or the reproducibility blocker);
- classification as source code, project configuration, dependency/environment
  setup, test, or CI-entry-point issue;
- the smallest planned in-scope change and why it addresses the upstream
  failure;
- intended patch file name(s) and verification command.

This is an evidence-based working note, not a generic checklist. Do not claim
success before the original workflow has actually passed.

### 3. Snapshot files that may change

Before editing each source/configuration file, snapshot it. Use a baseline
outside the repository so it cannot be confused with a project file. Paths are
repository-relative and must name only the files planned for the fix.

```sh
ROOT="/path/discovered/at/runtime"
BASELINE="/tmp/java-build-fix-baseline"
python3 scripts/snapshot_files.py <<JSON
{"root":"$ROOT","baseline":"$BASELINE","paths":["path/identified/during/diagnosis"]}
JSON
```

The helper records regular UTF-8/text or binary file baselines and a manifest.
For a new file, list its intended path before creating it; the manifest records
that it was absent. Do not snapshot build output directories, downloaded
artifacts, logs, or the patch files themselves.

Make only the targeted source or POM/configuration edits justified by the log.
Avoid broad version upgrades, deleting tests, changing the CI runner to skip
work, or papering over dependent-module errors.

### 4. Generate, validate, and apply the patch

After making the proposed edits in the working tree, generate a patch from the
snapshot and apply it back onto the baseline with the helper. This ensures that
the required patch exists *before* it is applied. The helper emits GNU unified
diffs with `--- a/...` and `+++ b/...` labels, restores the selected files to
the snapshot, uses `git apply --check`, then applies the saved patch.

```sh
python3 scripts/make_and_apply_patch.py <<JSON
{
  "root":"$ROOT",
  "baseline":"$BASELINE",
  "paths":["path/identified/during/diagnosis"],
  "patch":"$ROOT/patch_1.diff",
  "apply":true
}
JSON
```

Its JSON result must have `ok: true` and `applied: true`. The patch is valid
only for the baseline captured before the edit. Keep logical changes separate
in `patch_1.diff`, `patch_2.diff`, and so on when they are independently
justified; use a fresh baseline/target list per patch. The patch must contain
only intended source/configuration changes, with paths relative to the actual
repository root.

If the helper reports an unsupported condition (for example, an unsafe path,
missing snapshot, no content change, or unavailable `git`), stop and correct
that condition. Do not hand-edit hunk counts. If a binary file truly must be
changed, use Git's binary patch facilities and explicitly validate application;
ordinary unified text diffs do not represent binary edits.

### 5. Verify the repair

Confirm the intended files are changed and the patch is applicable to a clean
baseline (`git apply --check patch_1.diff` is also a useful independent check).
Then run exactly the reproduction script/CI command recorded in
`failed_reasons.txt`, under its original JDK and flags. Inspect the exit code
and final log, including later modules when `--fail-at-end` is used. Update the
notes with the actual verification result and any remaining blocker.

A successful ad-hoc `mvn test` does not substitute for the original workflow.
If the original workflow still fails for a distinct upstream issue, repeat the
analysis with another minimal patch rather than modifying the runner or
claiming the repair is complete.

## Helper input/output schemas

All packaged scripts read one JSON object from standard input and write one
JSON object to standard output. A nonzero exit and `ok: false` indicates an
observable failure; inspect the returned `error`/`stderr` fields.

- `discover_repositories.py`: input `{"base": "/home/travis/build/failed"}`.
  Output contains `repositories` (directories containing `.git`) and relevant
  top-level CI/build candidate files.
- `snapshot_files.py`: input `{"root": string, "baseline": string,
  "paths": [repository_relative_path, ...]}`. Output contains the absolute
  baseline manifest path and the paths/snapshot states.
- `make_and_apply_patch.py`: input `{"root": string, "baseline": string,
  "paths": [repository_relative_path, ...], "patch": string,
  "apply": boolean}`. It writes the requested patch and returns patch
  metadata. With `apply: true`, it validates and applies it. With
  `apply: false`, it only creates the patch and leaves the proposed working
  edits in place.
