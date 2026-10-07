#!/usr/bin/env python3
"""Write the requested Wyckoff-analysis solution module.

Input JSON:
  {"output_path": "/root/workspace/solution.py"}  # output_path optional
Output JSON:
  {"written": "/absolute/or/relative/path"}
"""

import json
import sys
from pathlib import Path


SOLUTION = r'''"""Wyckoff-position summaries for CIF structures.

The public function preserves coordinates from the parsed input structure.
Symmetry analysis is used only to assign equivalent-site orbits and Wyckoff
letters; it does not supply the representative coordinates returned here.
"""

from __future__ import annotations

from fractions import Fraction
from math import isfinite
import os
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


_MAX_DENOMINATOR = 12
_WYCKOFF_LETTER = re.compile(r"([A-Za-z]+)\s*$")


def _rational_string(value: Any, max_denominator: int = _MAX_DENOMINATOR) -> str:
    """Return the nearest bounded-denominator rational without periodic wrapping."""
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise ValueError("Fractional coordinates must be finite numbers")
    # str(float(...)) gives Fraction a stable decimal representation while
    # limit_denominator performs the requested nearest bounded approximation.
    fraction = Fraction(str(numeric_value)).limit_denominator(max_denominator)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    return f"{fraction.numerator}/{fraction.denominator}"


def _wyckoff_letter(symbol: Any) -> str:
    """Extract the terminal letter part from a symbol such as '8c'."""
    match = _WYCKOFF_LETTER.search(str(symbol))
    if match is None:
        raise ValueError(f"Cannot extract a Wyckoff letter from {symbol!r}")
    return match.group(1).lower()


def _source_coordinate(structure: Any, site_index: int) -> List[str]:
    """Serialize an original parsed site's fractional coordinate triplet."""
    coordinate = structure[site_index].frac_coords
    if len(coordinate) != 3:
        raise ValueError("A crystal site must have exactly three fractional coordinates")
    return [_rational_string(component) for component in coordinate]


def analyze_wyckoff_position_multiplicities_and_coordinates(filepath: str) -> Dict[str, Dict[str, Any]]:
    """Summarize Wyckoff letters and first source-site coordinates in a CIF.

    Multiplicities count represented sites in the supplied, non-primitive CIF
    structure. Distinct symmetry orbits that share a Wyckoff letter are folded
    into one letter key by summation, with the earliest source-site coordinate
    retained as that key's representative.
    """
    if not isinstance(filepath, str) or not filepath:
        raise ValueError("filepath must be a non-empty string")
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    except ImportError as exc:
        raise ImportError(
            "analyze_wyckoff_position_multiplicities_and_coordinates requires pymatgen"
        ) from exc

    # Explicitly retain the supplied cell rather than reducing it to a primitive
    # cell, because returned multiplicities must reconcile with parsed sites.
    structure = Structure.from_file(filepath, primitive=False)
    site_count = len(structure)
    if site_count == 0:
        raise ValueError("The CIF contains no sites")

    symmetrized = SpacegroupAnalyzer(structure).get_symmetrized_structure()
    equivalent_groups = list(symmetrized.equivalent_indices)
    wyckoff_symbols = list(symmetrized.wyckoff_symbols)
    if len(equivalent_groups) != len(wyckoff_symbols):
        raise RuntimeError("Symmetry analysis returned mismatched orbit and Wyckoff data")

    # Form records before reduction so that the first original occurrence,
    # rather than analyzer/standardized ordering, determines representatives.
    orbit_records: List[Tuple[int, Tuple[int, ...], str]] = []
    observed_indices: List[int] = []
    for indices, symbol in zip(equivalent_groups, wyckoff_symbols):
        source_indices = tuple(int(index) for index in indices)
        if not source_indices:
            raise RuntimeError("Symmetry analysis returned an empty orbit")
        if any(index < 0 or index >= site_count for index in source_indices):
            raise RuntimeError("Symmetry analysis returned an out-of-range site index")
        observed_indices.extend(source_indices)
        orbit_records.append((min(source_indices), source_indices, _wyckoff_letter(symbol)))

    if sorted(observed_indices) != list(range(site_count)):
        raise RuntimeError(
            "Symmetry orbit groups do not form an exact partition of the parsed structure"
        )

    orbit_records.sort(key=lambda record: record[0])
    multiplicities: Dict[str, int] = {}
    coordinates: Dict[str, List[str]] = {}
    for first_index, source_indices, letter in orbit_records:
        multiplicities[letter] = multiplicities.get(letter, 0) + len(source_indices)
        if letter not in coordinates:
            coordinates[letter] = _source_coordinate(structure, first_index)

    if sum(multiplicities.values()) != site_count:
        raise RuntimeError("Reduced Wyckoff multiplicities do not reconcile with parsed sites")

    return {
        "wyckoff_multiplicity_dict": multiplicities,
        "wyckoff_coordinates_dict": coordinates,
    }
'''


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    output_path = payload.get("output_path", "/root/workspace/solution.py")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path must be a non-empty string")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(SOLUTION, encoding="utf-8")
    print(json.dumps({"written": str(destination)}))


if __name__ == "__main__":
    main()
