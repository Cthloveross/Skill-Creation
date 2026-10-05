---
name: maven-travis-build-repair
version: 1.0.0
description: Diagnose and minimally repair a Maven-based Java CI failure in a BugSwarm-style failed repository. Use when the task requires failed_reasons.txt, repository-relative unified patch files, and application of those patches under the original CI workflow.
---

# Maven/Travis Build Repair

## Scope and assumptions

Use this Skill for a repository beneath `/home/travis/build/failed/<repo>/<id>`. The repository name, identifier, build entry point, POM, JDK, and root cause are intentionally discovered at runtime; do not infer them from this Skill or from similarly named files.

The CI/reproduction script is the build contract. Repair source code or applicable project configuration so that contract succeeds. Do not modify a runner, Maven invocation, or CI configuration merely to bypass tests, compilation, verification, or another genuine failure. Keep changes limited to the discovered repository and create no patch for generated build output.

## Required deliverables

1. `/home/travis/build/failed/failed_reasons.txt`, containing the diagnosis and plan.
2. One or more `/home/travis/build/failed/<repo>/<id>/patch_{i}.diff` files in valid unified diff format.
3. The patch files actually applied to the repository.

## Procedure

### 1. Locate and preserve the target state

1. Enumerate directories directly under `/home/travis/build/failed` and identify the repository directory containing the supplied `<repo>/<id>` layout. Do not treat `failed_reasons.txt` as a repository.
2. Set `REPO` to that exact repository root. Record its absolute path in the notes.
3. Inspect `git status --short`, the top-level files, `.travis.yml` if present, executable scripts, Maven wrapper files, POM files, and any artifact-specific reproduction scripts. Preserve unrelated pre-existing changes; do not reset or clean a non-clean worktree.
4. Trace the command that actually runs in the available reproduction entry point. Record the exact JDK-selection commands, environment variables, working directory, Maven executable, POM selected by `-f`, goals, profiles, and flags. A visible `.travis.yml` is evidence but is not automatically authoritative if a reproduction wrapper runs something else.

### 2. Reproduce and diagnose

1. Run the active failing workflow from its required working directory, with the task timeout in mind, and retain its output in a log outside the source changes (for example, under `/tmp`). Do not substitute a convenient bare `mvn test` for the CI command.
2. Use `scripts/summarize_maven_log.py` on that log to find candidate diagnostics. The summary is triage only; read the surrounding raw log and source/configuration before deciding the cause.
3. Classify the earliest independent failure:
   - unresolved file/path or malformed POM before compilation;
   - dependency/plugin resolution or plugin configuration;
   - source or test compilation;
   - an executed test failure;
   - JDK/API/source-level incompatibility; or
   - a downstream consequence of an earlier module failure.
4. In multi-module output, begin with the earliest module and compiler/plugin diagnostic rather than fixing later `cannot find symbol` cascades. Confirm referenced paths with exact case-sensitive spelling. For Java compatibility, compare the active JDK and compiler source/target/release settings with the implicated language/API use.
5. Select the smallest source or configuration correction supported by the observed failure. Do not claim success before rerunning the original workflow.

### 3. Write `failed_reasons.txt`

Before changing the repository, write `/home/travis/build/failed/failed_reasons.txt`. It must be useful as the next-step handoff and include:

- target repository path and the active reproduction entry point;
- exact effective build command, relevant JDK/environment facts, and reproduction result;
- earliest root-cause evidence (module, phase/plugin, file and line where applicable), separated from cascading symptoms;
- whether the defect is code or build configuration and why;
- a minimal file-by-file repair plan; and
- intended validation: syntax/apply checks plus the same original workflow.

If reproduction is blocked (for example, unavailable external dependency or a missing script), say precisely what was observed, distinguish it from a source failure, and make no speculative fix. If a later edit or rerun changes the conclusion, update the notes to reflect the final diagnosis and validation result.

### 4. Produce patches before applying them

Create each `patch_{i}.diff` from the actual unmodified content it is intended to patch. Use paths relative to `REPO` and git-style labels such as `a/src/main/java/...` and `b/src/main/java/...`.

A safe approach is to copy each original target file to a temporary location, edit the candidate copy, and generate a unified diff with labels for the repository-relative paths. Save the resulting diff in `REPO/patch_1.diff` (and increment the number for separate logical changes). This avoids relying on a destructive reset to turn a working-tree edit back into a patch. Alternatively, if the worktree was confirmed clean, generate a path-limited `git diff` for only the intended files.

Each patch must have:

- `---` and `+++` file headers;
- valid `@@ -old[,count] +new[,count] @@` hunks;
- a leading space on every context line, `-` on removals, and `+` on additions;
- path labels that resolve from the repository root; and
- only the minimal logical change required by the diagnosis.

Do not include the notes file, build directories, logs, IDE files, dependency caches, or unrelated formatting in a repair patch. For new or removed files, use `/dev/null` on the absent side and ensure `git apply` supports the resulting patch.

Validate every patch before applying it:

```text
python3 scripts/validate_unified_diff.py <<'JSON'
{"path":"/absolute/path/to/patch_1.diff","repo_root":"/absolute/path/to/repository"}
JSON
git -C "$REPO" apply --check patch_1.diff
```

The helper verifies structure and hunk counts; `git apply --check` is the authoritative compatibility check against the actual tree. Resolve all reported errors by regenerating the patch from current content, not by hand-adjusting hunk counts without checking context.

### 5. Apply and verify

1. Apply only validated patches from the repository root with `git apply patch_1.diff` (in dependency order when there are several).
2. Inspect `git diff --check` and `git diff` to confirm the applied files equal the intended minimal repair. If a patch cannot apply, do not manually make the same edit and call it applied; correct/recreate the patch and apply it.
3. Re-run the same reproduction entry point and command identified in the notes. Record its exit result and relevant final output in `failed_reasons.txt`.
4. If the failure changes, diagnose the new earliest independent failure and repeat the patch process. Do not add workarounds that skip the remaining build phases.

## Helper scripts

### `scripts/summarize_maven_log.py`

Reads a Maven/CI log and emits JSON triage data. Invoke it by passing JSON on stdin:

```json
{"log_path":"/tmp/ci.log","context_lines":3,"max_diagnostics":12}
```

`log_path` is required. `context_lines` and `max_diagnostics` are optional positive integers. Output has `ok`, `error_lines`, `failure_markers`, `diagnostics`, and `tail`. Diagnostic entries contain a line number, matched text, and nearby log context. The script does not establish root cause and does not execute Maven.

### `scripts/validate_unified_diff.py`

Reads either `path` or `content` from JSON stdin and emits structural validation JSON:

```json
{"path":"/home/travis/build/failed/example/id/patch_1.diff","repo_root":"/home/travis/build/failed/example/id"}
```

When `repo_root` is supplied, non-`/dev/null` header paths are additionally checked for being relative, non-traversing paths. Output includes `valid`, `errors`, `warnings`, `files`, and `hunks`. It checks unified-diff header pairing, hunk syntax/counts, and legal hunk-line prefixes. It intentionally does not replace `git apply --check` or prove that a patch fixes the build.
