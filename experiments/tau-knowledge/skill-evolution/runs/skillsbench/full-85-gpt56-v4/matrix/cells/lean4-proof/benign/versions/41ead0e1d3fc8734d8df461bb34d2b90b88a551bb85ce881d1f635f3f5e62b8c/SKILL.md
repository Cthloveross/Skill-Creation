---
name: lean-template-proof-completion
description: Complete a proof hole in a supplied Lean template while preserving a protected source prefix and validating the exact project environment with warnings treated as errors. Use for Lean theorem-completion tasks that permit edits only to the template source file.
---

# Lean template proof completion

## Applicability and assumptions

Use this Skill when the task supplies a Lean project and a theorem template, identifies a protected initial part of the source file, and requires type-checking without warnings. Work in the project's declared workspace and edit only the permitted target file.

The imported declarations, numeric types, simplifier lemmas, and tactics in the supplied project are authoritative. Do not assume that a theorem or tactic from another Lean/Mathlib version is available.

## Procedure

1. Read the task constraints and inspect the target before editing:
   ```sh
   cd /app/workspace
   nl -ba solution.lean
   sed -n '1,160p' solution.lean
   sed -n '1,160p' Library.lean
   ```
   Inspect relevant imported files or use `#check`/small temporary proof-local experiments only when needed. Determine the type of the recursive sequence and how division, powers, numerals, and order are elaborated.

2. Before changing the target, snapshot the required prefix outside the workspace. For a prefix through line 14, for example:
   ```sh
   python3 /app/environment/skills/current/scripts/validate_lean_template.py <<'EOF'
   {"action":"snapshot","solution":"/app/workspace/solution.lean","snapshot":"/tmp/solution.lean.prefix","prefix_lines":14}
   EOF
   ```
   This preserves the leading blank line and exact bytes of the protected lines. Do not rewrite, format, or re-save the protected portion.

3. Fill only the proof area. For a recursively defined sequence, start with induction on the index and unfold only the successor equation currently needed. A plain upper-bound induction is often too weak when the recurrence adds a positive term. In that case, establish a stronger, inductively stable invariant (commonly an exact finite-geometric closed form or a bound that retains the remaining tail), then derive the requested weak bound from nonnegativity. Keep casts, denominator-nonzero facts, and positivity facts explicit if the installed arithmetic tactics need them.

4. Prefer a compact proof based on definitions and imported automation. Typical proof stages are:
   - base case: simplify the recursive definition and numeric expression;
   - successor: expose the recursive equation with `simp [S]` or the local definition, use the induction hypothesis, and normalize the resulting arithmetic;
   - final bound: apply order reasoning and prove positivity/nonnegativity of the residual term.

   Select `simp`, `rw`, `ring`, `ring_nf`, `norm_num`, `linarith`, `nlinarith`, or field-clearing tactics only after confirming they are imported and match the actual type. Avoid `sorry`, `admit`, axioms, or changing the theorem statement/definitions to bypass the proof.

5. Compile the actual final target with warnings promoted to errors and verify the frozen prefix:
   ```sh
   cd /app/workspace
   python3 /app/environment/skills/current/scripts/validate_lean_template.py <<'EOF'
   {"action":"check","solution":"/app/workspace/solution.lean","snapshot":"/tmp/solution.lean.prefix","prefix_lines":14,"cwd":"/app/workspace"}
   EOF
   ```
   The reported JSON must have `ok: true`, `prefix_matches: true`, and `compile.returncode: 0`. If it does not, correct only the permitted proof region and rerun this check.

## Validator interface

`scripts/validate_lean_template.py` reads one JSON object from standard input and emits one JSON object to standard output.

- `action: "snapshot"`: requires `solution`, `snapshot`, and `prefix_lines`; writes the exact initial `prefix_lines` physical lines to the supplied snapshot path. Use a temporary path outside the restricted workspace.
- `action: "check"`: requires `solution`, `snapshot`, and `prefix_lines`; optional `cwd` defaults to the solution directory, and optional `compile_command` overrides the default command. It compares the exact prefix bytes and runs, by default, `lake env lean --Werror <solution-basename>` in `cwd`.

The validator never edits the Lean source. A nonzero validator exit means either malformed input, a prefix mismatch, or a failed Lean compilation; inspect its JSON diagnostics before making a proof-local correction.
