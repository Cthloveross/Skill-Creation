"""Compute a main-part mass report from a binary STL and Markdown density table.

Read one JSON object from stdin and emit a JSON status object on stdout.
"""
import json
import math
import os
import re
import struct
import sys
from collections import Counter, defaultdict


class TaskError(Exception):
    pass


class DSU:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def read_binary_stl(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise TaskError("cannot read STL %r: %s" % (path, exc))
    if len(data) < 84:
        raise TaskError("file is too short to be a binary STL")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + 50 * count
    if len(data) != expected:
        raise TaskError("binary STL length does not match its triangle count (%d records)" % count)
    if count == 0:
        raise TaskError("STL contains no triangles")
    triangles, attributes = [], []
    for i in range(count):
        off = 84 + 50 * i
        # Ignore supplied facet normal: vertices define the volume calculation.
        values = struct.unpack_from("<12fH", data, off)
        verts = (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12]))
        if not all(math.isfinite(c) for v in verts for c in v):
            raise TaskError("triangle %d has a non-finite vertex coordinate" % i)
        triangles.append(verts)
        attributes.append(values[12])
    return triangles, attributes


def make_components(triangles):
    coords = [c for tri in triangles for vert in tri for c in vert]
    lo, hi = min(coords), max(coords)
    # Bounding-box diagonal is the geometric scale.  Coordinate magnitude is
    # included for models stored far from the origin, where float spacing grows.
    xs = [v[0] for tri in triangles for v in tri]
    ys = [v[1] for tri in triangles for v in tri]
    zs = [v[2] for tri in triangles for v in tri]
    diagonal = math.sqrt((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2 + (max(zs)-min(zs))**2)
    magnitude = max(abs(lo), abs(hi))
    tolerance = max(1.0e-9, 1.0e-7 * max(diagonal, magnitude))
    tol2 = tolerance * tolerance

    dsu = DSU(len(triangles))
    buckets = defaultdict(list)
    representatives = []
    tri_vertex_ids = []

    def key_for(v):
        return (math.floor(v[0] / tolerance), math.floor(v[1] / tolerance), math.floor(v[2] / tolerance))

    for tri_index, tri in enumerate(triangles):
        ids = []
        for v in tri:
            base = key_for(v)
            nearest, nearest_d2 = None, None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for candidate in buckets[(base[0]+dx, base[1]+dy, base[2]+dz)]:
                            rv = representatives[candidate]
                            d2 = (v[0]-rv[0])**2 + (v[1]-rv[1])**2 + (v[2]-rv[2])**2
                            if d2 <= tol2 and (nearest_d2 is None or d2 < nearest_d2):
                                nearest, nearest_d2 = candidate, d2
            if nearest is None:
                nearest = len(representatives)
                representatives.append(v)
                buckets[base].append(nearest)
            ids.append(nearest)
        if len(set(ids)) != 3:
            raise TaskError("triangle %d becomes degenerate at the connectivity tolerance" % tri_index)
        dsu.union(tri_index, tri_index)  # documents that isolated triangles are components too
        tri_vertex_ids.append(tuple(ids))

    # Shared snapped vertices create triangle connectivity.
    first_triangle_for_vertex = {}
    for ti, ids in enumerate(tri_vertex_ids):
        for vid in ids:
            prior = first_triangle_for_vertex.get(vid)
            if prior is None:
                first_triangle_for_vertex[vid] = ti
            else:
                dsu.union(ti, prior)
    components = defaultdict(list)
    for ti in range(len(triangles)):
        components[dsu.find(ti)].append(ti)
    return list(components.values()), tri_vertex_ids, tolerance


def signed_volume(triangles, indices):
    terms = []
    for i in indices:
        a, b, c = triangles[i]
        cross = (b[1]*c[2] - b[2]*c[1], b[2]*c[0] - b[0]*c[2], b[0]*c[1] - b[1]*c[0])
        terms.append((a[0]*cross[0] + a[1]*cross[1] + a[2]*cross[2]) / 6.0)
    value = math.fsum(terms)
    if not math.isfinite(value):
        raise TaskError("non-finite signed volume")
    return value


def require_closed_consistent(indices, tri_vertex_ids):
    uses = defaultdict(list)
    for ti in indices:
        a, b, c = tri_vertex_ids[ti]
        for u, v in ((a, b), (b, c), (c, a)):
            uses[(min(u, v), max(u, v))].append((u, v))
    bad_count = 0
    bad_winding = 0
    for directed in uses.values():
        if len(directed) != 2:
            bad_count += 1
        elif directed[0] != (directed[1][1], directed[1][0]):
            bad_winding += 1
    if bad_count or bad_winding:
        raise TaskError("component is not a closed consistently wound surface (%d non-manifold/open edges, %d winding conflicts)" % (bad_count, bad_winding))


def normalized_unit(text):
    if not text:
        return None
    u = text.lower().replace("³", "3").replace("²", "2").replace("^", "").replace("*", "")
    u = re.sub(r"\s+", "", u).strip("()[]:;.,")
    aliases = {"g/mm3": "g/mm3", "g/cm3": "g/cm3", "g/ml": "g/cm3",
               "kg/m3": "kg/m3", "kg/mm3": "kg/mm3", "kg/l": "kg/l"}
    return aliases.get(u)


def find_unit(text):
    # Longest alternatives first prevents matching the prefix of kg/mm3.
    match = re.search(r"(?:kg|g)\s*/\s*(?:mm|cm|ml|m|l)\s*(?:\^?\s*[23³])?", text, re.I)
    return normalized_unit(match.group(0)) if match else None


def density_to_g_per_mm3(value, unit):
    factors = {"g/mm3": 1.0, "g/cm3": 1.0e-3, "kg/m3": 1.0e-6,
               "kg/mm3": 1000.0, "kg/l": 1.0e-3}
    if unit not in factors:
        raise TaskError("unsupported or missing density unit")
    result = value * factors[unit]
    if not math.isfinite(result) or result <= 0:
        raise TaskError("density must be a positive finite number")
    return result


def first_number(text):
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def parse_density_table(path):
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as exc:
        raise TaskError("cannot read density table %r: %s" % (path, exc))
    densities = {}
    lines = text.splitlines()
    default_unit = find_unit(text) or "g/cm3"
    for row_index, line in enumerate(lines):
        if "|" not in line:
            continue
        headers = [x.strip() for x in line.strip().strip("|").split("|")]
        material_col = next((i for i, h in enumerate(headers) if "material" in h.lower() and "id" in h.lower()), None)
        density_col = next((i for i, h in enumerate(headers) if "density" in h.lower()), None)
        if material_col is None or density_col is None:
            continue
        header_unit = find_unit(headers[density_col]) or default_unit
        for data_line in lines[row_index+1:]:
            if "|" not in data_line:
                break
            cells = [x.strip() for x in data_line.strip().strip("|").split("|")]
            if len(cells) <= max(material_col, density_col) or set("".join(cells)) <= set("-: "):
                continue
            id_match = re.search(r"\d+", cells[material_col])
            value = first_number(cells[density_col])
            if not id_match or value is None:
                continue
            material_id = int(id_match.group(0))
            unit = find_unit(cells[density_col]) or header_unit
            converted = density_to_g_per_mm3(value, unit)
            if material_id in densities and not math.isclose(densities[material_id], converted, rel_tol=1e-12):
                raise TaskError("density table gives conflicting densities for Material ID %d" % material_id)
            densities[material_id] = converted
        if densities:
            return densities
    raise TaskError("no Markdown table with Material ID and Density columns was found")


def coordinate_scale_to_mm(unit):
    u = str(unit).lower().strip()
    values = {"mm": 1.0, "millimeter": 1.0, "millimetre": 1.0,
              "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}
    if u not in values:
        raise TaskError("unsupported coordinate_unit %r" % unit)
    return values[u]


def compute(stl_path, density_path, coordinate_unit):
    triangles, attributes = read_binary_stl(stl_path)
    components, vertex_ids, tolerance = make_components(triangles)
    candidates = []
    for indices in components:
        try:
            require_closed_consistent(indices, vertex_ids)
            volume = abs(signed_volume(triangles, indices))
            if volume > 0:
                candidates.append((volume, indices))
        except TaskError:
            # A broken disconnected scan fragment cannot provide enclosed mass.
            continue
    if not candidates:
        raise TaskError("no closed consistently wound component with positive volume was found")
    raw_volume, main_indices = max(candidates, key=lambda item: item[0])
    ids = set(attributes[i] for i in main_indices)
    if len(ids) != 1:
        raise TaskError("selected component has ambiguous Material IDs: %s" % sorted(ids))
    material_id = next(iter(ids))
    densities = parse_density_table(density_path)
    if material_id not in densities:
        raise TaskError("Material ID %d from STL is absent from density table" % material_id)
    mm_scale = coordinate_scale_to_mm(coordinate_unit)
    volume_mm3 = raw_volume * mm_scale ** 3
    mass = volume_mm3 * densities[material_id]
    if not math.isfinite(mass) or mass < 0:
        raise TaskError("calculated mass is non-finite or negative")
    return {"main_part_mass": mass, "material_id": material_id}, {"component_count": len(components), "vertex_tolerance": tolerance, "volume_mm3": volume_mm3}


def write_report(path, report):
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise TaskError("output directory does not exist: %s" % directory)
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(report, f, allow_nan=False, separators=(",", ":"))
            f.write("\n")
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise TaskError("cannot write report %r: %s" % (path, exc))


def main(request):
    stl = request.get("stl_path", "/root/scan_data.stl")
    density = request.get("density_table_path", "/root/material_density_table.md")
    output = request.get("output_path", "/root/mass_report.json")
    unit = request.get("coordinate_unit", "mm")
    report, details = compute(stl, density, unit)
    write_report(output, report)
    if request.get("verify", True):
        try:
            saved = json.load(open(output, "r", encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskError("cannot reopen written report: %s" % exc)
        second_report, _ = compute(stl, density, unit)
        if saved != report or saved.get("material_id") != second_report["material_id"] or not math.isclose(saved.get("main_part_mass", float("nan")), second_report["main_part_mass"], rel_tol=1e-12, abs_tol=0.0):
            raise TaskError("reopened report does not match independent recomputation")
    return {"ok": True, "output_path": output, "report": report, "validation": details}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TaskError("stdin JSON must be an object")
        print(json.dumps(main(request), allow_nan=False, separators=(",", ":")))
    except (TaskError, ValueError, TypeError, struct.error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
