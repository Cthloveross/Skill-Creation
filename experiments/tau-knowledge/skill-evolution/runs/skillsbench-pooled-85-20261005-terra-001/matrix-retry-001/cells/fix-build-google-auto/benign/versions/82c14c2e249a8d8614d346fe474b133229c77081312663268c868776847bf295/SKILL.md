---
name: diagnose-and-patch-java-ci-build
summary: Diagnose a Maven/Java CI failure in a BugSwarm-style failed workspace, document the root cause, create minimal valid unified-diff patch files, and apply them without weakening the active CI contract.
---

# Diagnose and patch a Java CI build

Use this Skill when a Java repository under `/home/travis/build/failed/<repo>/<id>` must be repaired by first writing `/home/travis/build/failed/failed_reasons.txt`, then creating `patch_{i}.diff` files at the repository root, and finally applying those patches.

## Inputs and helper scripts

The executor must inspect the actual workspace at runtime. Do not infer a repository name, module, failing source line, Maven command, Java version, or patch content from this Skill.

`scripts/inspect_build_context.py` accepts JSON on stdin:

```json
{"root":"/home/travis/build/failed"}
```

It emits JSON listing candidate artifact directories and likely CI/build entry-point and Maven configuration files. It is an inventory aid only; it does not establish which command is authoritative and does not run a build.

`scripts/validate_unified_diff.py` accepts:

```json
{"patches":["/absolute/or/relative/patch_1.diff"],"repository":"/home/travis/build/failed/<repo>/<id>"}
```

It emits one result per patch, including syntax errors, malformed hunk counts, unsafe paths, and whether `git apply --check` accepted the patch when a repository is supplied. It never applies a patch. A nonempty `errors` list or `git_apply_check.ok: false` means the patch must be corrected before application.

## Required workflow

1. **Locate and preserve the editable artifact.** Inspect `/home/travis/build/failed` and identify the actual `<repo>/<id>` directory. Record `pwd`, `git status --short`, top-level files, and the module layout. Do not use any hidden/reference/passing checkout as a source for a fix. Do not discard pre-existing changes; account for them when constructing a patch.

2. **Determine the active build contract.** Inspect available reproduction scripts, CI configuration, wrappers, `pom.xml` files, Maven profiles, and environment setup. Trace the script/command that the reproduction environment actually executes. Record the exact command, working directory, POM selected with `-f` if any, Maven flags/properties, active Java/JDK selection, and relevant environment variables. A `.travis.yml` file alone is not necessarily the executed contract.

3. **Reproduce and diagnose.** Run the authoritative workflow with the task's supplied timeout. Save or capture the full output. Identify the earliest originating error, its Maven lifecycle phase and plugin, and its source/configuration location. In a multi-module reactor, distinguish the first failed module from downstream missing-symbol cascades. Also distinguish startup/path failures from dependency resolution, compilation, test, and plugin failures.

4. **Write the required analysis before changing the repository.** Create `/home/travis/build/failed/failed_reasons.txt`. It must state:
   - artifact path and the authoritative reproduction command;
   - observed JDK/runtime and relevant Maven/POM/profile settings;
   - failure phase, first root-cause diagnostic, affected module/file/location, and supporting log evidence;
   - whether the cause is source code or project configuration;
   - a minimal change plan and why it preserves (rather than bypasses) the CI contract;
   - intended patch file names and target paths.

   If the failure cannot be reproduced or the command is ambiguous, document the exact missing evidence and resolve the entry point before patching. Do not claim success based only on a different Maven invocation.

5. **Prepare a minimal patch without changing CI to hide the error.** Make only targeted source or build-configuration changes that address the observed root cause. Do not alter CI/reproduction scripts merely to skip tests, compilation, checks, or modules. Avoid broad upgrades, unrelated formatting, generated output, lock/cache files, and whole-file replacement.

   To honor the required ordering, preserve an original copy of every intended target outside the repository, edit working copies outside the repository, and generate patches before application. For example, for each target path, use `diff -u` with explicit repository-relative labels `a/<path>` and `b/<path>` (or an equivalent `git diff --no-index` invocation) to write `patch_1.diff`, `patch_2.diff`, etc. at the repository root. The patches must contain only the planned changes. Do not use absolute paths or `..` path components in diff headers.

   Each patch must be standard unified diff text with `---` and `+++` headers, valid `@@ ... @@` hunk headers, correctly prefixed context/deletion/addition lines, and paths relative to the repository root. Use adequate unchanged context. A patch may cover multiple related files, but separate independent fixes into separately named `patch_{i}.diff` files.

6. **Validate and apply.** Run the packaged diff validator against every patch and inspect its JSON. Also use `git diff --check` on the proposed result where applicable. Correct every validation error. From the repository root, use `git apply --check patch_{i}.diff` for every patch first, then apply them in numeric order with `git apply patch_{i}.diff`. Do not manually reimplement patch changes after validation; the applied repository state must result from the declared patch files.

7. **Verify end-to-end.** Confirm the expected files changed with `git diff` and rerun the same authoritative reproduction workflow, under the same JDK and relevant environment. Report the command and outcome. If it still fails, diagnose the newly observed earliest root cause; do not paper over it by modifying the runner or changing the verification command.

## Failure handling

- If a referenced build file or POM is missing, verify exact case-sensitive paths and trace where the active command obtains it before deciding on a fix.
- If dependency/network infrastructure fails before project code is reached, record that separately and do not fabricate a source-level diagnosis.
- If a patch cannot apply cleanly, regenerate it from the actual unmodified target state with sufficient context; never force application.
- If a required target lies outside the editable artifact or the evidence does not support a safe change, leave the repository unchanged after writing an explicit `failed_reasons.txt` describing the blocker.

## Completion checklist

Before completion, ensure `/home/travis/build/failed/failed_reasons.txt` exists, every proposed change is represented in repository-root `patch_{i}.diff` files, each patch passes structural validation and `git apply --check`, the patches have been applied, and the original CI/reproduction command was used for final verification.
