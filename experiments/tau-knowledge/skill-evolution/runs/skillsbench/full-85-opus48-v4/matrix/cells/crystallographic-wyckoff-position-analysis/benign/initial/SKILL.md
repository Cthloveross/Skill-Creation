---
name: crystallographic-wyckoff-position-analysis
description: >-
  Build and run a standalone Python deliverable that reads a CIF file, performs
  crystallographic symmetry analysis, and returns Wyckoff-position multiplicities
  plus bounded-denominator rational approximate coordinates for the first atom of
  each Wyckoff position. Use this when a task asks for
  analyze_wyckoff_position_multiplicities_and_coordinates(filepath) producing
  wyckoff_multiplicity_dict / wyckoff_coordinates_dict from SHELX/Materials-Project
  style CIF inputs.
---

# Wyckoff position multiplicity & coordinate analysis

## What the task requires

The public task asks you to author `/root/workspace/solution.py` containing:

```
def analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> (dict[str, dict] | dict[str, Any])
```

Given one CIF file path it must return a dict with exactly two keys:

- `wyckoff_multiplicity_dict`: `{wyckoff_letter: multiplicity_int}`
- `wyckoff_coordinates_dict`: `{wyckoff_letter: [str, str, str]}` where each
  string is a rational number with denominator ≤ 12 (e.g. `"0"`, `"1/2"`,
  `"3/8"`, `"8/9"`).

Example (`FeS2_mp-226.cif`):
```
{
  "wyckoff_multiplicity_dict": {"a": 4, "c": 8},
  "wyckoff_coordinates_dict": {"a": ["0","1/2","1/2"], "c": ["3/8","1/9","8/9"]}
}
```

Constraints: the script must not hardcode answers, and coordinates are the
nearest rational (denominator ≤ 12). External imports (e.g. `pymatgen`) are
explicitly encouraged.

CIF inputs are supplied at `/root/cif_files/*.cif` (see `public_inputs`
manifest). Read the actual files at runtime; never embed per-file answers.

## Method (why these choices)

Derived from the frozen background on interpreting Wyckoff summaries:

1. **Use the original parsed structure setting, not the standardized cell.**
   Parse the CIF with `pymatgen.core.Structure.from_file`, run
   `SpacegroupAnalyzer(structure).get_symmetrized_structure()`. Its
   `equivalent_sites` are `PeriodicSite`s of the *original* input structure, so
   representative fractional coordinates come from the intended setting.
2. **Representative = first occurrence in the orbit's requested ordering.** Take
   `equivalent_sites[i][0]` (lowest original site index of that orbit) for the
   coordinate triple.
3. **Distinct inequivalent orbits can share a Wyckoff letter.** The output has
   one entry per letter, so apply an explicit letter-level reduction:
   **sum the represented-site counts** (`len(equiv_group)`) across every orbit
   that carries the same letter rather than discarding later orbits. Keep the
   coordinate of the *first* orbit encountered for that letter.
4. **Reconcile with the parsed structure.** The total of all represented-site
   counts must equal `len(structure)` (the number of atoms actually parsed).
   The solution asserts this.
5. **Bounded-denominator rational approximation, endpoints preserved.** Convert
   each selected source coordinate with `Fraction(x).limit_denominator(12)` and
   serialize deterministically (`"0"`, `"1"`, `"n/d"`). Do **not** apply modulo /
   half-open canonicalization — preserve the source representative (so a `1.0`
   stays `"1"`).

Multiplicity therefore reflects represented sites in the parsed cell; for the
conventional-cell CIFs here this equals the crystallographic Wyckoff
multiplicity (e.g. FeS2 `a`=4, `c`=8). The Wyckoff *letter* is parsed as the
alphabetic part of each symbol such as `4a` -> `a`, `24d` -> `d`.

## Files

- `references/solution_template.py` — the complete, standalone deliverable. It
  depends only on `pymatgen` + the standard library and includes a `__main__`
  CLI. This is what gets written to `/root/workspace/solution.py`.
- `scripts/install_solution.py` — writes the template to the deliverable path
  (default `/root/workspace/solution.py`), creating the directory, and ensures
  `pymatgen` is importable (pip-installs it if missing and internet is allowed).
- `scripts/run_wyckoff.py` — dynamically loads the written `solution.py` and runs
  the entry function on a CIF path (or on every file under `/root/cif_files`),
  for local verification.

## How the executor uses this Skill

1. Install the deliverable and dependency:
   ```
   echo '{}' | python3 /app/environment/skills/current/scripts/install_solution.py
   ```
   Expected stdout JSON: `{"written": "/root/workspace/solution.py", "pymatgen": true}`.
   If `pymatgen` is false, inspect the `error` field and install manually
   (`pip install pymatgen`); internet is allowed in this environment.

2. Verify the deliverable actually regenerates correct output by running the
   exported entry function (not just checking a leftover file):
   ```
   echo '{"filepath": "/root/cif_files/FeS2_mp-226.cif"}' | \
     python3 /app/environment/skills/current/scripts/run_wyckoff.py
   ```
   Confirm the FeS2 result equals the documented example
   (`{"a":4,"c":8}` and the two coordinate triples). Then sanity-run every CIF:
   ```
   echo '{"all": true}' | \
     python3 /app/environment/skills/current/scripts/run_wyckoff.py
   ```
   For each file check: output has both required keys, both sub-dicts share the
   same letters, each coordinate list has 3 rational strings with denominator
   ≤ 12, and the multiplicity total equals the atom count of the parsed cell
   (the script reports `site_total_ok`).

3. The grader runs `/root/workspace/solution.py` independently with no access to
   this Skill directory, so the file must stay fully self-contained. Do not add
   imports from Skill helpers into the deliverable.

## Input/output schemas for scripts

`install_solution.py` — stdin: `{}` or `{"path": "<dest>"}`; stdout:
`{"written": <path>, "pymatgen": <bool>, "error": <optional str>}`.

`run_wyckoff.py` — stdin one of:
- `{"filepath": "/root/cif_files/X.cif"}` -> `{"result": {...}}`
- `{"all": true}` (optional `"dir"`, default `/root/cif_files`) ->
  `{"results": {basename: {...} | {"error": str}}}`
Each per-file result also carries `site_total_ok` / `n_atoms` diagnostics.

## Failure handling

- Missing `pymatgen`: `install_solution.py` attempts a pip install; if it still
  fails it returns `pymatgen=false` with the error — install it before grading.
- A CIF that a given `symprec` cannot symmetrize: `solution.py` retries
  `SpacegroupAnalyzer` with a looser tolerance before raising; the failure is
  reported per file by `run_wyckoff.py` rather than crashing the batch.
- If the represented-site total does not match the parsed atom count the
  solution raises an assertion — surfacing a setting/ordering mismatch instead
  of emitting an unreconciled summary.
