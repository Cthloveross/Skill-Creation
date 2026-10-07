# Adaptable proof for S n <= 2

These are templates. ALWAYS read the real `solution.lean` first and mirror its
number type (`ℚ` or `ℝ`) and the exact successor expression in the `S`
definition. Append only the proof body; never alter the fixed prefix.

## Primary attempt (equality strengthening)

Replace `T` with the actual type of `S` (e.g. `ℚ` or `ℝ`), and replace the term
in `hstep` with the exact right-hand side from the definition's successor case.

```lean
  have H : ∀ m : ℕ, S m = 2 - 1 / 2 ^ m := by
    intro m
    induction m with
    | zero => norm_num [S]
    | succ k ih =>
      have hstep : S (k + 1) = S k + 1 / 2 ^ (k + 1) := rfl
      rw [hstep, ih]
      ring
  rw [H n]
  have hpos : (0 : T) ≤ 1 / 2 ^ n := by positivity
  linarith
```

Why it works:
- base: `S 0` is definitionally `1`; `norm_num [S]` reduces the goal
  `1 = 2 - 1/2^0` (with `2^0 = 1`).
- step: unfold the recursion, rewrite with `ih`, and `ring` closes
  `(2 - 1/2^k) + 1/2^(k+1) = 2 - 1/2^(k+1)` because `ring` knows
  `2^(k+1) = 2^k * 2` and handles division in a field.
- finish: `2 - 1/2^n ≤ 2` since `1/2^n ≥ 0`.

## Fallbacks

- If `rfl` fails for `hstep`, unfold via the generated equation lemmas:
  ```lean
    | succ k ih =>
      simp only [S]
      rw [ih]
      ring
  ```
  or `rw [S, ih]; ring` / `rw [S]; rw [ih]; ring`.
- If `ring` leaves a residual goal, try `field_simp; ring` or `ring_nf; norm_num`.
- If the base case is not closed by `norm_num [S]`, try
  `show (1 : T) = 2 - 1 / 2 ^ 0; norm_num` or `simp only [S]; norm_num`.
- If `linarith`/`positivity` are unexpectedly unavailable, the final step is
  `rw [H n]`, then `have : (0:T) ≤ 1/2^n := by positivity` and
  `linarith`; alternatively `nlinarith [hpos]`, or the Library tactics
  `addarith`/`rel` with an explicit `1/2^n ≥ 0` fact.

## Alternative: inequality strengthening (if equality route stalls)

Prove `∀ m, S m ≤ 2 - 1 / 2 ^ m` by the same induction, using `rel`/`linarith`
in the step with `0 < 1/2^(k+1)`, then conclude `S n ≤ 2 - 1/2^n ≤ 2`.

## Discipline

- Make the smallest proof-local edit; keep positivity/nonzero and coercion side
  conditions explicit when automation cannot infer them.
- After each edit run `scripts/build.py`; require `ok=true` with no warnings.
- Run `scripts/check_prefix.py` against the saved `solution.lean.orig` to prove
  the fixed prefix (including the leading blank line) is byte-identical.
- Change no file other than `solution.lean`.
