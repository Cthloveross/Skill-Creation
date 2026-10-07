---
name: binary-stl-main-part-mass
description: Parse a binary STL whose per-facet attribute word is a material ID, discard disconnected scan debris by geometric connectivity, calculate the largest closed part's mass from a supplied density table, and write the required JSON report.
---

# Binary STL main-part mass

Use this Skill when a binary STL contains one printable object plus disconnected debris and its two-byte attribute field identifies the material. It uses only the Python standard library.

## Method

1. Read the STL as binary: skip its 80-byte header, decode the little-endian triangle count, and decode exactly one 50-byte record per triangle. The final unsigned 16-bit word in every record is retained as the material ID.
2. Build triangle connectivity from runtime vertex coordinates. Vertices within a scale-relative tolerance are treated as shared; triangles sharing a canonicalized vertex are connected. This does not rely on record order or triangle count.
3. Measure each component geometrically. A watertight component is ranked by its enclosed absolute signed-tetrahedral volume. Non-watertight candidates receive only a bounding-box fallback metric, which helps reject small scan fragments but cannot be used for the delivered volume.
4. Require the selected component to be a closed, consistently oriented triangle surface. Its volume is the absolute value of the signed tetrahedral sum. A globally reversed winding is therefore harmless; mixed winding, open edges, and non-manifold edges are reported as errors rather than silently producing an unreliable mass.
5. Determine the component material from its facet attributes. All facets must agree, except that a clear strict majority is accepted to tolerate a small number of corrupted scan records.
6. Look up that ID in the density document and multiply the volume in compatible units by its numeric density. Binary STL has no unit declaration. For density in g/cm³, convert cubic millimetres to cm³ by dividing by 1000; the entrypoint therefore defaults to `coordinate_unit: "mm"`, appropriate for ordinary 3D-print scan data. Set `coordinate_unit` to `cm` or `m` only when the supplied scan documentation establishes that unit.

## Execution

Run the entrypoint with a JSON object on standard input. It writes the report to `output_path` and emits the same report JSON on standard output.

```json
{
  "stl_path": "/path/to/scan.stl",
  "density_table_path": "/path/to/material_density_table.md",
  "output_path": "/path/to/mass_report.json",
  "coordinate_unit": "mm"
}
```

For the task paths, invoke `python3 scripts/create_mass_report.py` and provide those three paths in the JSON input. `tolerance` is optional; when omitted, the script derives it as one millionth of the STL bounding-box diagonal (with a small absolute floor). Supply a smaller explicit positive tolerance only if the input documentation establishes a more appropriate coordinate precision.

The density parser supports Markdown tables with a `Material ID`/`ID` column and a `Density` column, including ordinary inline Markdown decoration such as `**42**`, and common labelled text rows such as `Material ID: ... Density: ...`. It rejects ambiguous or missing matches. `coordinate_unit` may be `mm`, `cm`, or `m`; the mass is in the density table's mass unit when its density volume unit is cm³.

## Validation and failure handling

A successful report is a UTF-8 JSON object with exactly `main_part_mass` (finite nonnegative number) and `material_id` (integer). The entrypoint reopens the report after writing and validates this schema. It exits nonzero with a descriptive error if the STL is truncated or not binary-layout-consistent, there are no usable triangles, the selected object is not watertight/orientable, its attributes do not identify one material, or the density table lacks one unambiguous density for that material.
