---
name: stl-material-mass-report
description: Calculate a printed part's mass from a binary STL whose 2-byte attribute field stores a Material ID. Use when the required result is the mass of the geometrically largest connected, closed STL component and a supplied Markdown table maps Material IDs to densities.
---

# STL material mass report

Use `scripts/calculate_mass.py` to parse the runtime STL, remove disconnected debris, obtain the selected part's Material ID from its STL attribute words, look up density, and write the required JSON report.

## Assumptions and method

- The STL is binary: an 80-byte header, a little-endian unsigned 32-bit facet count, then exactly that many 50-byte records. Each record has 12 little-endian `float32` values followed by a little-endian unsigned 16-bit attribute word.
- Attribute words are treated as Material IDs, not as conventional unused attribute-byte counts.
- Vertices within a scale-relative tolerance (`max(bounding-box span, 1) * 1e-8`) are treated as identical. Triangle components are formed through these shared vertices; neither STL record order nor Material ID is used to select the part.
- Components must be watertight and consistently orientable. The script consistently orients each closed component, calculates its signed tetrahedral volume, and selects the component with the largest absolute enclosed volume. This makes “largest” a geometric measurement rather than a facet-count heuristic.
- The density number is multiplied directly by the computed STL volume, as requested by `Volume * Density`. Any density/unit conventions therefore must be those documented in the supplied density table and task inputs; STL itself has no inherent unit metadata.

The density table should contain a Markdown table with headers identifying a Material ID (for example `Material ID` or `ID`) and `Density`. The numeric density cell may include a unit suffix.

## Run

The script receives one JSON object on standard input and emits one JSON object on standard output. All fields are optional only because the public task supplies these default paths:

```json
{
  "stl_path": "/root/scan_data.stl",
  "density_table_path": "/root/material_density_table.md",
  "output_path": "/root/mass_report.json"
}
```

For example, invoke it with Python and the JSON above. On success stdout includes `ok`, the report path, selected Material ID, density, volume, and mass. It creates `output_path` atomically with exactly:

```json
{"main_part_mass": 12345.67, "material_id": 42}
```

(the actual numeric values come only from the runtime inputs).

## Validation and failures

Before writing the result the script validates STL record length, finite coordinates, connectivity, component watertightness, orientability, nonzero selected volume, a single Material ID across the selected part, and a matching numeric density. It reopens the written JSON and verifies its exact key set, numeric finite mass, integer Material ID, and equality with the calculated result. Failures produce a JSON error on stdout and a nonzero exit status; do not substitute a guessed material, density, or mass.
