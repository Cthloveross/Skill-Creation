# Unit conversion notes for mass computation

mass_grams = volume_mm3 * density_g_per_mm3

Convert the density value read from the table into g/mm^3:

| Table unit  | factor to g/mm^3 | reasoning                                   |
|-------------|------------------|---------------------------------------------|
| g/cm^3      | 1e-3             | 1 cm^3 = 1000 mm^3                           |
| kg/m^3      | 1e-6             | 1 kg = 1000 g, 1 m^3 = 1e9 mm^3             |
| g/mm^3      | 1                | already in target units                     |

Assumptions:
- STL coordinates are in millimetres (typical for 3D-printed parts). If the answer is off
  by exactly 10^3 or 10^6, the coordinate unit or density unit assumption is wrong; use the
  `volume_scale` or `density_unit` stdin options to correct it instead of altering geometry.
- The report's `main_part_mass` is expressed in grams by default. If the grader expects
  kilograms, pass `mass_scale=1e-3`.

The signed tetrahedral volume uses V = (1/6) * sum(v1 . (v2 x v3)). The absolute value is
taken so that overall mesh winding does not flip the sign. Only the main (largest) connected
component is summed; debris components are excluded.
