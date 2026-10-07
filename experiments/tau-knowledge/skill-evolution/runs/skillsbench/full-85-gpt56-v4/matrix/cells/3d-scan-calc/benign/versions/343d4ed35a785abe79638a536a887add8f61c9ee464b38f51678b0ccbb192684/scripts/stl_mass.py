"""Reusable binary-STL parsing, geometric component analysis, and density lookup."""
import math
import re
import struct
from collections import Counter, defaultdict


class MassInputError(ValueError):
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
    """Return (triangles, attributes), where triangle is three xyz tuples."""
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 84:
        raise MassInputError("STL is shorter than the binary STL header and count")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + 50 * count
    if len(data) != expected:
        raise MassInputError(
            "binary STL length does not match its declared triangle count "
            "(expected %d bytes, got %d)" % (expected, len(data))
        )
    if count == 0:
        raise MassInputError("STL contains no triangles")
    triangles, attributes = [], []
    offset = 84
    for _ in range(count):
        # Normal occupies the first 12 bytes and is intentionally not trusted.
        values = struct.unpack_from("<12fH", data, offset)
        pts = (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12]))
        if not all(math.isfinite(c) for point in pts for c in point):
            raise MassInputError("STL contains non-finite vertex coordinates")
        triangles.append(pts)
        attributes.append(values[12])
        offset += 50
    return triangles, attributes


def default_tolerance(triangles):
    values = [c for tri in triangles for point in tri for c in point]
    lo, hi = min(values), max(values)
    # Per-axis diagonal is less sensitive to a large translated origin.
    xs = [p[0] for tri in triangles for p in tri]
    ys = [p[1] for tri in triangles for p in tri]
    zs = [p[2] for tri in triangles for p in tri]
    diagonal = math.sqrt((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2 + (max(zs)-min(zs))**2)
    scale = max(diagonal, abs(lo), abs(hi), 1.0)
    return max(diagonal * 1.0e-6, scale * 1.0e-9)


def canonicalize_and_components(triangles, tolerance):
    """Return canonical vertex triples per triangle and lists of triangle indices."""
    if not (math.isfinite(tolerance) and tolerance > 0):
        raise MassInputError("vertex tolerance must be a finite positive number")
    dsu = DSU(len(triangles))
    cells = defaultdict(list)
    canonical_points = []
    vertex_owner = {}
    canonical_triangles = []

    def cell_for(point):
        return tuple(math.floor(v / tolerance) for v in point)

    for ti, tri in enumerate(triangles):
        ids = []
        for point in tri:
            cell = cell_for(point)
            found = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for candidate in cells[(cell[0]+dx, cell[1]+dy, cell[2]+dz)]:
                            q = canonical_points[candidate]
                            if ((point[0]-q[0])**2 + (point[1]-q[1])**2 + (point[2]-q[2])**2) <= tolerance*tolerance:
                                found = candidate
                                break
                        if found is not None:
                            break
                    if found is not None:
                        break
                if found is not None:
                    break
            if found is None:
                found = len(canonical_points)
                canonical_points.append(point)
                cells[cell].append(found)
            ids.append(found)
            previous = vertex_owner.get(found)
            if previous is None:
                vertex_owner[found] = ti
            else:
                dsu.union(ti, previous)
        canonical_triangles.append(tuple(ids))

    groups = defaultdict(list)
    for i in range(len(triangles)):
        groups[dsu.find(i)].append(i)
    return canonical_triangles, list(groups.values())


def signed_volume(triangles, indices):
    total = 0.0
    for i in indices:
        a, b, c = triangles[i]
        total += (a[0]*(b[1]*c[2]-b[2]*c[1]) +
                  a[1]*(b[2]*c[0]-b[0]*c[2]) +
                  a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
    return total


def winding_status(canonical_triangles, indices):
    """Return (is_watertight_and_oriented, explanatory_reason)."""
    edges = defaultdict(list)
    for i in indices:
        a, b, c = canonical_triangles[i]
        if len({a, b, c}) != 3:
            return False, "contains a degenerate triangle"
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            edges[key].append((u, v))
    for directed in edges.values():
        if len(directed) != 2:
            return False, "has open or non-manifold edges"
        if directed[0] != (directed[1][1], directed[1][0]):
            return False, "has inconsistent triangle winding"
    return True, "ok"


def bbox_volume(triangles, indices):
    coords = [p for i in indices for p in triangles[i]]
    spans = [max(p[axis] for p in coords) - min(p[axis] for p in coords) for axis in range(3)]
    return spans[0] * spans[1] * spans[2]


def select_main_component(triangles, canonical_triangles, groups):
    if not groups:
        raise MassInputError("no connected components were found")
    ranked = []
    for group in groups:
        closed, _ = winding_status(canonical_triangles, group)
        metric = abs(signed_volume(triangles, group)) if closed else bbox_volume(triangles, group)
        ranked.append((metric, group))
    metric, chosen = max(ranked, key=lambda item: item[0])
    if metric <= 0 or not math.isfinite(metric):
        raise MassInputError("largest component has no positive geometric extent")
    closed, reason = winding_status(canonical_triangles, chosen)
    if not closed:
        raise MassInputError("largest component cannot yield a reliable enclosed volume: " + reason)
    return chosen


def component_material(attributes, indices):
    counts = Counter(attributes[i] for i in indices)
    material, count = counts.most_common(1)[0]
    # A single outlier can arise from scan corruption, but a mixed object is ambiguous.
    if len(counts) > 1 and count * 2 <= len(indices):
        raise MassInputError("selected component has no majority material ID")
    return int(material)


def _plain_markdown(cell):
    """Remove common inline Markdown decoration before comparing cell values."""
    return re.sub(r"[*_`~]", "", cell).strip()


def _numeric(cell):
    cell = _plain_markdown(cell)
    match = re.search(r"(?<![A-Za-z0-9_.+-])([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", cell)
    return float(match.group(1)) if match else None


def density_for_material(text, material_id):
    """Extract one density value for an ID from a Markdown table or labelled line."""
    matches = []
    lines = text.splitlines()
    header = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            cells = [x.strip() for x in line.strip("|").split("|")]
            normalized = [re.sub(r"[^a-z0-9]", "", c.lower()) for c in cells]
            if any("density" in cell for cell in normalized) and any(cell in ("id", "materialid") or "materialid" in cell for cell in normalized):
                header = normalized
                continue
            if header and len(cells) == len(header) and not all(re.fullmatch(r"[-: ]+", c) for c in cells):
                id_columns = [j for j, h in enumerate(header) if h == "id" or "materialid" in h]
                density_columns = [j for j, h in enumerate(header) if "density" in h]
                if any(_plain_markdown(cells[j]) == str(material_id) for j in id_columns):
                    for j in density_columns:
                        value = _numeric(cells[j])
                        if value is not None:
                            matches.append(value)
        # Supports prose/CSV-like records only when both labels are explicit.
        id_pattern = r"(?:material\s*id|\bid)\s*[:=#-]?\s*" + re.escape(str(material_id)) + r"(?!\d)"
        if re.search(id_pattern, line, re.IGNORECASE):
            density_match = re.search(r"density\s*[:=#-]?\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", line, re.IGNORECASE)
            if density_match:
                matches.append(float(density_match.group(1)))
    unique = []
    for value in matches:
        if math.isfinite(value) and value > 0 and not any(math.isclose(value, old, rel_tol=1e-12, abs_tol=0.0) for old in unique):
            unique.append(value)
    if len(unique) != 1:
        if not unique:
            raise MassInputError("no positive density found for material ID %d" % material_id)
        raise MassInputError("density table gives conflicting densities for material ID %d" % material_id)
    return unique[0]


def cubic_centimeters_per_coordinate_unit(coordinate_unit):
    """Return the volume conversion factor for a declared STL coordinate unit."""
    units = {"mm": 0.1, "cm": 1.0, "m": 100.0}
    if not isinstance(coordinate_unit, str) or coordinate_unit.lower() not in units:
        raise MassInputError("coordinate_unit must be one of: mm, cm, m")
    return units[coordinate_unit.lower()] ** 3


def calculate(stl_path, density_table_path, tolerance=None, coordinate_unit="mm"):
    """Calculate grams when density is expressed in g/cm^3.

    STL does not record units.  The caller must therefore supply its coordinate
    unit; millimetres are the default for ordinary 3D-print scan data.
    """
    triangles, attributes = read_binary_stl(stl_path)
    tolerance = default_tolerance(triangles) if tolerance is None else float(tolerance)
    canonical, groups = canonicalize_and_components(triangles, tolerance)
    chosen = select_main_component(triangles, canonical, groups)
    material_id = component_material(attributes, chosen)
    with open(density_table_path, "r", encoding="utf-8") as handle:
        density = density_for_material(handle.read(), material_id)
    volume = abs(signed_volume(triangles, chosen)) * cubic_centimeters_per_coordinate_unit(coordinate_unit)
    mass = volume * density
    if not math.isfinite(mass) or mass < 0:
        raise MassInputError("computed mass is not a finite nonnegative number")
    return {"main_part_mass": mass, "material_id": material_id}
