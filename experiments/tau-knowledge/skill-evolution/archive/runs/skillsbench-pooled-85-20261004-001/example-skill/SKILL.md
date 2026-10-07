---
name: stl-material-attribute-mass-calculator
description: Calculate a 3D printed part mass from a binary STL whose 2-byte triangle Attribute Byte Count stores a Material ID. Applies when the task requires filtering scan debris by connected components, selecting the largest geometric component, looking up material density from a supplied markdown table, and writing a JSON mass report.
---

# STL Material Attribute Mass Calculator

This Skill parses a binary STL, treats the 2-byte Attribute Byte Count field on each triangle as a Material ID, welds vertices with a coordinate-scale tolerance to find connected components, selects the largest geometric component (preferring watertight enclosed volume over triangle count), looks up the selected component's material density in a markdown table, and writes the required mass report.

## Entrypoint

Use the packaged script:

```bash
python scripts/calculate_mass_report.py <<'JSON'
{
  "stl_path": "/root/scan_data.stl",
  "density_table_path": "/root/material_density_table.md",
  "output_path": "/root/mass_report.json",
  "stl_length_unit": "mm"
}
JSON
```

The script reads JSON from stdin and emits JSON to stdout. It writes `/root/mass_report.json` with exactly:

```json
{
  "main_part_mass": 12345.67,
  "material_id": 42
}
```

Do not hardcode IDs, densities, component counts, or expected masses. The script reads the supplied runtime files.

## Input schema for `scripts/calculate_mass_report.py`

All fields are optional except when using non-default paths:

- `stl_path` (string, default `/root/scan_data.stl`): binary STL path.
- `density_table_path` (string, default `/root/material_density_table.md`): markdown material-density table path.
- `output_path` (string, default `/root/mass_report.json`): report path to write.
- `tolerance` (number or null): vertex weld tolerance in STL coordinate units. If omitted/null, the script uses a scale-based tolerance derived from the mesh bounding-box diagonal.
- `stl_length_unit` (string, default `mm`): coordinate length unit used only when the density table explicitly states a volumetric unit such as `g/cm^3` or `kg/m^3`. Accepted values include `raw`, `mm`, `cm`, `m`, `in`, `inch`. Use `raw` to disable length-unit conversion even if a density unit is detected.
- `density_conversion` (string, default `auto`): `auto` converts explicit density units to mass per STL coordinate unit cubed; `none` uses density numbers exactly as listed.
- `output_mass_unit` (string, default `same`): optional conversion of the final mass to `mg`, `g`, `kg`, `lb`, or `same` for the mass unit implied by the density entry.

Stdout on success contains `status: ok`, the written `report`, and diagnostics including component statistics, chosen tolerance, density parsing details, watertightness, and material counts. On failure it emits `status: error` and exits nonzero.

## Method and assumptions

1. Binary STL validation: the script checks the 80-byte header, little-endian triangle count, and 50-byte triangle record size. The final 2-byte field is parsed as an unsigned little-endian Material ID, per the task-specific data documentation.
2. Connected components: vertices are welded using a tolerance justified by coordinate scale. Triangles sharing any welded vertex are unioned into components. This filters disconnected scanning debris without relying on file order, triangle count, or identifiers.
3. Largest part selection: each component is measured geometrically. For closed/watertight components, the script selects the component with largest repaired absolute enclosed volume. If no component is watertight, it falls back to surface area and reports this in diagnostics.
4. Volume: for the selected closed oriented triangle surface, the script checks edge watertightness and attempts consistent face orientation via shared-edge constraints. It computes enclosed volume by a signed tetrahedral sum relative to the component bounding-box center and uses the absolute repaired volume.
5. Material ID: the selected component's triangle Attribute Byte Count values are counted; the modal Material ID is used. If multiple IDs appear in the selected component, diagnostics include all counts.
6. Density lookup: markdown pipe tables and simple labeled/list lines are parsed for Material ID and Density. Explicit units like `g/cm^3`, `kg/m^3`, and `g/mm^3` are recognized. If table values already represent mass per STL-coordinate cubed or no unit is stated, use `density_conversion: none` or `stl_length_unit: raw` as appropriate.
7. Artifact validation: the solver reopens the written report and verifies that it contains finite numeric `main_part_mass` and integer `material_id` matching the computed result. A separate validation script can independently recompute and compare the report.

## Optional validation

After producing the artifact, run:

```bash
python scripts/validate_mass_report.py <<'JSON'
{
  "stl_path": "/root/scan_data.stl",
  "density_table_path": "/root/material_density_table.md",
  "report_path": "/root/mass_report.json",
  "stl_length_unit": "mm",
  "relative_tolerance": 1e-9
}
JSON
```

This script recomputes the mass with the same public inputs, reads the produced JSON, and emits `status: ok` only if the material ID matches and the mass agrees within the requested relative tolerance.

## Failure modes to handle

- STL file missing, too small, not a valid fixed-size binary STL, or triangle count/size mismatch.
- No nondegenerate connected component can be measured.
- Main component is not watertight; the script can still fall back to area selection, but volume may be unreliable and diagnostics should be reviewed.
- Selected component has zero/nonfinite volume.
- Material ID is missing from the density table or the density table format is too ambiguous to parse.
- Density units are explicit but the STL coordinate unit is unknown; rerun with the correct `stl_length_unit` or `density_conversion: none`.
