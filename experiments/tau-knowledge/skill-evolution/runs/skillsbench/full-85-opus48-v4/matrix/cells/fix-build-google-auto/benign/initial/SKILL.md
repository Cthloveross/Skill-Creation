---
name: bugswarm-java-maven-build-fix
description: >
  Diagnose and fix a failing BugSwarm Java/Maven build, then emit the three required
  deliverables: an analysis note at /home/travis/build/failed/failed_reasons.txt,
  one or more standard unified-diff patch files (patch_1.diff, patch_2.diff, ...) inside
  the editable repository directory, and the same fixes applied to the source tree so the
  build passes under the original CI invocation. Use when a task gives a repository under
  /home/travis/build/failed/<repo>/<id> and asks to analyze, patch, and fix build errors.
---

# BugSwarm Java/Maven Build Fix

This Skill drives a disciplined build-repair loop. It does **not** contain the fix for any
particular artifact — the root cause must be read from the actual build log and filesystem
of the current container. The scripts automate the repetitive, error-prone mechanics
(locating the editable repo, discovering the real CI command, running the build, generating
valid unified diffs, validating them, and proving they apply cleanly).

## Required deliverables (the output contract)

The task asks for exactly three things. Produce all of them:

1. **Analysis note**: `/home/travis/build/failed/failed_reasons.txt` describing the
   observed error, the failing Maven phase/module, whether it is a code error or a
   configuration error, and the planned minimal fix.
2. **Patch files**: `/home/travis/build/failed/<repo>/<id>/patch_{i}.diff` (1-indexed),
   each a standard unified diff accepted by `git apply` and GNU `patch`. One patch per
   logical fix (or per file) is preferred over one giant patch.
3. **Applied source changes**: the same edits present in the working tree so that the
   original CI build command succeeds end-to-end.

All three are independently checked. Passing the build is **not** sufficient if the
`patch_{i}.diff` files are missing or malformed, and vice-versa.

## Hard rules (from the task scope)

- Work **only** in the repository state the task marks editable
  (`/home/travis/build/failed/<repo>/<id>`). Do not read, copy, or mine a passing tree,
  hidden reference solution, or golden diff.
- Fix the **code or project configuration**, not the CI/build script. The build command is
  the contract; do not add flags that skip the failing phase or edit the runner to suppress
  the real failure.
- Keep patches **minimal and targeted**. Replace only the lines that must change; include
  ~3 lines of surrounding context so hunks match.
- Generate diffs against the **actual current file state** (git diff of your real edits),
  never against an assumed state.
- Target the **earliest / root** error. In multi-module builds a compile failure in one
  module cascades into many "cannot find symbol" errors downstream; fix the origin, not the
  symptoms. google/auto is an annotation-processing (code-generation) project, so watch for
  JDK/source-level and generated-code compile errors specifically.

## Workflow

Let `SKDIR` be this Skill's directory (e.g. `/app/environment/skills/current`). Scripts read
JSON on stdin and write JSON on stdout.

### Step 0 — Inspect the environment
```
echo '{}' | python3 "$SKDIR/scripts/inspect_env.py"
```
Returns `repo_dir` (the editable `<repo>/<id>`), `git_root`, `pom_files`, parsed `.travis.yml`
script lines, discovered reproduction `*.sh` scripts, and `suggested_commands`. Read these to
determine the **authoritative** build command (prefer an existing reproduction script or the
`.travis.yml` `script:` steps; `-f`/`-pl`/system-property flags matter). Confirm every file
referenced by the entry point actually resolves (case-sensitive) before deciding the cause.

### Step 1 — Reproduce the failure and write the analysis note
Run the real CI command and capture the log (never let huge Maven output flood the terminal):
```
echo '{"cmd":"<discovered build command>","cwd":"<repo_dir>","log_path":"/tmp/build.log","timeout":600}' \
  | python3 "$SKDIR/scripts/run_build.py"
```
It returns `exit_code`, `success`, a bounded `tail`, and extracted `errors` (lines matching
`[ERROR]`, `error:`, `cannot find symbol`, `BUILD FAILURE`, etc.). Read `/tmp/build.log` in
small sections for the earliest compilation/plugin/test error. Then write the analysis:
```
cat > /home/travis/build/failed/failed_reasons.txt <<'EOF'
<root cause: failing module, phase, plugin goal, file:line, message;
 code vs configuration; the minimal planned fix>
EOF
```

### Step 2 — Make the minimal source/config edit
Edit the offending file(s) in `repo_dir` directly with the smallest change that resolves the
root error while preserving behavior and the project's support range. For version/JDK
incompatibilities, make the code backward-compatible for the JDK the build actually selects;
do not downgrade the build matrix or skip phases.

### Step 3 — Generate the patch files from your real edits
```
echo '{"repo_dir":"<repo_dir>","files":["<rel/path/A.java>","<rel/path/B.java>"],"out_dir":"<repo_dir>","prefix":"patch","start_index":1}' \
  | python3 "$SKDIR/scripts/gen_patches.py"
```
This runs `git diff` per file and writes `<repo_dir>/patch_1.diff`, `patch_2.diff`, ... with
correct `a/`/`b/` headers and `@@` hunks. `empty` lists files that produced no diff (meaning
you did not actually change them). Patches are written relative to `git_root`; if `repo_dir`
differs from `git_root`, pass paths relative to the git root and set `out_dir` to the repo dir.

### Step 4 — Validate the patches
```
echo '{"repo_dir":"<git_root>","patches":["<repo_dir>/patch_1.diff"]}' \
  | python3 "$SKDIR/scripts/validate_patches.py"
```
For each patch it checks: structural validity (headers, hunk prefixes, hunk line-count math)
and that `git apply --check --reverse` succeeds, i.e. the patch exactly represents the current
working tree versus HEAD. Any `parse_ok:false` or `reverse_apply_ok:false` means the diff is
malformed or stale — fix it before continuing.

### Step 5 — Prove the patches alone reproduce the fix, then rebuild
Confirm the diffs are self-sufficient by resetting the touched files to HEAD and re-applying
only the patch files:
```
echo '{"repo_dir":"<git_root>","patches":["<repo_dir>/patch_1.diff"],"reset_first":true}' \
  | python3 "$SKDIR/scripts/apply_patches.py"
```
Then rerun Step 1's exact build command and confirm `success:true` (and that the build
reaches the phase that previously failed). Finally re-verify all three deliverables exist:
```
ls -1 /home/travis/build/failed/failed_reasons.txt <repo_dir>/patch_*.diff
```

## Interpreting results and failure handling

- If `inspect_env.py` finds no `repo_dir`, pass an explicit `base` or search `/home` and
  `/root` manually; the repo is the directory containing `pom.xml`/`.git` under
  `.../failed/<repo>/<id>`.
- If the build still fails after a fix, re-read the **new** earliest error — a second,
  independent problem may surface once the first is cleared. Keep each patch to one logical
  fix.
- If a referenced path in the CI entry point is missing, the failure is an early startup
  error (correct the reference), distinct from compile/test/plugin errors that appear later.
- Never edit the sealed observation or the build runner to mask a real failure. If a
  requirement genuinely cannot be met with an in-scope code/config change, record that
  explicitly in `failed_reasons.txt` rather than skipping the phase.

## Scripts summary

- `scripts/inspect_env.py` — locate editable repo, git root, POMs, CI entry points, suggested commands.
- `scripts/run_build.py` — run a shell/Maven command, log to file, return exit code + bounded tail + extracted errors.
- `scripts/gen_patches.py` — produce `patch_{i}.diff` from your real `git diff` edits.
- `scripts/validate_patches.py` — structural + `git apply --check --reverse` validation.
- `scripts/apply_patches.py` — (optionally reset to HEAD and) apply patch files to prove self-sufficiency.
