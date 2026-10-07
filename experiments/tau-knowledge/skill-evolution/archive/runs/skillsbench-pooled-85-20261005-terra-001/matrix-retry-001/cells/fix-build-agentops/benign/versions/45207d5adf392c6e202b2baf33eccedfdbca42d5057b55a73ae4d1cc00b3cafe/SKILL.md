---
name: bugswarm-python-ci-repair
version: 1.0.0
description: Diagnose and repair a Python CI failure in the editable BugSwarm failed workspace while preserving the CI contract. Use when the task requires failed_reasons.txt, numbered valid unified-diff artifacts, and the corresponding source changes applied.
---

# BugSwarm Python CI Repair

## Scope and safeguards

Work only in the editable repository below `/home/github/build/failed/`; do not seek or compare a passing snapshot, hidden patch, or reference solution. The build configuration and its original reproduction entry point are the contract. Do not make a build pass by removing environments, skipping tests, weakening assertions, or changing CI to avoid the failing command unless the observed first failure itself proves that configuration is erroneous.

The required deliverables are:

1. `/home/github/build/failed/failed_reasons.txt`
2. One or more `/home/github/build/failed/<repo>/<id>/patch_<i>.diff` files
3. The source changes represented by those patches applied in that same editable repository

## Procedure

1. **Locate the target without leaving the failed workspace.** Inspect the immediate structure under `/home/github/build/failed/` to identify the `<repo>/<id>` directory containing the editable checkout. Confirm it contains project files or repository metadata. Do not infer a repository name or ID from this Skill.

2. **Find the actual CI entry point and inspect configuration.** Read available reproduction scripts first, then relevant `tox.ini`, `pyproject.toml`, `setup.cfg`, `setup.py`, dependency metadata, and `.github/workflows/` files. Determine the command, interpreter, environment variables, and test runner used by the declared failing build. Do not substitute an unrelated local pytest invocation for a tox/CI entry point.

3. **Reproduce and record the first failure.** Run the available declared entry point from the editable checkout, respecting the supplied build timeout. Capture the earliest failing step, its command, interpreter/environment name, traceback or resolver error, file and line, and whether it occurs in environment creation, installation, collection, or test execution. Later failures may be cascades.

4. **Write the analysis before changing source.** Write `failed_reasons.txt` using `scripts/write_analysis.py` or an equivalent atomic write. It must state:
   - the checkout and reproduction command examined;
   - relevant Python, tox, and dependency versions if reported;
   - the first observed failure and its layer;
   - evidence connecting that failure to a precise root cause;
   - whether the correction belongs in source or build configuration and why;
   - a minimal file-by-file repair plan and the original-command verification plan.

   Do not claim a command passed unless it was actually run by the executor.

5. **Make a minimal compatible repair.** For a version error, replace only the confirmed incompatible construct with an equivalent supported by the project’s declared interpreter range. For logic failures, preserve intended behavior and target the assertion/traceback evidence. Review related executing occurrences only when the evidence shows they share the same unsupported path.

6. **Create patches before applying them.** Prefer `scripts/create_apply_patches.py`. Supply candidate *complete new text* for each existing UTF-8 source/configuration file. The script reads the real current preimage, creates `patch_<i>.diff` using standard `a/` and `b/` headers, structurally validates every hunk, verifies every preimage in memory, writes every patch, and only then atomically writes the changed source files. This ensures the patch is based on the actual state and the applied edit is exactly what its diff represents.

   Example (replace placeholders with actual values and content):

   ```sh
   python "$SKILL_DIR/scripts/create_apply_patches.py" <<'JSON'
   {
     "repo": "/home/github/build/failed/<repo>/<id>",
     "patch_start": 1,
     "changes": [
       {"path": "relative/file.py", "new_content": "complete replacement file text\\n"}
     ]
   }
   JSON
   ```

   For later independent repair rounds, set `patch_start` to an unused number. A later patch is intentionally generated against the source state produced by earlier patches, so applying numbered patches in order recreates the final tree.

   The helper supports modifications of existing, newline-terminated UTF-8 text files. For binary files or file creation/deletion, use the available standard `git diff`/`git apply` tools against the real checkout instead; validate with `git apply --check` before applying. Never handwrite a diff against assumed content.

7. **Validate artifacts and verify the repair.** The helper validates patch headers, hunk syntax, line counts, path safety, and exact preimage matching before modification. Additionally inspect that every required `patch_<i>.diff` exists in the checkout, use `git diff --check` when Git is available, and validate externally generated patches with the helper’s `validate` mode. Re-run the original CI/reproduction command and report its actual result. If it exposes a distinct root cause, update `failed_reasons.txt`, create the next patch, and retest rather than concealing the failure.

## Helper interfaces

### `scripts/write_analysis.py`

Reads one JSON object from stdin and emits one JSON result to stdout.

Input:

```json
{"path":"/home/github/build/failed/failed_reasons.txt","text":"analysis and plan"}
```

`path` must be an absolute path and `text` must be nonempty. The file is UTF-8 and atomically replaced.

### `scripts/create_apply_patches.py`

Reads one JSON object from stdin and emits one JSON result to stdout.

`apply` mode input:

```json
{
  "repo": "/absolute/editable/checkout",
  "patch_start": 1,
  "changes": [
    {"path": "relative/existing-file.py", "new_content": "full UTF-8 replacement text\\n"}
  ]
}
```

All paths must be relative regular files inside `repo`; each item must change content. On success, stdout lists created patch paths and applied source paths. On an error, it emits `{ "ok": false, "error": "..." }`, exits nonzero, and does not intentionally write any source modification.

`validate` mode input:

```json
{"mode":"validate","repo":"/absolute/editable/checkout","patch_path":"/absolute/editable/checkout/patch_1.diff","check_preimage":true}
```

It validates standard unified-diff structure and, when requested, confirms the current files match each deletion/context preimage. Validation does not write source files.
