"""Create a mass report from a binary STL and documented material densities.

The program reads one JSON object from stdin and writes a JSON status object to
stdout.  The report itself is written to output_path.
"""
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict


class TaskError(Exception):
    pass


class DSU:
    def __init__(self, size):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, first, second):
        first, second = self.find(first), self.find(second)
        if first == second:
            return
        if self.rank[first] < self.rank[second]:
            first, second = second, first
        self.parent[second] = first
        if self.rank[first] == self.rank[second]:
            self.rank[first] += 1


NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
ID_LABEL_RE = re.compile(
    r"(?:material\s*)?(?:id|identifier)\s*[:=#-]*\s*(\d+)", re.IGNORECASE
)
DENSITY_LABEL_RE = re.compile(
    r"density\s*(?:\([^\n)]*\))?\s*[:=,-]*\s*("
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)",
    re.IGNORECASE,
)


def read_binary_stl(path):
    try:
        with open(path, "rb") as source:
            payload = source.read()
    except OSError as exc:
        raise TaskError("cannot read STL %r: %s" % (path, exc))
    if len(payload) < 84:
        raise TaskError("file is too short for a binary STL")
    triangle_count = struct.unpack_from("<I", payload, 80)[0]
    expected_length = 84 + triangle_count * 50
    if len(payload) != expected_length:
        raise TaskError("binary STL length does not match declared triangle count")
    if triangle_count == 0:
        raise TaskError("STL contains no triangles")

    triangles = []
    attributes = []
    for index in range(triangle_count):
        values = struct.unpack_from("<12fH", payload, 84 + 50 * index)
        triangle = (tuple(values[3:6]), tuple(values[6:9]), tuple(values[9:12]))
        if not all(math.isfinite(coordinate) for vertex in triangle for coordinate in vertex):
            raise TaskError("triangle %d has a non-finite vertex" % index)
        triangles.append(triangle)
        # Documentation for this task defines Attribute Byte Count as Material ID.
        attributes.append(int(values[12]))
    return triangles, attributes


def make_components(triangles):
    """Connect triangles by tolerance-coincident runtime vertices."""
    coordinates = [value for triangle in triangles for vertex in triangle for value in vertex]
    extent = max(coordinates) - min(coordinates)
    # A scale-relative tolerance covers float serialization noise while avoiding
    # a fixed absolute tolerance that would depend on model placement or scale.
    tolerance = max(extent, 1.0) * 1.0e-6
    tolerance_squared = tolerance * tolerance

    dsu = DSU(len(triangles))
    buckets = defaultdict(list)
    representatives = []
    triangle_vertex_ids = []

    def bucket_key(vertex):
        return tuple(math.floor(value / tolerance) for value in vertex)

    for triangle_index, triangle in enumerate(triangles):
        vertex_ids = []
        for vertex in triangle:
            base = bucket_key(vertex)
            closest = None
            closest_distance = None
            for x_offset in (-1, 0, 1):
                for y_offset in (-1, 0, 1):
                    for z_offset in (-1, 0, 1):
                        nearby_key = (base[0] + x_offset, base[1] + y_offset, base[2] + z_offset)
                        for candidate in buckets[nearby_key]:
                            representative = representatives[candidate]
                            distance = sum((vertex[i] - representative[i]) ** 2 for i in range(3))
                            if distance <= tolerance_squared and (
                                closest_distance is None or distance < closest_distance
                            ):
                                closest = candidate
                                closest_distance = distance
            if closest is None:
                closest = len(representatives)
                representatives.append(vertex)
                buckets[base].append(closest)
            vertex_ids.append(closest)
        if len(set(vertex_ids)) != 3:
            raise TaskError("triangle %d is degenerate at connectivity tolerance" % triangle_index)
        triangle_vertex_ids.append(tuple(vertex_ids))

    owner = {}
    for triangle_index, vertex_ids in enumerate(triangle_vertex_ids):
        for vertex_id in vertex_ids:
            if vertex_id in owner:
                dsu.union(triangle_index, owner[vertex_id])
            else:
                owner[vertex_id] = triangle_index

    grouped = defaultdict(list)
    for triangle_index in range(len(triangles)):
        grouped[dsu.find(triangle_index)].append(triangle_index)
    return list(grouped.values()), triangle_vertex_ids, tolerance


def require_closed_consistent(indices, triangle_vertex_ids):
    """Require exactly two oppositely directed uses of every snapped edge."""
    edge_uses = defaultdict(list)
    for triangle_index in indices:
        first, second, third = triangle_vertex_ids[triangle_index]
        for start, end in ((first, second), (second, third), (third, first)):
            edge_uses[(min(start, end), max(start, end))].append((start, end))

    bad_count = 0
    bad_winding = 0
    for uses in edge_uses.values():
        if len(uses) != 2:
            bad_count += 1
        elif uses[0] != (uses[1][1], uses[1][0]):
            bad_winding += 1
    if bad_count or bad_winding:
        raise TaskError(
            "component is not closed and consistently wound (%d open/non-manifold edges, %d winding conflicts)"
            % (bad_count, bad_winding)
        )


def signed_volume(triangles, indices):
    terms = []
    for index in indices:
        first, second, third = triangles[index]
        cross = (
            second[1] * third[2] - second[2] * third[1],
            second[2] * third[0] - second[0] * third[2],
            second[0] * third[1] - second[1] * third[0],
        )
        terms.append((first[0] * cross[0] + first[1] * cross[1] + first[2] * cross[2]) / 6.0)
    result = math.fsum(terms)
    if not math.isfinite(result):
        raise TaskError("component volume is non-finite")
    return result


def first_number(text):
    match = NUMBER_RE.search(text.replace(",", ""))
    return float(match.group(0)) if match else None


def clean_header(text):
    """Remove lightweight Markdown decoration before semantic header matching."""
    value = re.sub(r"[`*_]", "", text).strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def header_is_material_id(header):
    header = clean_header(header)
    if "material" in header and ("id" in header or "identifier" in header):
        return True
    return bool(re.fullmatch(r"(?:material )?(?:id|identifier)", header))


def header_is_density(header):
    return "density" in clean_header(header)


def separator_row(cells):
    joined = "".join(cells).replace(" ", "")
    return bool(joined) and all(character in "-:" for character in joined)


def add_density(result, material_id, density):
    if not math.isfinite(density) or density <= 0:
        raise TaskError("density for Material ID %d must be positive and finite" % material_id)
    existing = result.get(material_id)
    if existing is not None and not math.isclose(existing, density, rel_tol=1e-12, abs_tol=0.0):
        raise TaskError("conflicting documented densities for Material ID %d" % material_id)
    result[material_id] = density


def parse_density_table(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            text = source.read()
    except OSError as exc:
        raise TaskError("cannot read density documentation %r: %s" % (path, exc))

    densities = {}
    lines = text.splitlines()

    # Parse every named Markdown table, preserving column meaning rather than
    # assuming that a numeric ID occupies the first column.
    for header_index, header_line in enumerate(lines):
        if "|" not in header_line:
            continue
        headers = [cell.strip() for cell in header_line.strip().strip("|").split("|")]
        id_column = next((i for i, header in enumerate(headers) if header_is_material_id(header)), None)
        density_column = next((i for i, header in enumerate(headers) if header_is_density(header)), None)
        if id_column is None or density_column is None:
            continue

        for data_line in lines[header_index + 1:]:
            if "|" not in data_line:
                break
            cells = [cell.strip() for cell in data_line.strip().strip("|").split("|")]
            if len(cells) <= max(id_column, density_column) or separator_row(cells):
                continue
            # IDs are deliberately strict: a material-name number is not an ID.
            if not re.fullmatch(r"\d+", cells[id_column]):
                continue
            density = first_number(cells[density_column])
            if density is not None:
                add_density(densities, int(cells[id_column]), density)

    # Also accept ordinary labelled prose records.  Restrict density lookup to
    # the text before the next ID record so adjacent materials cannot be mixed.
    id_matches = list(ID_LABEL_RE.finditer(text))
    for position, id_match in enumerate(id_matches):
        record_end = id_matches[position + 1].start() if position + 1 < len(id_matches) else len(text)
        density_match = DENSITY_LABEL_RE.search(text, id_match.end(), record_end)
        if density_match:
            add_density(densities, int(id_match.group(1)), float(density_match.group(1)))

    if not densities:
        raise TaskError("no documented Material ID/density pairs could be parsed")
    return densities


def compute(stl_path, density_path):
    triangles, attributes = read_binary_stl(stl_path)
    components, vertex_ids, tolerance = make_components(triangles)

    candidates = []
    for indices in components:
        try:
            require_closed_consistent(indices, vertex_ids)
            volume = abs(signed_volume(triangles, indices))
        except TaskError:
            # Disconnected broken scan debris has no validated enclosed volume.
            continue
        if volume > 0:
            candidates.append((volume, indices))
    if not candidates:
        raise TaskError("no closed component with positive enclosed volume was found")

    volume, main_indices = max(candidates, key=lambda candidate: candidate[0])
    material_ids = {attributes[index] for index in main_indices}
    if len(material_ids) != 1:
        raise TaskError("largest component has ambiguous Material IDs: %s" % sorted(material_ids))
    material_id = next(iter(material_ids))

    densities = parse_density_table(density_path)
    if material_id not in densities:
        raise TaskError("Material ID %d is absent from density documentation" % material_id)
    mass = volume * densities[material_id]
    if not math.isfinite(mass) or mass < 0:
        raise TaskError("calculated mass is non-finite or negative")

    return ({"main_part_mass": mass, "material_id": material_id}, {
        "component_count": len(components),
        "vertex_tolerance": tolerance,
        "main_part_volume": volume,
    })


def write_report(path, report):
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise TaskError("output directory does not exist: %s" % directory)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as destination:
            json.dump(report, destination, allow_nan=False, separators=(",", ":"))
            destination.write("\n")
        os.replace(temporary_path, path)
    except OSError as exc:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise TaskError("cannot write report %r: %s" % (path, exc))


def main(request):
    stl_path = request.get("stl_path", "/root/scan_data.stl")
    density_path = request.get("density_table_path", "/root/material_density_table.md")
    output_path = request.get("output_path", "/root/mass_report.json")
    if not all(isinstance(value, str) and value for value in (stl_path, density_path, output_path)):
        raise TaskError("stl_path, density_table_path, and output_path must be nonempty strings")

    report, details = compute(stl_path, density_path)
    write_report(output_path, report)

    if request.get("verify", True):
        try:
            with open(output_path, "r", encoding="utf-8") as source:
                saved = json.load(source)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TaskError("cannot reopen written report: %s" % exc)
        recomputed, _ = compute(stl_path, density_path)
        saved_mass = saved.get("main_part_mass") if isinstance(saved, dict) else None
        if (
            not isinstance(saved, dict)
            or saved.get("material_id") != recomputed["material_id"]
            or isinstance(saved_mass, bool)
            or not isinstance(saved_mass, (int, float))
            or not math.isfinite(float(saved_mass))
            or not math.isclose(float(saved_mass), recomputed["main_part_mass"], rel_tol=1e-12, abs_tol=0.0)
        ):
            raise TaskError("reopened report does not match recomputation")

    return {"ok": True, "output_path": output_path, "report": report, "validation": details}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TaskError("stdin JSON must be an object")
        print(json.dumps(main(request), allow_nan=False, separators=(",", ":")))
    except (TaskError, ValueError, TypeError, struct.error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
