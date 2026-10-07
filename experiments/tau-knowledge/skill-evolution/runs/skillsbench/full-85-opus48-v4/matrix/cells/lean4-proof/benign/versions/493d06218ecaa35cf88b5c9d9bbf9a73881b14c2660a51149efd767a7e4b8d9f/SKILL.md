---
name: lean4-geometric-sum-bound-proof
description: >-
  Finalize a Lean 4 proof in /app/workspace/solution.lean for a recursively
  defined partial-sum sequence (S 0 = 1, S (n+1) = S n + 1/2^(n+1)) proving an
  upper bound (S n <= 2) for all natural n. Use this when a Lean template leaves
  a `by` block to complete starting at a fixed line, the file prefix (imports,
  definition, theorem statement, including a leading blank line) must stay byte
  identical, no other file may change, and the file must type-check with no
  warnings (warnings treated as errors). Applies to Mechanics-of-Proof style
  projects whose Library imports Mathlib. Adapt by reading the actual file.
---

# Lean 4 geometric-sum upper-bound proof

## What the task requires

The public task gives `/app/workspace/solution.lean` with a fixed prefix:
a leading blank line, imports, a recursive definition of `S`, and the theorem
`problemsolution` ending in `:= by`. You must complete the proof body (from the
line indicated in the opening, typically line 15 onward) so that:

- Nothing before the proof region changes (the grader checks the exact prefix,
  including the leading blank line).
- No file other than `solution.lean` changes.
- The file type-checks with **no warnings** (warnings = errors).

This Skill does not auto-write the proof; the executor writes it in the terminal
and uses the packaged scripts to compile and to confirm the prefix is intact.

## Mathematical method (strengthened induction)

`S n = sum_{i=0}^n 1/2^i = 2 - 1/2^n`, so `S n <= 2`. A direct induction on
`S n <= 2` is too weak (the successor step adds a positive term). Prove the
**equality strengthening** `S m = 2 - 1/2^m` by induction, then finish:

- base `m = 0`: `S 0 = 1 = 2 - 1/2^0`.
- step `m = k+1`: unfold `S (k+1) = S k + 1/2^(k+1)`, rewrite with the induction
  hypothesis `S k = 2 - 1/2^k`, then close by field arithmetic (`ring`), since
  the sequence lives in a field (`ℚ` or `ℝ`) where `2^(k+1) = 2^k * 2`.
- conclusion: `1/2^n >= 0`, hence `2 - 1/2^n <= 2`.

## Step-by-step procedure

1. Inspect the real environment before choosing tactics:
   - `sed -n '1,30p' /app/workspace/solution.lean` to see the leading blank
     line, imports, the exact `S` definition (its number type and the exact
     shape of the successor expression, e.g. `1 / 2 ^ (n + 1)`), the theorem
     statement, and the first editable line.
   - Note whether the type is `ℚ` or `ℝ`; mirror it in your `have`/`positivity`
     steps. Confirm which imports are present (`cat /app/workspace/Library.lean`
     and the file's own imports) — these projects re-export Mathlib, so
     `induction ... with`, `ring`, `norm_num`, `positivity`, `linarith` are
     available. The Library's custom tactics (`addarith`, `cancel`, `rel`,
     `numbers`, `extra`) are fallbacks; core `induction` is not shadowed.
2. Back up the original to be able to prove the prefix is unchanged:
   `cp /app/workspace/solution.lean /app/workspace/solution.lean.orig`.
3. Append the proof body only after the fixed prefix. Do not retype or alter the
   prefix lines. See `references/proof_strategy.md` for a ready-to-adapt proof
   and fallbacks for unfolding `S`.
4. Compile with the build script and read its JSON result:
   `echo '{"file":"/app/workspace/solution.lean"}' | python3 \
     $SKILL/scripts/build.py` (SKILL = the installed skill directory,
   e.g. /app/environment/skills/current). `ok` must be `true`, with
   `has_error=false` and `has_warning=false`. If not, read `stdout`/`stderr`,
   fix the smallest proof-local issue, and recompile. Treat any `warning:` line
   as a failure (e.g. unused hypothesis, `simp` made no progress): remove the
   offending tactic/binder.
5. Confirm the fixed prefix is byte-identical to the backup:
   `printf '{"file":"/app/workspace/solution.lean","reference":"/app/workspace/solution.lean.orig","lines":PREFIX_N}' | python3 $SKILL/scripts/check_prefix.py`
   where `PREFIX_N` is the number of fixed lines before your first edit
   (the editable region starts at line 15 per the opening, so the fixed prefix
   is lines 1..14 — verify against the actual file; the `S := by` theorem line
   must be inside the fixed prefix). Require `prefix_match=true`.
6. Re-open the final file (`cat /app/workspace/solution.lean`) to confirm no
   unrelated declaration changed and that only the proof body was added. Remove
   the `.orig` backup is optional (it is not graded, but do not leave stray
   edits to other project files).

## Handling failure modes

- `rfl`/`simp only [S]` cannot unfold the step: these recursive defs are
  structurally recursive, so `have hstep : S (k+1) = S k + <exact term> := rfl`
  usually holds; if `rfl` fails, use `simp only [S]` (its auto-generated
  equation lemmas) or `rw [S]`. Match the def's exact term verbatim.
- `ring` leaves a goal: use `field_simp` then `ring`, or `ring_nf` then
  `norm_num`. Divisions in a field are handled by `ring`.
- Final inequality: `rw [H n]` then `have h : (0:T) <= 1/2^n := by positivity`
  and `linarith` (T is the sequence's type). `positivity` needs the correct
  numeric type literal.
- Unknown-option / warning noise: if the build reports a warning you cannot
  silence through tactics, delete the construct producing it (unused `have`,
  redundant `simp`); do not add `set_option` lines inside the proof unless they
  are strictly proof-local and warning-free.
- Only `solution.lean` may change. If any check needs another file edited, stop:
  that is unsupported; re-read the actual definition instead.

## Scripts

- `scripts/build.py` — stdin JSON `{"file":<path>, "warnings_as_errors":bool?,
  "workdir":<dir>?, "timeout":<sec>?}`. Runs `lake env lean <file>` in the
  file's directory (the Lean project at `/app/workspace`). stdout JSON:
  `{ok, returncode, has_error, has_warning, stdout, stderr, cmd}`. `ok` is true
  only when returncode is 0 and no `warning:`/`error:` appears.
- `scripts/check_prefix.py` — stdin JSON `{"file":<path>, "reference":<path>?,
  "lines":<N>?}`. Compares the first `N` lines of `file` to `reference`
  (defaults to all reference lines). stdout JSON: `{prefix_match, diffs, head,
  file_total_lines}`.

See `references/proof_strategy.md` for the concrete adaptable proof text.
