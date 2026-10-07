---
name: wyckoff-position-cif-analyzer
description: Create a reusable Python solution for CIF inputs that determines symmetry-derived Wyckoff letters, aggregates represented-site multiplicities by letter, and reports rationalized source-cell coordinates for the first original atom of each letter.
---

# Wyckoff-position CIF analyzer

Use this Skill when a task asks for a Python function that analyzes a CIF file into Wyckoff multiplicities and representative fractional coordinates.

## Deliverable

Deploy the packaged implementation to the task-required location (for this task, `/root/workspace/solution.py`):

```sh
python "$SKILL_DIRECTORY/scripts/deploy_solution.py" <<'JSON'
{"target":"/root/workspace/solution.py"}
JSON
```

The deploy helper reads one JSON object from standard input and writes one JSON object to standard output. Input schema: `{"target": "absolute-or-relative-output-path"}`; omitted `target` defaults to `/root/workspace/solution.py`. Output schema: `{"ok": true, "target": "..."}` or `{"ok": false, "error": "..."}`.

## Implementation behavior

The deployed module exposes:

```python
def analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> dict:
```

It uses `pymatgen`'s CIF parser and `SpacegroupAnalyzer` to identify symmetry-equivalent groups in the parsed structure. It intentionally does **not** use a conventional or refined standardized structure as the coordinate source. For each equivalent group it obtains its Wyckoff letter, counts represented parsed sites, and selects the lowest original site index as that orbit's representative.

Different inequivalent orbits can have the same letter. The function processes orbit records in original-site order, retains the coordinate from the first such orbit, and sums all represented-site counts into a single entry for the letter. It verifies that the groups partition all parsed sites before returning results. Each selected source fractional coordinate is converted to the closest `Fraction` having denominator at most 12 and serialized as `"0"`, `"1/2"`, etc.; it is not modulo-canonicalized, so a source endpoint such as `1` remains `"1"`.

Expected successful result schema:

```python
{
  "wyckoff_multiplicity_dict": {"a": 4},
  "wyckoff_coordinates_dict": {"a": ["0", "1/2", "1/2"]}
}
```

If parsing, symmetry analysis, or validation fails, the public function returns `{"error": "..."}` rather than returning partial data. This makes absent dependencies, invalid paths, malformed CIFs, and unsupported disordered/symmetry-inconsistent structures observable.

## Validation

After deployment, ensure the module imports and call it on one or more supplied CIF paths. Confirm that a successful response has exactly the two top-level result keys, every coordinate is a three-string list, every multiplicity is a positive integer, and the sum of multiplicities equals the number of sites parsed from the CIF. Do not alter the implementation based on particular CIF names or their expected answers.
