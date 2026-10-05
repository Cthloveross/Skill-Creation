---
name: wyckoff-position-summary-solution
description: Create and validate a Python solution that reads a CIF, uses pymatgen symmetry analysis to summarize source-structure Wyckoff positions, combines inequivalent orbits with the same Wyckoff letter, and emits bounded-denominator rational representative coordinates. Use for the crystallographic Wyckoff-position analysis task requiring /root/workspace/solution.py.
---

## What this Skill produces

The packaged writer creates `/root/workspace/solution.py`.  Its public entrypoint is:

```python
def analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> dict:
```

The entrypoint returns:

```python
{
    "wyckoff_multiplicity_dict": {<letter>: <int>, ...},
    "wyckoff_coordinates_dict": {<letter>: [<rational>, <rational>, <rational>], ...},
}
```

It relies on `pymatgen`, which provides CIF parsing and `SpacegroupAnalyzer` symmetry classification.

## Method

1. Load the supplied CIF without primitive-cell conversion. This retains the parsed/source site ordering and coordinates.
2. Obtain `equivalent_indices` and `wyckoff_symbols` from `SpacegroupAnalyzer(...).get_symmetrized_structure()`.
3. Treat every equivalent-index group as one orbit. Its represented multiplicity is the number of original parsed sites in that group, not a standardized-cell multiplicity.
4. Sort orbit records by their earliest original site index. For each Wyckoff letter, sum multiplicities across all its orbits. If multiple inequivalent orbits share that letter, retain the coordinate from the earliest original site across them.
5. Read the representative coordinate from the original parsed `Structure`, never from a standardized structure. Approximate each component independently with `Fraction(...).limit_denominator(12)` and serialize it as a deterministic `p/q` or integer string. Do not modulo-wrap coordinates, since a source endpoint such as `1` may be the requested representative.
6. Validate that symmetry groups partition the original sites and that the final multiplicity sum reconciles with the parsed site count.

The solution deliberately fails clearly for missing input, empty structures, malformed Wyckoff symbols, unavailable pymatgen, or internally inconsistent symmetry partitions. It does not substitute CIF labels or silently return a partial result.

## Create the required artifact

Run the writer with JSON on standard input. `output_path` is optional and defaults to the required task path.

```bash
python scripts/write_solution.py <<'JSON'
{"output_path": "/root/workspace/solution.py"}
JSON
```

The script emits a JSON status object on stdout. The generated module contains no hardcoded CIF names, materials identifiers, or expected result values.

## Validate an artifact

After the artifact is created, validate it with any supplied CIF path. This validator imports the generated entrypoint, checks the required schema and rational-coordinate contract, and reconciles reported multiplicities with the number of non-primitive parsed source sites.

```bash
python scripts/validate_solution.py <<'JSON'
{
  "solution_path": "/root/workspace/solution.py",
  "cif_path": "/root/cif_files/<input>.cif"
}
JSON
```

A successful validation emits `{"valid": true, ...}`. A false result identifies an import, execution, schema, coordinate, or site-count reconciliation failure.
