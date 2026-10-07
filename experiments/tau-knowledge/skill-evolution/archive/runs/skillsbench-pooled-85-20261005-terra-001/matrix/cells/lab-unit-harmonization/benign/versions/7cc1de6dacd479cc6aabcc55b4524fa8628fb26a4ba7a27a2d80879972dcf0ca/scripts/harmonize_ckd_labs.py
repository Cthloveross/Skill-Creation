#!/usr/bin/env python3
"""CSV clinical-lab unit harmonizer; JSON stdin -> JSON stdout.

Uses only Python's standard library.  Conversion factors are established
molar-mass / scale relationships and are deliberately independent of any one
input dataset.
"""
import csv
import json
import math
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 34
MISSING = {"", "na", "n/a", "nan", "null", "none", "?", "missing", "not available"}

# key: aliases, broad conventional-unit screening interval, alternate->US factors.
# Intervals support unit selection in a CKD-oriented adult extract; they are not
# patient-specific clinical reference ranges.
REGISTRY = {
 "creatinine": (['creatinine','serum creat','s creat','scr'], (Decimal('0.1'),Decimal('25')), [('umol',Decimal('0.011312217')),('micromol',Decimal('0.011312217'))]),
 "bun": (['blood urea nitrogen','bun','urea nitrogen'], (Decimal('1'),Decimal('200')), [('urea mmol',Decimal('2.80112')),('urea mg',Decimal('0.4667')),('mmol',Decimal('2.80112'))]),
 "urea": (['serum urea','blood urea','urea'], (Decimal('2'),Decimal('430')), [('mmol',Decimal('6.006')),('mg dl bun',Decimal('2.14'))]),
 "glucose": (['glucose','blood sugar'], (Decimal('20'),Decimal('1000')), [('mmol',Decimal('18.0182'))]),
 "hemoglobin": (['hemoglobin','haemoglobin',' hgb','hb '], (Decimal('3'),Decimal('25')), [('g l',Decimal('0.1'))]),
 "hematocrit": (['hematocrit','haematocrit',' hct'], (Decimal('10'),Decimal('75')), [('fraction',Decimal('100')),('l l',Decimal('100'))]),
 "albumin_serum": (['serum albumin','plasma albumin','albumin'], (Decimal('0.5'),Decimal('7')), [('g l',Decimal('0.1'))]),
 "protein_total": (['total protein','serum protein','plasma protein'], (Decimal('2'),Decimal('12')), [('g l',Decimal('0.1'))]),
 "calcium_total": (['total calcium','serum calcium','calcium'], (Decimal('3'),Decimal('20')), [('mmol',Decimal('4.008'))]),
 "phosphorus": (['phosphorus','phosphate','phos'], (Decimal('0.5'),Decimal('20')), [('mmol',Decimal('3.097'))]),
 "magnesium": (['magnesium',' mg '], (Decimal('0.5'),Decimal('8')), [('mmol',Decimal('2.4305'))]),
 "bilirubin_total": (['total bilirubin','bilirubin'], (Decimal('0.05'),Decimal('40')), [('umol',Decimal('0.0584795')),('micromol',Decimal('0.0584795'))]),
 "uric_acid": (['uric acid','urate'], (Decimal('0.5'),Decimal('30')), [('umol',Decimal('0.016813'))]),
 "cholesterol_total": (['total cholesterol','cholesterol'], (Decimal('50'),Decimal('600')), [('mmol',Decimal('38.67'))]),
 "triglycerides": (['triglyceride','triglycerides','tg '], (Decimal('15'),Decimal('3000')), [('mmol',Decimal('88.57'))]),
 "hdl": (['hdl cholesterol','high density lipoprotein',' hdl'], (Decimal('5'),Decimal('200')), [('mmol',Decimal('38.67'))]),
 "ldl": (['ldl cholesterol','low density lipoprotein',' ldl'], (Decimal('5'),Decimal('600')), [('mmol',Decimal('38.67'))]),
 "iron": (['serum iron',' iron'], (Decimal('5'),Decimal('500')), [('umol',Decimal('5.5845'))]),
 "tibc": (['total iron binding','tibc'], (Decimal('50'),Decimal('800')), [('umol',Decimal('5.5845'))]),
 "transferrin": (['transferrin'], (Decimal('0.5'),Decimal('6')), [('g l',Decimal('0.1'))]),
 "crp": (['c reactive protein','c-reactive protein',' crp'], (Decimal('0'),Decimal('100')), [('mg l',Decimal('0.1'))]),
 "vitamin_d": (['vitamin d','25 oh d','25ohd'], (Decimal('1'),Decimal('200')), [('nmol',Decimal('0.40064'))]),
 "a1c": (['hemoglobin a1c','hba1c','glycated hemoglobin'], (Decimal('3'),Decimal('20')), [('fraction',Decimal('100'))]),
 "urine_albumin": (['urine albumin','urinary albumin','microalbumin'], (Decimal('0'),Decimal('2000')), [('mg l',Decimal('0.1'))]),
 "acr": (['albumin creatinine ratio','urine acr','uacr'], (Decimal('0'),Decimal('20000')), [('mg mmol',Decimal('8.84'))]),
 "urine_protein": (['urine protein','urinary protein','proteinuria'], (Decimal('0'),Decimal('2000')), [('g l',Decimal('100'))]),
}

# Alias-order overrides prevent broad names resolving before semantically richer names.
PRIORITY = ['acr','urine_albumin','urine_protein','albumin_serum','protein_total',
            'cholesterol_total','hdl','ldl','triglycerides','bilirubin_total','bun','urea']

def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def read_csv(path):
    text = Path(path).read_text(encoding='utf-8-sig', newline='')
    # Semicolon is common where comma is decimal separator. Otherwise standard CSV.
    first = next((x for x in text.splitlines() if x.strip()), '')
    delimiter = ';' if first.count(';') > first.count(',') else ','
    return list(csv.reader(text.splitlines(), delimiter=delimiter)), delimiter

def description_evidence(path, headers):
    if not path or not Path(path).exists():
        return {h: norm(h) for h in headers}
    rows, _ = read_csv(path)
    evidence = {h: norm(h) for h in headers}
    header_norm = {norm(h): h for h in headers}
    for row in rows:
        combined = norm(' '.join(row))
        # A row may have feature short-name in any field; attach its full description.
        for cell in row:
            n = norm(cell)
            if n in header_norm:
                evidence[header_norm[n]] += ' ' + combined
    return evidence

def resolve(text):
    # Specimen-sensitive adjustments precede generic matching.
    ordered = PRIORITY + [k for k in REGISTRY if k not in PRIORITY]
    for key in ordered:
        aliases = REGISTRY[key][0]
        if any(a in text for a in aliases):
            if key == 'albumin_serum' and ('urine albumin' in text or 'urinary albumin' in text or 'ratio' in text):
                continue
            if key == 'urea' and ('nitrogen' in text or 'bun' in text):
                continue
            return key
    return None

def parse_number(value):
    raw = str(value).strip()
    if raw.lower() in MISSING:
        raise ValueError('missing')
    # Decimal comma is only normalized when comma is the lone decimal separator;
    # do not reinterpret thousands grouping such as 1,234.
    if re.fullmatch(r'[+-]?(?:\d+,\d*|\d*,\d+)[eE][+-]?\d+', raw) or re.fullmatch(r'[+-]?\d+,\d*', raw):
        raw = raw.replace(',', '.')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', raw):
        raise ValueError('not a strict numeric token')
    try:
        d = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not d.is_finite():
        raise ValueError('nonfinite')
    return d

def inside(x, bounds):
    return bounds[0] <= x <= bounds[1]

def convert(value, key):
    """Return (output, action); action is identity, conversion label, or ambiguous."""
    _, bounds, candidates = REGISTRY[key]
    identity_ok = inside(value, bounds)
    fits = [(label, value * factor) for label, factor in candidates if inside(value * factor, bounds)]
    if identity_ok:
        # Retaining conventional values avoids false conversion where both scales fit.
        return value, 'identity' if not fits else 'ambiguous_identity_retained'
    if len(fits) == 1:
        return fits[0][1], 'converted:' + fits[0][0]
    if len(fits) > 1:
        return value, 'ambiguous_unconverted'
    return value, 'outside_no_admissible_conversion'

def fixed2(d):
    return format(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')

def main(cfg):
    input_path = cfg.get('input_path')
    if not input_path:
        raise ValueError('input_path is required')
    output_path = cfg.get('output_path', '/root/ckd_lab_data_harmonized.csv')
    strict = bool(cfg.get('strict', False))
    table, delimiter = read_csv(input_path)
    if not table:
        raise ValueError('input CSV is empty')
    headers = table[0]
    if not headers or len(set(headers)) != len(headers):
        raise ValueError('input header is missing or has duplicate column names')
    evidence = description_evidence(cfg.get('descriptions_path'), headers)
    resolved = {h: resolve(evidence[h]) for h in headers}
    output_rows, bad_rows = [], Counter()
    actions, outside, ambiguity = Counter(), Counter(), Counter()
    malformed_width = 0
    for row_number, row in enumerate(table[1:], start=2):
        if len(row) != len(headers):
            malformed_width += 1
            bad_rows['wrong_column_count'] += 1
            continue
        try:
            values = [parse_number(v) for v in row]
        except ValueError as exc:
            bad_rows[str(exc)] += 1
            continue
        newrow = []
        for h, value in zip(headers, values):
            key = resolved[h]
            if key:
                value, action = convert(value, key)
                actions[key + ':' + action] += 1
                if action.startswith('ambiguous'):
                    ambiguity[h] += 1
                if not inside(value, REGISTRY[key][1]):
                    outside[h] += 1
            newrow.append(fixed2(value))
        output_rows.append(newrow)
    if strict and outside:
        raise ValueError('strict validation failed; known analytes outside validation interval: ' + ', '.join(sorted(outside)))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator='\n')
        writer.writerow(headers)
        writer.writerows(output_rows)
    return {
        'output_path': str(out), 'input_columns': len(headers), 'output_columns': len(headers),
        'input_data_rows': max(0, len(table)-1), 'output_data_rows': len(output_rows),
        'dropped_rows': sum(bad_rows.values()), 'dropped_row_reasons': dict(bad_rows),
        'malformed_width_rows': malformed_width,
        'resolved_columns': {h:k for h,k in resolved.items() if k},
        'unresolved_columns': [h for h,k in resolved.items() if not k],
        'conversion_counts': dict(actions), 'ambiguous_cells': dict(ambiguity),
        'outside_validation_after': dict(outside), 'delimiter': delimiter,
        'all_retained_cells_fixed_two_decimals': True
    }

if __name__ == '__main__':
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError('stdin JSON must be an object')
        print(json.dumps(main(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stdout)
        sys.exit(2)
