"""CIF Wyckoff-position summary using the coordinates of the parsed CIF cell.

The public entry point is
``analyze_wyckoff_position_multiplicities_and_coordinates(filepath)``.
It requires pymatgen, which supplies robust CIF parsing and spglib-backed symmetry
analysis. No result is specialized to a particular filename or composition.
"""
from __future__ import annotations

from fractions import Fraction
from math import isfinite
from pathlib import Path
from typing import Any


_MAX_DENOMINATOR = 12
# Appropriate for typical experimentally reported CIF coordinates while avoiding
# accidental merging of clearly distinct sites.
_SYMPREC = 0.01
_ANGLE_TOLERANCE = 5.0


def _rational_string(value: Any, max_denominator: int = _MAX_DENOMINATOR) -> str:
    """Return the nearest bounded-denominator rational for one source coordinate."""
    number = float(value)
    if not isfinite(number):
        raise ValueError("fractional coordinate is not finite")
    # str(float) avoids Fraction's exact binary representation while retaining
    # the parsed source value.  No modulo operation is done deliberately.
    rational = Fraction(str(number)).limit_denominator(max_denominator)
    if rational.denominator == 1:
        return str(rational.numerator)
    return f"{rational.numerator}/{rational.denominator}"


def _load_source_structure(filepath: str):
    """Parse exactly one CIF structure without primitive/standard-cell conversion."""
    from pymatgen.io.cif import CifParser

    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"CIF file does not exist: {filepath}")

    parser = CifParser(str(path))
    # primitive=False is important: equivalent-group sizes and representative
    # coordinates must refer to the input's parsed cell and site ordering.
    try:
        structures = parser.parse_structures(primitive=False)
    except AttributeError:
        # Compatibility with older pymatgen releases.
        structures = parser.get_structures(primitive=False)
    if len(structures) != 1:
        raise ValueError(f"expected exactly one structure in CIF, found {len(structures)}")
    structure = structures[0]
    if len(structure) == 0:
        raise ValueError("CIF contains no atomic sites")
    return structure


def _orbit_records(structure):
    """Return (first-original-index, letter, represented-site-count) records."""
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    analyzer = SpacegroupAnalyzer(
        structure, symprec=_SYMPREC, angle_tolerance=_ANGLE_TOLERANCE
    )
    symmetrized = analyzer.get_symmetrized_structure()
    groups = list(symmetrized.equivalent_indices)
    # pymatgen supplies one Wyckoff letter per parsed site, whereas
    # ``equivalent_indices`` contains one list per orbit.  Associate an orbit
    # with its first parsed-site letter and require all of its members to agree.
    site_letters = list(symmetrized.wyckoff_letters)
    if len(site_letters) != len(structure):
        raise ValueError("symmetry analysis returned a Wyckoff letter count that does not match parsed sites")

    seen: set[int] = set()
    records = []
    for indices in groups:
        site_indices = [int(index) for index in indices]
        if not site_indices:
            raise ValueError("symmetry analysis returned an empty orbit")
        if any(index < 0 or index >= len(structure) for index in site_indices):
            raise ValueError("symmetry analysis returned an invalid site index")
        overlap = seen.intersection(site_indices)
        if overlap:
            raise ValueError("symmetry orbits overlap in parsed site indices")
        seen.update(site_indices)
        orbit_letters = {str(site_letters[index]).strip() for index in site_indices}
        if len(orbit_letters) != 1 or not next(iter(orbit_letters)):
            raise ValueError("symmetry orbit has missing or inconsistent Wyckoff letters")
        normalized_letter = next(iter(orbit_letters))
        records.append((min(site_indices), normalized_letter, len(site_indices)))

    if seen != set(range(len(structure))):
        raise ValueError("symmetry orbits do not account for every parsed site")
    return sorted(records, key=lambda item: item[0])


def analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> dict[str, Any]:
    """Summarize a CIF's Wyckoff letters using original parsed-site coordinates.

    On success returns keys ``wyckoff_multiplicity_dict`` and
    ``wyckoff_coordinates_dict``.  Repeated inequivalent orbits with one letter
    are reduced to one letter entry by summing their parsed-site multiplicities;
    the coordinates are those of the first original site among those orbits.
    On failure returns an ``error`` dictionary and never returns a partial
    summary.
    """
    try:
        if not isinstance(filepath, str) or not filepath:
            raise ValueError("filepath must be a nonempty string")
        structure = _load_source_structure(filepath)
        multiplicities: dict[str, int] = {}
        coordinates: dict[str, list[str]] = {}

        for first_index, letter, orbit_size in _orbit_records(structure):
            multiplicities[letter] = multiplicities.get(letter, 0) + orbit_size
            if letter not in coordinates:
                source_coordinates = structure[first_index].frac_coords
                coordinates[letter] = [
                    _rational_string(component) for component in source_coordinates
                ]

        if sum(multiplicities.values()) != len(structure):
            raise ValueError("reduced multiplicities do not reconcile with parsed sites")
        if set(multiplicities) != set(coordinates):
            raise ValueError("multiplicity and coordinate Wyckoff keys differ")
        return {
            "wyckoff_multiplicity_dict": multiplicities,
            "wyckoff_coordinates_dict": coordinates,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _main() -> int:
    """Optional command-line interface for checking one CIF result as JSON."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Summarize CIF Wyckoff multiplicities and representative coordinates."
    )
    parser.add_argument("filepath", help="path to one CIF file")
    args = parser.parse_args()
    print(json.dumps(analyze_wyckoff_position_multiplicities_and_coordinates(args.filepath)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
