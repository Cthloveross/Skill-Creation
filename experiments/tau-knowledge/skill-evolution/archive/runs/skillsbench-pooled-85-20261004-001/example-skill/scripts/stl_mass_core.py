#!/usr/bin/env python3
"""Core helpers for calculating mass from binary STL material attributes.

The public entrypoint scripts read JSON on stdin and emit JSON on stdout. This
module contains deterministic mesh, density-table, and report-writing logic.
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Triangle = Tuple[Vec3, Vec3, Vec3]


class STLParseError(ValueError):
    pass


class DensityParseError(ValueError):
    pass


@dataclass
class DensityEntry:
    material_id: int
    value: float
    unit_text: str
    source: str


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def triangle_area(tri: Triangle) -> float:
    a, b, c = tri
    return 0.5 * norm(cross(vsub(b, a), vsub(c, a)))


def signed_tetra_volume(tri: Triangle, ref: Vec3) -> float:
    a, b, c = tri
    ar = vsub(a, ref)
    br = vsub(b, ref)
    cr = vsub(c, ref)
    return dot(ar, cross(br, cr)) / 6.0


def bbox_of_points(points: Iterable[Vec3]) -> Tuple[Vec3, Vec3]:
    pts = list(points)
    if not pts:
        raise ValueError("cannot compute bounding box of empty point set")
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])


def bbox_diagonal(bmin: Vec3, bmax: Vec3) -> float:
    return norm(vsub(bmax, bmin))


def bbox_center(bmin: Vec3, bmax: Vec3) -> Vec3:
    return ((bmin[0] + bmax[0]) / 2.0, (bmin[1] + bmax[1]) / 2.0, (bmin[2] + bmax[2]) / 2.0)


def parse_binary_stl(path: str) -> Tuple[bytes, List[Triangle], List[int]]:
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 84:
        raise STLParseError(f"STL file is too small for a binary STL: {path}")
    header = data[:80]
    tri_count = struct.unpack("<I", data[80:84])[0]
    expected = 84 + 50 * tri_count
    if len(data) != expected:
        raise STLParseError(
            f"binary STL size mismatch: header count={tri_count}, expected {expected} bytes, found {len(data)} bytes"
        )
    triangles: List[Triangle] = []
    attrs: List[int] = []
    off = 84
    for _ in range(tri_count):
        rec = data[off : off + 50]
        vals = struct.unpack("<12f", rec[:48])
        tri = (
            (float(vals[3]), float(vals[4]), float(vals[5])),
            (float(vals[6]), float(vals[7]), float(vals[8])),
            (float(vals[9]), float(vals[10]), float(vals[11])),
        )
        attr = struct.unpack("<H", rec[48:50])[0]
        triangles.append(tri)
        attrs.append(int(attr))
        off += 50
    return header, triangles, attrs


def auto_weld_tolerance(triangles: Sequence[Triangle]) -> float:
    points = [p for tri in triangles for p in tri]
    bmin, bmax = bbox_of_points(points)
    diag = bbox_diagonal(bmin, bmax)
    max_abs = max(max(abs(coord) for coord in p) for p in points) if points else 0.0
    # Relative to model scale, with a small absolute floor for float32 STL data.
    return max(diag * 1.0e-6, max_abs * 1.0e-8, 1.0e-9)


def weld_vertices(triangles: Sequence[Triangle], tolerance: float) -> Tuple[List[Tuple[int, int, int]], List[Vec3]]:
    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be a finite non-negative number")

    tri_vids: List[Tuple[int, int, int]] = []
    welded: List[Vec3] = []

    if tolerance == 0:
        exact: Dict[Vec3, int] = {}
        for tri in triangles:
            ids = []
            for p in tri:
                if p not in exact:
                    exact[p] = len(welded)
                    welded.append(p)
                ids.append(exact[p])
            tri_vids.append((ids[0], ids[1], ids[2]))
        return tri_vids, welded

    cell_size = tolerance
    grid: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    tol2 = tolerance * tolerance

    def cell_key(p: Vec3) -> Tuple[int, int, int]:
        return (
            math.floor(p[0] / cell_size),
            math.floor(p[1] / cell_size),
            math.floor(p[2] / cell_size),
        )

    for tri in triangles:
        ids: List[int] = []
        for p in tri:
            ck = cell_key(p)
            found: Optional[int] = None
            for dx in (-1, 0, 1):
                if found is not None:
                    break
                for dy in (-1, 0, 1):
                    if found is not None:
                        break
                    for dz in (-1, 0, 1):
                        for vid in grid.get((ck[0] + dx, ck[1] + dy, ck[2] + dz), []):
                            q = welded[vid]
                            d = vsub(p, q)
                            if dot(d, d) <= tol2:
                                found = vid
                                break
                        if found is not None:
                            break
            if found is None:
                found = len(welded)
                welded.append(p)
                grid[ck].append(found)
            ids.append(found)
        tri_vids.append((ids[0], ids[1], ids[2]))
    return tri_vids, welded


def connected_components(tri_vids: Sequence[Tuple[int, int, int]]) -> List[List[int]]:
    n = len(tri_vids)
    uf = UnionFind(n)
    owner: Dict[int, int] = {}
    for ti, vids in enumerate(tri_vids):
        for vid in set(vids):
            if vid in owner:
                uf.union(ti, owner[vid])
            else:
                owner[vid] = ti
    groups: Dict[int, List[int]] = defaultdict(list)
    for ti in range(n):
        groups[uf.find(ti)].append(ti)
    return sorted(groups.values(), key=lambda g: min(g))


def orientation_and_volume(
    triangles: Sequence[Triangle],
    tri_vids: Sequence[Tuple[int, int, int]],
    component: Sequence[int],
) -> Dict[str, object]:
    points = [p for ti in component for p in triangles[ti]]
    bmin, bmax = bbox_of_points(points)
    ref = bbox_center(bmin, bmax)

    edge_map: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)
    degenerate_edge_refs = 0
    for ti in component:
        a, b, c = tri_vids[ti]
        for u, v in ((a, b), (b, c), (c, a)):
            if u == v:
                degenerate_edge_refs += 1
                continue
            key = (u, v) if u < v else (v, u)
            sign = 1 if (u, v) == key else -1
            edge_map[key].append((ti, sign))

    boundary_edges = sum(1 for inc in edge_map.values() if len(inc) == 1)
    nonmanifold_edges = sum(1 for inc in edge_map.values() if len(inc) > 2)
    watertight = boundary_edges == 0 and nonmanifold_edges == 0 and degenerate_edge_refs == 0

    adjacency: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for inc in edge_map.values():
        if len(inc) >= 2:
            base_t, base_sign = inc[0]
            for other_t, other_sign in inc[1:]:
                # If original edge directions match, exactly one face must be flipped.
                xor_flip = 1 if base_sign == other_sign else 0
                adjacency[base_t].append((other_t, xor_flip))
                adjacency[other_t].append((base_t, xor_flip))

    flip: Dict[int, int] = {}
    orient_group: Dict[int, int] = {}
    conflicts = 0
    group_id = 0
    comp_set = set(component)
    for start in component:
        if start in flip:
            continue
        flip[start] = 0
        orient_group[start] = group_id
        q: deque[int] = deque([start])
        while q:
            cur = q.popleft()
            for nb, xor_flip in adjacency.get(cur, []):
                if nb not in comp_set:
                    continue
                wanted = flip[cur] ^ xor_flip
                if nb in flip:
                    if flip[nb] != wanted:
                        conflicts += 1
                else:
                    flip[nb] = wanted
                    orient_group[nb] = group_id
                    q.append(nb)
        group_id += 1

    raw_signed = 0.0
    repaired_signed_total = 0.0
    repaired_by_group: Dict[int, float] = defaultdict(float)
    for ti in component:
        tri = triangles[ti]
        raw_signed += signed_tetra_volume(tri, ref)
        if flip.get(ti, 0):
            repaired_tri = (tri[0], tri[2], tri[1])
        else:
            repaired_tri = tri
        vol = signed_tetra_volume(repaired_tri, ref)
        repaired_signed_total += vol
        repaired_by_group[orient_group.get(ti, 0)] += vol

    repaired_abs_sum = sum(abs(v) for v in repaired_by_group.values())
    return {
        "bbox_min": list(bmin),
        "bbox_max": list(bmax),
        "bbox_diagonal": bbox_diagonal(bmin, bmax),
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "degenerate_edge_refs": degenerate_edge_refs,
        "watertight": watertight,
        "orientation_conflicts": conflicts,
        "orientation_groups": group_id,
        "raw_signed_volume": raw_signed,
        "repaired_signed_volume": repaired_signed_total,
        "repaired_abs_volume": repaired_abs_sum,
    }


def analyze_components(
    triangles: Sequence[Triangle],
    attrs: Sequence[int],
    tolerance: Optional[float] = None,
) -> Dict[str, object]:
    if not triangles:
        raise ValueError("STL contains no triangles")
    tol = auto_weld_tolerance(triangles) if tolerance is None else float(tolerance)
    tri_vids, welded = weld_vertices(triangles, tol)
    comps = connected_components(tri_vids)

    stats: List[Dict[str, object]] = []
    for ci, comp in enumerate(comps):
        area = sum(triangle_area(triangles[ti]) for ti in comp)
        orient = orientation_and_volume(triangles, tri_vids, comp)
        mat_counts = Counter(int(attrs[ti]) for ti in comp)
        st: Dict[str, object] = {
            "component_index": ci,
            "triangle_count": len(comp),
            "surface_area": area,
            "material_counts": dict(sorted(mat_counts.items())),
            "triangle_indices_sample": comp[:10],
        }
        st.update(orient)
        stats.append(st)

    if not stats:
        raise ValueError("no connected components found")

    watertight_with_volume = [
        st
        for st in stats
        if bool(st["watertight"]) and math.isfinite(float(st["repaired_abs_volume"])) and float(st["repaired_abs_volume"]) > 0.0
    ]
    if watertight_with_volume:
        selected = max(
            watertight_with_volume,
            key=lambda st: (float(st["repaired_abs_volume"]), float(st["surface_area"]), float(st["bbox_diagonal"])),
        )
        selection_basis = "largest_watertight_repaired_abs_volume"
    else:
        selected = max(stats, key=lambda st: (float(st["surface_area"]), float(st["bbox_diagonal"])))
        selection_basis = "largest_surface_area_no_watertight_volume_available"

    return {
        "tolerance": tol,
        "welded_vertex_count": len(welded),
        "component_count": len(stats),
        "components": stats,
        "selected_component_index": int(selected["component_index"]),
        "selection_basis": selection_basis,
        "selected_component": selected,
    }


_NUM_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_INT_RE = re.compile(r"[-+]?\d+")


def _parse_number(text: str) -> Optional[float]:
    m = _NUM_RE.search(text.replace(",", ""))
    return float(m.group(0)) if m else None


def _parse_int(text: str) -> Optional[int]:
    m = _INT_RE.search(text.replace(",", ""))
    return int(m.group(0)) if m else None


def _split_md_row(line: str) -> Optional[List[str]]:
    if "|" not in line:
        return None
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def _is_separator_row(cells: Sequence[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{2,}:?", c.strip()) or c.strip() == "" for c in cells)


def parse_density_table(path: str) -> Dict[int, DensityEntry]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    entries: Dict[int, DensityEntry] = {}

    def add_entry(mid: Optional[int], val: Optional[float], unit_text: str, source: str) -> None:
        if mid is None or val is None:
            return
        if not math.isfinite(val):
            return
        new = DensityEntry(int(mid), float(val), unit_text.strip(), source)
        old = entries.get(new.material_id)
        if old is not None and not math.isclose(old.value, new.value, rel_tol=1e-12, abs_tol=1e-12):
            raise DensityParseError(
                f"conflicting densities for material ID {new.material_id}: {old.value} ({old.source}) vs {new.value} ({source})"
            )
        entries[new.material_id] = new

    lines = text.splitlines()

    # Markdown pipe tables with identifiable headers.
    i = 0
    while i < len(lines):
        row = _split_md_row(lines[i])
        if row is None:
            i += 1
            continue
        block: List[List[str]] = []
        while i < len(lines):
            r = _split_md_row(lines[i])
            if r is None:
                break
            block.append(r)
            i += 1
        if not block:
            continue

        header = block[0]
        data_start = 1
        if len(block) > 1 and _is_separator_row(block[1]):
            data_start = 2
        header_l = [h.lower() for h in header]
        id_idx = None
        dens_idx = None
        for idx, h in enumerate(header_l):
            if id_idx is None and (("material" in h and "id" in h) or re.fullmatch(r"id", h.strip())):
                id_idx = idx
            if dens_idx is None and "dens" in h:
                dens_idx = idx
        if id_idx is None:
            for idx, h in enumerate(header_l):
                if "id" in h:
                    id_idx = idx
                    break
        if dens_idx is None:
            for idx, h in enumerate(header_l):
                if any(token in h for token in ("rho", "specific gravity")):
                    dens_idx = idx
                    break
        if id_idx is not None and dens_idx is not None:
            density_header = header[dens_idx]
            for row_cells in block[data_start:]:
                if _is_separator_row(row_cells):
                    continue
                if id_idx >= len(row_cells) or dens_idx >= len(row_cells):
                    continue
                add_entry(
                    _parse_int(row_cells[id_idx]),
                    _parse_number(row_cells[dens_idx]),
                    density_header + " " + row_cells[dens_idx],
                    "markdown table row: " + " | ".join(row_cells),
                )

    # Labeled free-form lines: Material ID ... Density ...
    for line in lines:
        l = line.strip()
        if not l or _is_separator_row([l]):
            continue
        id_match = re.search(r"(?:material\s*id|\bid\b)\s*[:=#-]?\s*(\d+)", l, flags=re.I)
        dens_match = re.search(
            r"(?:density|\brho\b|specific\s+gravity)\s*[:=#-]?\s*(" + _NUM_RE.pattern + r")",
            l,
            flags=re.I,
        )
        if id_match and dens_match:
            add_entry(int(id_match.group(1)), float(dens_match.group(1)), l, "labeled line: " + l)

    # Generic non-header rows with at least two numeric values. This catches simple lists.
    if not entries:
        for line in lines:
            l = line.strip()
            if not l or set(l) <= set("-|: "):
                continue
            nums = _NUM_RE.findall(l.replace(",", ""))
            if len(nums) >= 2:
                mid_text = nums[0]
                try:
                    mid = int(float(mid_text))
                except ValueError:
                    continue
                val = float(nums[1])
                add_entry(mid, val, l, "generic numeric line: " + l)

    if not entries:
        raise DensityParseError(f"could not parse any material densities from {path}")
    return entries


def detect_density_unit(unit_text: str) -> Tuple[Optional[str], Optional[str], str]:
    """Return (mass_unit, length_unit, normalized_description)."""
    s = unit_text.lower()
    s = s.replace("³", "3").replace("㎥", "m3")
    s = s.replace("cubic centimetre", "cm3").replace("cubic centimeter", "cm3")
    s = s.replace("cubic millimetre", "mm3").replace("cubic millimeter", "mm3")
    s = s.replace("cubic metre", "m3").replace("cubic meter", "m3")
    s = s.replace("grams", "g").replace("gram", "g")
    s = s.replace("kilograms", "kg").replace("kilogram", "kg")
    s = s.replace("milligrams", "mg").replace("milligram", "mg")
    s = re.sub(r"\s+", " ", s)

    patterns = [
        ("kg", "m", r"kg\s*(?:/|per)\s*m\s*(?:\^?3|\*\*3|3)?"),
        ("kg", "cm", r"kg\s*(?:/|per)\s*cm\s*(?:\^?3|\*\*3|3)?"),
        ("kg", "mm", r"kg\s*(?:/|per)\s*mm\s*(?:\^?3|\*\*3|3)?"),
        ("g", "cm", r"\bg\s*(?:/|per)\s*cm\s*(?:\^?3|\*\*3|3)?"),
        ("g", "mm", r"\bg\s*(?:/|per)\s*mm\s*(?:\^?3|\*\*3|3)?"),
        ("g", "m", r"\bg\s*(?:/|per)\s*m\s*(?:\^?3|\*\*3|3)?"),
        ("mg", "mm", r"mg\s*(?:/|per)\s*mm\s*(?:\^?3|\*\*3|3)?"),
        ("lb", "in", r"lb\s*(?:/|per)\s*(?:in|inch|inches)\s*(?:\^?3|\*\*3|3)?"),
    ]
    for mass, length, pat in patterns:
        if re.search(pat, s):
            return mass, length, f"{mass}/{length}^3"

    # Header may contain only the denominator, e.g. "Density (per cm^3)".
    length_only_patterns = [
        ("cm", r"(?:/|per)\s*cm\s*(?:\^?3|\*\*3|3)?|cm\s*(?:\^?3|\*\*3|3)"),
        ("mm", r"(?:/|per)\s*mm\s*(?:\^?3|\*\*3|3)?|mm\s*(?:\^?3|\*\*3|3)"),
        ("m", r"(?:/|per)\s*m\s*(?:\^?3|\*\*3|3)?|\bm\s*(?:\^?3|\*\*3|3)"),
    ]
    mass_unit = None
    if re.search(r"\bkg\b", s):
        mass_unit = "kg"
    elif re.search(r"\bmg\b", s):
        mass_unit = "mg"
    elif re.search(r"\bg\b", s):
        mass_unit = "g"
    elif re.search(r"\blb\b", s):
        mass_unit = "lb"
    for length, pat in length_only_patterns:
        if re.search(pat, s):
            return mass_unit, length, (f"{mass_unit or 'mass'}/{length}^3")

    return mass_unit, None, mass_unit or "unitless"


_LENGTH_TO_M = {
    "m": 1.0,
    "meter": 1.0,
    "metre": 1.0,
    "cm": 1.0e-2,
    "centimeter": 1.0e-2,
    "centimetre": 1.0e-2,
    "mm": 1.0e-3,
    "millimeter": 1.0e-3,
    "millimetre": 1.0e-3,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
}

_MASS_TO_KG = {
    "kg": 1.0,
    "g": 1.0e-3,
    "mg": 1.0e-6,
    "lb": 0.45359237,
}


def convert_density_to_stl_units(
    entry: DensityEntry,
    stl_length_unit: str = "mm",
    density_conversion: str = "auto",
    output_mass_unit: str = "same",
) -> Tuple[float, Dict[str, object]]:
    if density_conversion not in ("auto", "none"):
        raise ValueError("density_conversion must be 'auto' or 'none'")
    mass_unit, density_length_unit, normalized = detect_density_unit(entry.unit_text)
    stl_unit_norm = (stl_length_unit or "raw").lower()

    factor = 1.0
    conversion_note = "density used exactly as listed"
    if density_conversion == "auto" and density_length_unit and stl_unit_norm != "raw":
        if stl_unit_norm not in _LENGTH_TO_M:
            raise ValueError(f"unsupported stl_length_unit for density conversion: {stl_length_unit}")
        if density_length_unit not in _LENGTH_TO_M:
            raise ValueError(f"unsupported density length unit: {density_length_unit}")
        factor = (_LENGTH_TO_M[stl_unit_norm] / _LENGTH_TO_M[density_length_unit]) ** 3
        conversion_note = f"converted density from per {density_length_unit}^3 to per {stl_unit_norm}^3"

    density_per_stl_unit = entry.value * factor
    mass_factor = 1.0
    out_unit = output_mass_unit.lower() if output_mass_unit else "same"
    if out_unit != "same":
        if not mass_unit:
            raise ValueError("cannot convert output mass unit because density mass unit was not detected")
        if mass_unit not in _MASS_TO_KG or out_unit not in _MASS_TO_KG:
            raise ValueError(f"unsupported output_mass_unit conversion: {mass_unit} to {output_mass_unit}")
        mass_factor = _MASS_TO_KG[mass_unit] / _MASS_TO_KG[out_unit]
        conversion_note += f"; output mass converted from {mass_unit} to {out_unit}"

    return density_per_stl_unit * mass_factor, {
        "material_id": entry.material_id,
        "density_value_from_table": entry.value,
        "density_unit_text": entry.unit_text,
        "detected_density_unit": normalized,
        "detected_mass_unit": mass_unit,
        "detected_density_length_unit": density_length_unit,
        "stl_length_unit": stl_unit_norm,
        "density_multiplier_applied": factor,
        "output_mass_multiplier_applied": mass_factor,
        "effective_density_per_stl_unit_cubed": density_per_stl_unit * mass_factor,
        "source": entry.source,
        "conversion_note": conversion_note,
    }


def choose_material_id(material_counts: Dict[object, object]) -> Tuple[int, Dict[str, int]]:
    counts = {int(k): int(v) for k, v in material_counts.items()}
    if not counts:
        raise ValueError("selected component has no material IDs")
    # Modal Material ID; deterministic tie-break by higher count then lower ID.
    material_id = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return material_id, counts


def calculate_mass(config: Dict[str, object]) -> Dict[str, object]:
    stl_path = str(config.get("stl_path") or "/root/scan_data.stl")
    density_table_path = str(config.get("density_table_path") or "/root/material_density_table.md")
    tolerance_val = config.get("tolerance", None)
    tolerance = None if tolerance_val is None else float(tolerance_val)
    stl_length_unit = str(config.get("stl_length_unit") or "mm")
    density_conversion = str(config.get("density_conversion") or "auto")
    output_mass_unit = str(config.get("output_mass_unit") or "same")

    header, triangles, attrs = parse_binary_stl(stl_path)
    analysis = analyze_components(triangles, attrs, tolerance=tolerance)
    selected = analysis["selected_component"]  # type: ignore[index]
    volume = float(selected["repaired_abs_volume"])  # type: ignore[index]
    if not math.isfinite(volume) or volume <= 0.0:
        raise ValueError(f"selected component has nonpositive/nonfinite volume: {volume}")

    material_id, mat_counts = choose_material_id(selected["material_counts"])  # type: ignore[index]
    densities = parse_density_table(density_table_path)
    if material_id not in densities:
        raise DensityParseError(
            f"material ID {material_id} not found in density table; available IDs: {sorted(densities.keys())}"
        )
    effective_density, density_info = convert_density_to_stl_units(
        densities[material_id],
        stl_length_unit=stl_length_unit,
        density_conversion=density_conversion,
        output_mass_unit=output_mass_unit,
    )
    mass = volume * effective_density
    if not math.isfinite(mass):
        raise ValueError("computed mass is not finite")

    report = {"main_part_mass": mass, "material_id": int(material_id)}
    diagnostics = {
        "stl_path": stl_path,
        "density_table_path": density_table_path,
        "triangle_count": len(triangles),
        "stl_header_ascii_prefix": header[:32].decode("ascii", errors="replace"),
        "main_component_volume": volume,
        "main_component_surface_area": float(selected["surface_area"]),  # type: ignore[index]
        "main_component_material_counts": mat_counts,
        "material_id_choice_note": "modal Attribute Byte Count value on selected component",
        "density": density_info,
        "mesh_analysis": analysis,
    }
    return {"report": report, "diagnostics": diagnostics}


def write_report(report: Dict[str, object], output_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp_path = output_path + ".tmp"
    # Only the task-required keys are written to the artifact.
    artifact = {
        "main_part_mass": float(report["main_part_mass"]),
        "material_id": int(report["material_id"]),
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, output_path)


def read_and_validate_report(output_path: str, expected: Dict[str, object]) -> Dict[str, object]:
    with open(output_path, "r", encoding="utf-8") as f:
        observed = json.load(f)
    if set(observed.keys()) != {"main_part_mass", "material_id"}:
        raise ValueError(f"report keys are not exactly the required keys: {sorted(observed.keys())}")
    obs_mass = float(observed["main_part_mass"])
    obs_mid = int(observed["material_id"])
    exp_mass = float(expected["main_part_mass"])
    exp_mid = int(expected["material_id"])
    if not math.isfinite(obs_mass):
        raise ValueError("report main_part_mass is not finite")
    if obs_mid != exp_mid:
        raise ValueError(f"report material_id {obs_mid} does not match computed {exp_mid}")
    if obs_mass != exp_mass:
        # JSON roundtrip should normally preserve this float exactly enough; allow tiny representation noise.
        rel = abs(obs_mass - exp_mass) / max(abs(exp_mass), 1.0)
        if rel > 1.0e-15:
            raise ValueError(f"report mass {obs_mass} does not match computed {exp_mass}")
    return {"observed": observed, "relative_mass_difference": abs(obs_mass - exp_mass) / max(abs(exp_mass), 1.0)}


def calculate_and_write(config: Dict[str, object]) -> Dict[str, object]:
    output_path = str(config.get("output_path") or "/root/mass_report.json")
    result = calculate_mass(config)
    write_report(result["report"], output_path)  # type: ignore[arg-type]
    validation = read_and_validate_report(output_path, result["report"])  # type: ignore[arg-type]
    result["output_path"] = output_path
    result["postwrite_validation"] = validation
    return result
