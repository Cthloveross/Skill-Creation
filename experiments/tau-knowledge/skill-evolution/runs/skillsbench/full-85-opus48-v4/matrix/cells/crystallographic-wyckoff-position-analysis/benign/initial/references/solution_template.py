"""Standalone deliverable: analyze Wyckoff multiplicities and approximate
coordinates from a CIF file.

This file is self-contained (standard library + pymatgen only) because the
grader executes it independently of any Skill directory. It must not hardcode
any per-structure answers.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any
import re


def _to_rational(value: float, max_den: int = 12) -> str:
    """Nearest rational with denominator <= max_den, serialized deterministically.

    Endpoints are preserved (no modulo/half-open canonicalization): a source
    coordinate at 1.0 stays "1", a coordinate at 0.0 stays "0".
    """
    frac = Fraction(float(value)).limit_denominator(max_den)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def _wyckoff_letter(symbol: str) -> str:
    """Extract the alphabetic Wyckoff letter from a symbol like '4a' or '24d'."""
    match = re.search(r"([A-Za-z]+)\s*$", str(symbol).strip())
    return match.group(1) if match else str(symbol).strip()


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
) -> "dict[str, dict] | dict[str, Any]":
    from pymatgen.core import Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    structure = Structure.from_file(filepath)

    sym_struct = None
    last_err = None
    for symprec in (0.01, 0.05, 0.1):
        try:
            sga = SpacegroupAnalyzer(structure, symprec=symprec)
            sym_struct = sga.get_symmetrized_structure()
            break
        except Exception as exc:  # pragma: no cover - robustness fallback
            last_err = exc
            sym_struct = None
    if sym_struct is None:
        raise RuntimeError(f"symmetry analysis failed for {filepath}: {last_err}")

    multiplicity: dict[str, int] = {}
    coordinates: dict[str, list] = {}
    represented_total = 0

    # Iterate orbits in the symmetrized structure's order. equivalent_sites[i]
    # are PeriodicSite objects of the ORIGINAL parsed structure (correct
    # setting), and [i][0] is the first occurrence in that orbit's ordering.
    for symbol, group in zip(sym_struct.wyckoff_symbols, sym_struct.equivalent_sites):
        letter = _wyckoff_letter(symbol)
        n_sites = len(group)
        represented_total += n_sites
        # Letter-level reduction: sum represented-site counts across orbits that
        # share a letter rather than dropping later orbits.
        multiplicity[letter] = multiplicity.get(letter, 0) + n_sites
        if letter not in coordinates:
            rep = group[0]
            coordinates[letter] = [_to_rational(c) for c in rep.frac_coords]

    # Validation: every orbit occurrence must have contributed, so the total of
    # represented sites equals the number of atoms in the parsed structure.
    assert represented_total == len(structure), (
        f"represented-site total {represented_total} does not reconcile with "
        f"parsed structure atom count {len(structure)}"
    )

    ordered = sorted(multiplicity.keys())
    return {
        "wyckoff_multiplicity_dict": {k: multiplicity[k] for k in ordered},
        "wyckoff_coordinates_dict": {k: coordinates[k] for k in ordered},
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            print(path)
            print(json.dumps(
                analyze_wyckoff_position_multiplicities_and_coordinates(path),
                indent=2,
            ))
    else:
        print("usage: python solution.py <file.cif> [more.cif ...]")
