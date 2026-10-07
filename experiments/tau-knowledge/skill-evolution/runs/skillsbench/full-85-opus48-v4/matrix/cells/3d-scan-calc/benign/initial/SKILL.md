---
name: stl-mass-from-scan
description: >
  Compute the mass of a 3D-printed part from a binary STL scan where the per-triangle
  "Attribute Byte Count" field actually stores a Material ID. Parses the binary STL,
  isolates the largest connected component (filtering scanning debris), computes enclosed
  volume via a signed tetrahedral sum, reads the per-triangle Material ID, looks up the
  density in a markdown density table, applies unit conversion, and writes a mass_report.json.
  Use for tasks like "3d-scan-calc" that require mass = Volume * Density within tight tolerance.
---

# STL mass-from-scan Skill

## When to use
Use this Skill when you are given a binary STL scan plus a material density table and must
report the mass of the main part. The key non-standard detail: the 2-byte attribute field
at the end of each STL triangle record is repurposed to store a **Material ID** rather than
being unused.

## Method (assumptions documented)
Binary STL layout:
- 80-byte header (ignored).
- 4-byte little-endian uint32 triangle count.
- Per triangle (50 bytes): 12 little-endian float32 values (normal x,y,z then vertex1 x,y,z,
  vertex2 x,y,z, vertex3 x,y,z) followed by a 2-byte little-endian uint16 attribute. Here
  that uint16 is the Material ID of the triangle.

Steps performed by `scripts/compute_mass.py`:
1. Parse all triangles and their attribute (Material ID) values.
2. Build vertex connectivity by quantizing each vertex onto a grid whose cell size is
   `tol = max_bbox_extent * 1e-6` (a tolerance justified by the coordinate scale), then
   union triangles that share a quantized vertex (union-find). Disconnected scanning debris
   forms separate components.
3. Select the **largest connected component by triangle count** as the main part. The number
   of components and sizes are reported for inspection.
4. Compute the enclosed volume of that component via the signed tetrahedral sum
   `V = (1/6) * sum( v1 . (v2 x v3) )` over its triangles, taking the absolute value (robust
   to overall winding orientation).
5. Determine the part's Material ID as the most common attribute value among the main
   component's triangles.
6. Parse the markdown density table (`material_density_table.md`) to map Material ID -> density
   and detect the density unit string. Convert density to g/mm^3 so that
   `mass_grams = volume_mm3 * density_g_per_mm3`.
   Unit handling (see `references/units.md`):
   - `g/cm^3` (default assumption if unit is ambiguous) -> multiply by 1e-3.
   - `kg/m^3` -> multiply by 1e-6.
   - `g/mm^3` -> factor 1.
7. Write `/root/mass_report.json` with `main_part_mass` (rounded to 2 decimals) and
   `material_id` (int). Also returns volume, density, detected unit, and component stats on
   stdout for verification.

The STL coordinate unit is assumed to be millimetres (common for printed parts). If the
delivered answer is off by a clean power-of-ten factor, the mismatch is a unit assumption:
re-run with `--unit-density-override` / `density_unit` or `volume_scale` (see below) and the
reference notes, rather than changing the geometry logic.

## Running
The script reads a JSON object on stdin and writes a JSON object on stdout. It also writes the
output file. Example:

```bash
echo '{"stl_path":"/root/scan_data.stl",
       "density_table_path":"/root/material_density_table.md",
       "output_path":"/root/mass_report.json"}' | python3 /app/environment/skills/current/scripts/compute_mass.py
```

Optional stdin keys:
- `density_unit`: force the density unit (e.g. "g/cm^3", "kg/m^3", "g/mm^3").
- `volume_scale`: multiply computed volume by this factor if the STL unit is not mm
  (e.g. 1e3 if coordinates are in cm and you want mm^3).
- `mass_scale`: final multiplier on mass (default 1) if the report expects kg instead of g.
- `component_by`: "triangles" (default) or "volume" to pick the main component by |volume|.

Stdout schema:
```json
{"main_part_mass": <float>, "material_id": <int>, "volume_mm3": <float>,
 "density_raw": <float>, "density_unit": "...", "density_g_per_mm3": <float>,
 "num_components": <int>, "component_triangle_counts": [...], "main_component_triangles": <int>}
```

## Verification
After running, re-open `/root/mass_report.json`, confirm it has `main_part_mass` and
`material_id`, and sanity-check that `main_part_mass ≈ volume_mm3 * density_g_per_mm3`
(within rounding) using the stdout diagnostics. Independently recompute volume on a small
sample of triangles if needed. The task tolerance is 0.1%.

## Failure handling
- If the triangle count in the header disagrees with file length, the script falls back to
  deriving the count from the file size and warns on stdout (`warnings`).
- If the Material ID is not found in the density table, the script reports
  `density_raw=null` and lists available ids under `available_material_ids` so the executor
  can resolve the mapping manually.
- If the file is an ASCII STL (starts with "solid " and lacks binary structure), the script
  reports an error; this task supplies a binary STL.
