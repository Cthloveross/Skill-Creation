---
name: binary-stl-main-part-mass
description: Create a mass_report.json for a binary STL whose per-triangle Attribute Byte Count stores a Material ID. Use when disconnected scan debris must be removed by geometric connected-component volume and density is documented in a supplied Markdown file.
---

# Binary STL main-part mass

Use `scripts/calculate_mass.py` to parse the runtime STL, select the disconnected closed component with greatest enclosed geometric volume, read its consistent Attribute Byte Count as its Material ID, look up that ID's documented density, and write the required JSON report.

The helper uses Python's standard library only. It does not choose a part from record order, triangle count, header text, or material ID.

## Invocation

The script accepts one JSON object on standard input and emits one JSON status object on standard output. Paths default to the task's supplied locations.

```sh
python3 scripts/calculate_mass.py <<'JSON'
{"stl_path":"/root/scan_data.stl","density_table_path":"/root/material_density_table.md","output_path":"/root/mass_report.json","verify":true}
JSON
```

Input fields:

- `stl_path` (optional string): binary STL path; default `/root/scan_data.stl`.
- `density_table_path` (optional string): Markdown material-density documentation; default `/root/material_density_table.md`.
- `output_path` (optional string): report destination; default `/root/mass_report.json`.
- `verify` (optional boolean): recompute and reopen the artifact after writing; default `true`.

The density reader supports Markdown tables whose headers identify a Material ID/Material Identifier (including ordinary `ID` or `Identifier` headers) and a Density column, regardless of column order. It also supports labelled records such as `Material ID: 42` followed by `Density: 1.24`. It takes the density value itself, not a digit displayed in a unit such as `g/cm³`.

## Result and checks

The resulting artifact contains exactly the requested fields, for example:

```json
{"main_part_mass":12345.67,"material_id":42}
```

`material_id` is an integer and `main_part_mass` is a finite JSON number. The calculation uses the task formula `Volume * Density`; therefore the STL coordinate units and documented density units must already be compatible. The helper does not silently introduce an unsupported unit conversion.

The method validates the fixed-record binary STL length, finite vertices, scale-derived vertex connectivity, closed/manifold oppositely wound edges, a positive signed-tetrahedral enclosed volume, one material ID across the chosen part, and an available finite density. It writes the report atomically and, when verification is enabled, reopens it and checks it against a fresh recomputation. Missing data, malformed meshes, ambiguous materials, and unparseable density documentation are failures rather than guessed values.
