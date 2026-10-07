---
name: binary-stl-main-part-mass
description: Calculate the mass of the largest closed connected component in a binary STL when each triangle's Attribute Byte Count is a Material ID and a supplied Markdown density table provides material density. Use for scan-cleanup mass tasks requiring a JSON report.
---

# Binary STL main-part mass

Use `scripts/calculate_mass.py` to parse the runtime STL, discard disconnected debris by selecting the geometrically largest valid closed component, obtain that component's Material ID from its triangle attribute fields, and write the requested report.

The script uses only Python's standard library. It does not infer material from STL file order, triangle count, or header text.

## Input and output

The script receives one JSON object on standard input:

```json
{
  "stl_path": "/root/scan_data.stl",
  "density_table_path": "/root/material_density_table.md",
  "output_path": "/root/mass_report.json",
  "coordinate_unit": "mm",
  "verify": true
}
```

All paths are optional and default to the paths above. `coordinate_unit` is the unit represented by the unitless STL coordinates; supported values are `mm`, `cm`, `m`, and `in`. It defaults to `mm`, which is the usual binary-STL convention. Set it explicitly if task documentation establishes another coordinate unit.

The density table must contain a Markdown table with a Material-ID column and a Density column. The density header or value should state a supported unit: `g/mm3`, `g/cm3` (including `g/cm³`), `kg/m3`, `kg/mm3`, `g/ml`, or `kg/l`. A density with no stated unit is treated as `g/cm3`; this convention is only appropriate when the task documentation uses conventional material-table densities. Density is converted to grams per cubic millimetre before multiplication.

Run it with the supplied runtime, for example:

```sh
python3 scripts/calculate_mass.py <<'JSON'
{"stl_path":"/root/scan_data.stl","density_table_path":"/root/material_density_table.md","output_path":"/root/mass_report.json","coordinate_unit":"mm","verify":true}
JSON
```

It writes exactly this artifact schema to `output_path`:

```json
{"main_part_mass": 12345.67, "material_id": 42}
```

Its stdout is a JSON execution summary; it is not the report artifact.

## Method and validation

1. Validate the binary STL length and triangle count, then read each 50-byte triangle record as little-endian floats plus an unsigned 16-bit attribute value.
2. Build triangle connectivity from vertices. Vertices are considered coincident if their distance is within `max(1e-9, 1e-7 * max(bounding-box diagonal, largest coordinate magnitude))` in STL coordinate units. This scale-relative tolerance accommodates binary floating-point coordinate noise without relying on record ordering.
3. For each component, check that every snapped edge occurs exactly twice and with opposite directed uses. It computes signed tetrahedral volume using `sum(dot(v0, cross(v1, v2))/6)`, then takes its absolute value only after the winding check. The largest valid component is the one with greatest enclosed volume, not the most triangles.
4. Require one unambiguous attribute Material ID across the selected component, look up its density, convert both volume and density to compatible gram/mm³ units, and calculate `mass = volume * density`.
5. Atomically write the report. With `verify: true` (the default), reopen the report and independently reparse/recompute the inputs, checking the stored material ID and mass before successful completion.

Malformed STL data, open or inconsistently wound candidate surfaces, ambiguous component materials, absent density entries, unknown units, or non-finite calculations are explicit failures. Do not substitute a majority material ID or silently apply an unknown density unit.
