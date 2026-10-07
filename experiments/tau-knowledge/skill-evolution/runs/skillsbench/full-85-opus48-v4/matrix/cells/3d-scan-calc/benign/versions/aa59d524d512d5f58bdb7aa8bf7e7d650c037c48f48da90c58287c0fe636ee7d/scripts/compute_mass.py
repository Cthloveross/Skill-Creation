#!/usr/bin/env python3
"""Compute part mass from a binary STL whose attribute field stores a Material ID.

Stdin: JSON object with keys:
  stl_path (required), density_table_path (required), output_path (optional,
  default /root/mass_report.json), density_unit, volume_scale, mass_scale,
  component_by.
Stdout: JSON diagnostics (see SKILL.md). Also writes output_path.
"""
import json
import os
import re
import struct
import sys
from collections import Counter, defaultdict


def read_binary_stl(path):
    with open(path, 'rb') as f:
        data = f.read()
    warnings = []
    if len(data) < 84:
        raise ValueError('file too small to be a binary STL')
    header = data[:80]
    if header[:6].lower() == b'solid ' and b'facet' in data[:512].lower():
        # heuristic: could be ASCII; but binary files may also start with 'solid'
        # Only treat as ASCII if there is no plausible binary record structure.
        count = struct.unpack('<I', data[80:84])[0]
        expected = 84 + count * 50
        if expected != len(data):
            raise ValueError('appears to be ASCII STL; this task expects binary STL')
    count = struct.unpack('<I', data[80:84])[0]
    expected = 84 + count * 50
    if expected != len(data):
        derived = (len(data) - 84) // 50
        warnings.append(
            'header triangle count %d inconsistent with file size; using %d'
            % (count, derived))
        count = derived
    tris = []
    attrs = []
    off = 84
    for _ in range(count):
        vals = struct.unpack_from('<12f', data, off)
        attr = struct.unpack_from('<H', data, off + 48)[0]
        v1 = (vals[3], vals[4], vals[5])
        v2 = (vals[6], vals[7], vals[8])
        v3 = (vals[9], vals[10], vals[11])
        tris.append((v1, v2, v3))
        attrs.append(attr)
        off += 50
    return tris, attrs, warnings


def bbox_extent(tris):
    xs = []
    ys = []
    zs = []
    for (a, b, c) in tris:
        for v in (a, b, c):
            xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
    if not xs:
        return 1.0
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) or 1.0


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def connected_components(tris, tol):
    n = len(tris)
    uf = UF(n)
    vmap = defaultdict(list)  # quantized vertex -> triangle indices
    inv = 1.0 / tol

    def key(v):
        return (round(v[0] * inv), round(v[1] * inv), round(v[2] * inv))
    for i, (a, b, c) in enumerate(tris):
        for v in (a, b, c):
            vmap[key(v)].append(i)
    for idxs in vmap.values():
        first = idxs[0]
        for j in idxs[1:]:
            uf.union(first, j)
    comps = defaultdict(list)
    for i in range(n):
        comps[uf.find(i)].append(i)
    return list(comps.values())


def signed_volume(tris, indices):
    v = 0.0
    for i in indices:
        a, b, c = tris[i]
        # a . (b x c)
        cx = b[1] * c[2] - b[2] * c[1]
        cy = b[2] * c[0] - b[0] * c[2]
        cz = b[0] * c[1] - b[1] * c[0]
        v += a[0] * cx + a[1] * cy + a[2] * cz
    return v / 6.0


def parse_density_table(path):
    """Return dict material_id(int)->(density_float, unit_str) and a global unit guess."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    unit_guess = None
    m = re.search(r'(g\s*/\s*cm\^?3|g\s*/\s*cm3|kg\s*/\s*m\^?3|kg\s*/\s*m3|g\s*/\s*mm\^?3|g\s*/\s*mm3)',
                  text, re.IGNORECASE)
    if m:
        unit_guess = m.group(1)
    mapping = {}
    for line in text.splitlines():
        if '|' not in line:
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 2:
            continue
        # find an integer id and a float density among cells
        ints = []
        floats = []
        for c in cells:
            if re.fullmatch(r'[-+]?\d+', c):
                ints.append(int(c))
            else:
                fm = re.search(r'[-+]?\d*\.\d+|[-+]?\d+\.\d*', c)
                if fm:
                    floats.append(float(fm.group(0)))
        if ints and floats:
            mapping[ints[0]] = (floats[0], unit_guess)
    return mapping, unit_guess


def unit_to_g_per_mm3(density, unit):
    if not unit:
        unit = 'g/cm^3'
    u = unit.lower().replace(' ', '').replace('^', '')
    if 'g/cm3' in u:
        return density * 1e-3
    if 'kg/m3' in u:
        return density * 1e-6
    if 'g/mm3' in u:
        return density
    # default
    return density * 1e-3


def main():
    cfg = json.load(sys.stdin)
    stl_path = cfg['stl_path']
    table_path = cfg['density_table_path']
    out_path = cfg.get('output_path', '/root/mass_report.json')
    volume_scale = float(cfg.get('volume_scale', 1.0))
    mass_scale = float(cfg.get('mass_scale', 1.0))
    forced_unit = cfg.get('density_unit')
    component_by = cfg.get('component_by', 'triangles')

    tris, attrs, warnings = read_binary_stl(stl_path)
    extent = bbox_extent(tris)
    tol = extent * 1e-6
    comps = connected_components(tris, tol)

    if component_by == 'volume':
        main_comp = max(comps, key=lambda idxs: abs(signed_volume(tris, idxs)))
    else:
        main_comp = max(comps, key=len)

    volume_mm3 = abs(signed_volume(tris, main_comp)) * volume_scale

    comp_attr = Counter(attrs[i] for i in main_comp)
    material_id = comp_attr.most_common(1)[0][0]

    mapping, unit_guess = parse_density_table(table_path)
    unit = forced_unit or unit_guess
    density_raw = None
    density_g_per_mm3 = None
    main_part_mass = None
    if material_id in mapping:
        density_raw, row_unit = mapping[material_id]
        unit = forced_unit or row_unit or unit_guess
        density_g_per_mm3 = unit_to_g_per_mm3(density_raw, unit)
        main_part_mass = round(volume_mm3 * density_g_per_mm3 * mass_scale, 2)

    result = {
        'main_part_mass': main_part_mass,
        'material_id': int(material_id),
        'volume_mm3': volume_mm3,
        'density_raw': density_raw,
        'density_unit': unit,
        'density_g_per_mm3': density_g_per_mm3,
        'num_components': len(comps),
        'component_triangle_counts': sorted((len(c) for c in comps), reverse=True),
        'main_component_triangles': len(main_comp),
        'available_material_ids': sorted(mapping.keys()),
        'warnings': warnings,
    }

    if main_part_mass is not None:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'main_part_mass': main_part_mass,
                       'material_id': int(material_id)}, f, indent=2)
        result['output_written'] = out_path
    else:
        result['output_written'] = None
        result['error'] = 'material_id not found in density table'

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
