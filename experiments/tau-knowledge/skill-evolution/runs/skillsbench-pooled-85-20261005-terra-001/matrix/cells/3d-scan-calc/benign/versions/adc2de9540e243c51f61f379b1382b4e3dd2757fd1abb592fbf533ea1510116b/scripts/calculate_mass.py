#!/usr/bin/env python3
"""Create a mass report from a binary STL and a Markdown density table.

stdin: {"stl_path": str?, "density_table_path": str?, "output_path": str?}
stdout success: {"ok": true, "report_path": str, "material_id": int,
                 "density": number, "volume": number, "main_part_mass": number}
stdout failure: {"ok": false, "error": str}
"""
import json
import math
import os
import re
import struct
import sys
import tempfile
from collections import Counter, defaultdict, deque


class MassError(Exception):
    pass


class DSU:
    def __init__(self, n):
        self.p = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.p[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def parse_binary_stl(path):
    try:
        data = open(path, "rb").read()
    except OSError as exc:
        raise MassError("cannot read STL: %s" % exc)
    if len(data) < 84:
        raise MassError("STL is shorter than binary header and count")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + 50 * count
    if len(data) != expected:
        raise MassError("STL length does not match its binary triangle count")
    triangles, attrs = [], []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        # values[0:3] is the stored normal, which is not needed for volume.
        verts = (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12]))
        if not all(math.isfinite(x) for v in verts for x in v):
            raise MassError("STL contains non-finite vertex coordinates")
        triangles.append(verts)
        attrs.append(int(values[12]))
        offset += 50
    if not triangles:
        raise MassError("STL has no triangles")
    return triangles, attrs


def canonical_vertices(triangles):
    points = [p for tri in triangles for p in tri]
    mins = [min(p[k] for p in points) for k in range(3)]
    maxs = [max(p[k] for p in points) for k in range(3)]
    span = max(maxs[k] - mins[k] for k in range(3))
    tol = max(span, 1.0) * 1.0e-8
    if not math.isfinite(tol) or tol <= 0:
        raise MassError("invalid coordinate scale")

    representatives = []
    buckets = defaultdict(list)
    canonical = []
    tol2 = tol * tol
    for p in points:
        cell = tuple(math.floor(x / tol) for x in p)
        found = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for candidate in buckets.get((cell[0]+dx, cell[1]+dy, cell[2]+dz), ()): 
                        q = representatives[candidate]
                        if sum((p[k] - q[k]) ** 2 for k in range(3)) <= tol2:
                            found = candidate
                            break
                    if found is not None:
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            found = len(representatives)
            representatives.append(p)
            buckets[cell].append(found)
        canonical.append(found)
    return [tuple(canonical[3*i:3*i+3]) for i in range(len(triangles))]


def triangle_components(canonical_tris):
    dsu = DSU(len(canonical_tris))
    owner = {}
    for i, tri in enumerate(canonical_tris):
        if len(set(tri)) != 3:
            raise MassError("mesh contains a degenerate triangle after vertex matching")
        for vertex in tri:
            if vertex in owner:
                dsu.union(i, owner[vertex])
            else:
                owner[vertex] = i
    groups = defaultdict(list)
    for i in range(len(canonical_tris)):
        groups[dsu.find(i)].append(i)
    return list(groups.values())


def directed_edge(tri, flip, edge_key):
    vertices = (tri[0], tri[2], tri[1]) if flip else tri
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        if (a, b) if a < b else (b, a) == edge_key:
            return (a, b)
    raise MassError("internal edge lookup failure")


def oriented_component_volume(indices, canonical_tris, triangles):
    edge_users = defaultdict(list)
    for t in indices:
        tri = canonical_tris[t]
        for a, b in zip(tri, tri[1:] + tri[:1]):
            key = (a, b) if a < b else (b, a)
            edge_users[key].append(t)
    bad = [edge for edge, users in edge_users.items() if len(users) != 2]
    if bad:
        raise MassError("component is not watertight (an edge is not shared exactly twice)")

    neighbors = defaultdict(list)
    for edge, users in edge_users.items():
        a, b = users
        neighbors[a].append((b, edge))
        neighbors[b].append((a, edge))

    flipped = {indices[0]: False}
    queue = deque([indices[0]])
    while queue:
        current = queue.popleft()
        for other, edge in neighbors[current]:
            current_direction = directed_edge(canonical_tris[current], flipped[current], edge)
            desired = (current_direction[1], current_direction[0])
            original_other = directed_edge(canonical_tris[other], False, edge)
            required_flip = original_other != desired
            if other in flipped:
                if flipped[other] != required_flip:
                    raise MassError("component has inconsistent/non-orientable winding")
            else:
                flipped[other] = required_flip
                queue.append(other)
    if len(flipped) != len(indices):
        raise MassError("component connectivity traversal was incomplete")

    # A translated origin reduces cancellation for coordinates far from zero.
    used_points = [p for t in indices for p in triangles[t]]
    ref = tuple(sum(p[k] for p in used_points) / len(used_points) for k in range(3))
    volume6 = 0.0
    for t in indices:
        a, b, c = triangles[t]
        if flipped[t]:
            b, c = c, b
        a = tuple(a[k] - ref[k] for k in range(3))
        b = tuple(b[k] - ref[k] for k in range(3))
        c = tuple(c[k] - ref[k] for k in range(3))
        cross = (b[1]*c[2] - b[2]*c[1], b[2]*c[0] - b[0]*c[2], b[0]*c[1] - b[1]*c[0])
        volume6 += a[0]*cross[0] + a[1]*cross[1] + a[2]*cross[2]
    volume = volume6 / 6.0
    if not math.isfinite(volume) or volume == 0.0:
        raise MassError("component has zero or non-finite enclosed volume")
    return abs(volume)


def number_from_cell(cell):
    # Thousands separators are harmless when used between digits.
    cleaned = re.sub(r"(?<=\d),(?=\d)", "", cell)
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", cleaned)
    if not match:
        raise ValueError("no numeric value")
    value = float(match.group(0))
    if not math.isfinite(value):
        raise ValueError("non-finite value")
    return value


def density_for_material(table_path, material_id):
    try:
        text = open(table_path, "r", encoding="utf-8").read()
    except OSError as exc:
        raise MassError("cannot read density table: %s" % exc)
    lines = text.splitlines()
    for i in range(len(lines) - 2):
        if "|" not in lines[i] or "|" not in lines[i+1]:
            continue
        header = [x.strip().lower() for x in lines[i].strip().strip("|").split("|")]
        separator = lines[i+1].strip()
        if "-" not in separator:
            continue
        id_columns = [j for j, h in enumerate(header) if re.sub(r"[^a-z0-9]", "", h) in ("id", "materialid")]
        density_columns = [j for j, h in enumerate(header) if "density" in h]
        if not id_columns or not density_columns:
            continue
        for row in lines[i+2:]:
            if "|" not in row:
                break
            cells = [x.strip() for x in row.strip().strip("|").split("|")]
            if len(cells) < len(header):
                continue
            try:
                row_id = int(number_from_cell(cells[id_columns[0]]))
                density = number_from_cell(cells[density_columns[0]])
            except ValueError:
                continue
            if row_id == material_id:
                if density <= 0:
                    raise MassError("matched density is not positive")
                return density
    raise MassError("no Markdown density-table row matches Material ID %d" % material_id)


def atomic_write_report(path, report):
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        raise MassError("report output directory does not exist: " + parent)
    fd, temporary = tempfile.mkstemp(prefix=".mass_report_", suffix=".json", dir=parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, allow_nan=False, indent=1)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def validate_report(path, expected):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            actual = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MassError("written report cannot be reopened: %s" % exc)
    if set(actual) != {"main_part_mass", "material_id"}:
        raise MassError("written report has an unexpected schema")
    if not isinstance(actual["material_id"], int) or isinstance(actual["material_id"], bool):
        raise MassError("written Material ID is not an integer")
    if not isinstance(actual["main_part_mass"], (int, float)) or isinstance(actual["main_part_mass"], bool) or not math.isfinite(actual["main_part_mass"]):
        raise MassError("written mass is not finite numeric")
    if actual != expected:
        raise MassError("written report differs from calculated report")


def run(config):
    if not isinstance(config, dict):
        raise MassError("stdin must be a JSON object")
    stl_path = config.get("stl_path", "/root/scan_data.stl")
    density_path = config.get("density_table_path", "/root/material_density_table.md")
    output_path = config.get("output_path", "/root/mass_report.json")
    if not all(isinstance(x, str) and x for x in (stl_path, density_path, output_path)):
        raise MassError("input paths must be nonempty strings")

    triangles, attrs = parse_binary_stl(stl_path)
    canonical = canonical_vertices(triangles)
    components = triangle_components(canonical)
    measured = []
    failures = []
    for group in components:
        try:
            measured.append((oriented_component_volume(group, canonical, triangles), group))
        except MassError as exc:
            failures.append(str(exc))
    if not measured:
        detail = failures[0] if failures else "no measurable components"
        raise MassError("no closed, orientable component is available: " + detail)
    volume, main = max(measured, key=lambda item: item[0])
    material_ids = set(attrs[t] for t in main)
    if len(material_ids) != 1:
        raise MassError("selected component contains multiple Material IDs")
    material_id = material_ids.pop()
    density = density_for_material(density_path, material_id)
    mass = volume * density
    if not math.isfinite(mass):
        raise MassError("calculated mass is non-finite")
    report = {"main_part_mass": mass, "material_id": material_id}
    atomic_write_report(output_path, report)
    validate_report(output_path, report)
    return {"ok": True, "report_path": output_path, "material_id": material_id,
            "density": density, "volume": volume, "main_part_mass": mass}


def main():
    try:
        config = json.load(sys.stdin)
        result = run(config)
        print(json.dumps(result, allow_nan=False))
    except (MassError, json.JSONDecodeError, OSError, struct.error, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
