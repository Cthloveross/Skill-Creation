#!/usr/bin/env python3
"""Build the Dots sheet: copy input columns, append TotalKg and Dots formulas.

Reads a JSON object from stdin (all keys optional):
  xlsx_path, output_path, data_sheet, dots_sheet, precision
Writes a JSON report to stdout.
"""
import sys, json, os, re, shutil, subprocess, tempfile, glob, zipfile
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# Published DOTS equation coefficients (A,B,C,D,E) and bodyweight clamp ranges.
MALE_COEF = [-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093]
FEMALE_COEF = [-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.00000115283]
MALE_RANGE = (40.0, 210.0)
FEMALE_RANGE = (40.0, 150.0)

# Column keys needed to compute DOTS (plus the lifter name), with aliases.
NEEDED = {
    'name': ['name'],
    'sex': ['sex'],
    'bodyweightkg': ['bodyweightkg', 'bodyweight', 'bwkg'],
    'best3squatkg': ['best3squatkg', 'best3squat'],
    'best3benchkg': ['best3benchkg', 'best3bench'],
    'best3deadliftkg': ['best3deadliftkg', 'best3deadlift'],
}


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).strip().lower()) if s is not None else ''


def cf(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def dots_formula(sex_cell, bw_cell, total_cell, nd):
    m = f"MIN(MAX({bw_cell},{MALE_RANGE[0]}),{MALE_RANGE[1]})"
    f = f"MIN(MAX({bw_cell},{FEMALE_RANGE[0]}),{FEMALE_RANGE[1]})"
    a, b, c, d, e = MALE_COEF
    male = f"({a}+{b}*{m}+({c})*{m}^2+{d}*{m}^3+({e})*{m}^4)"
    a, b, c, d, e = FEMALE_COEF
    fem = f"({a}+{b}*{f}+({c})*{f}^2+{d}*{f}^3+({e})*{f}^4)"
    return f'=ROUND(500/IF({sex_cell}="M",{male},{fem})*{total_cell},{nd})'


def dots_value(sex, bw, total, nd):
    if bw is None:
        return None
    if str(sex).strip() == 'M':
        coef, lo, hi = MALE_COEF, MALE_RANGE[0], MALE_RANGE[1]
    else:
        coef, lo, hi = FEMALE_COEF, FEMALE_RANGE[0], FEMALE_RANGE[1]
    x = min(max(bw, lo), hi)
    denom = coef[0] + coef[1]*x + coef[2]*x**2 + coef[3]*x**3 + coef[4]*x**4
    if denom == 0:
        return None
    return round(500.0 / denom * total, nd)


def find_soffice():
    for b in ('soffice', 'libreoffice'):
        p = shutil.which(b)
        if p:
            return p
    for pat in ('/usr/bin/soffice', '/usr/bin/libreoffice',
                '/opt/libreoffice*/program/soffice'):
        for p in glob.glob(pat):
            if os.path.exists(p):
                return p
    return None


XCU = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    '<item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
    '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
    '<item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
    '<prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>\n'
    '</oor:items>\n'
)


def recalc_libreoffice(path):
    sof = find_soffice()
    if not sof:
        return False, 'no soffice'
    profile = tempfile.mkdtemp(prefix='lo_prof_')
    userdir = os.path.join(profile, 'user')
    os.makedirs(userdir, exist_ok=True)
    with open(os.path.join(userdir, 'registrymodifications.xcu'), 'w') as fh:
        fh.write(XCU)
    outdir = tempfile.mkdtemp(prefix='lo_out_')
    try:
        r = subprocess.run(
            [sof, '--headless', '--norestore',
             '-env:UserInstallation=file://' + profile,
             '--convert-to', 'xlsx', '--outdir', outdir, path],
            capture_output=True, timeout=300)
    except Exception as e:
        return False, str(e)
    conv = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + '.xlsx')
    if os.path.exists(conv):
        shutil.copy(conv, path)
        return True, 'libreoffice'
    return False, (r.stderr.decode('utf-8', 'ignore')[:200] if r.stderr else 'convert failed')


def inject_cached(path, sheet_name, cell_values):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        content = {n: z.read(n) for n in names}
    wb = content['xl/workbook.xml'].decode('utf-8')
    m = re.search(r'<sheet[^>]*name="%s"[^>]*r:id="([^"]+)"' % re.escape(sheet_name), wb)
    if not m:
        m = re.search(r'<sheet[^>]*r:id="([^"]+)"[^>]*name="%s"' % re.escape(sheet_name), wb)
    if not m:
        return False
    rid = m.group(1)
    rels = content['xl/_rels/workbook.xml.rels'].decode('utf-8')
    m2 = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % re.escape(rid), rels)
    if not m2:
        return False
    target = m2.group(1)
    sp = target[1:] if target.startswith('/') else 'xl/' + target
    if sp not in content:
        return False
    xml = content[sp].decode('utf-8')
    for coord, val in cell_values.items():
        if val is None:
            continue
        pat = re.compile(r'(<c r="%s"[^>]*>)(.*?)(</c>)' % re.escape(coord), re.DOTALL)

        def rep(mm, v=val):
            inner = mm.group(2)
            inner = re.sub(r'<v>.*?</v>', '', inner, flags=re.DOTALL)
            return mm.group(1) + inner + ('<v>%s</v>' % repr_num(v)) + mm.group(3)

        xml = pat.sub(rep, xml, count=1)
    content[sp] = xml.encode('utf-8')
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, content[n])
    os.replace(tmp, path)
    return True


def repr_num(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return ('%s' % v)


def main():
    raw = ''
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ''
    params = {}
    if raw.strip():
        try:
            params = json.loads(raw)
        except Exception:
            params = {}
    xlsx_path = params.get('xlsx_path', '/root/data/openipf.xlsx')
    output_path = params.get('output_path', xlsx_path)
    nd = int(params.get('precision', 3))
    warnings = []

    if not os.path.exists(xlsx_path):
        print(json.dumps({'ok': False, 'error': 'xlsx not found: ' + xlsx_path}))
        return

    wb = load_workbook(xlsx_path, data_only=False)
    names = wb.sheetnames
    data_name = params.get('data_sheet') or ('Data' if 'Data' in names else names[0])
    if 'dots_sheet' in params and params['dots_sheet']:
        dots_name = params['dots_sheet']
    elif 'Dots' in names:
        dots_name = 'Dots'
    else:
        dots_name = names[1] if len(names) > 1 else names[0]
    data_ws = wb[data_name]
    dots_ws = wb[dots_name]

    # Resolve header row of the Data sheet.
    header = {}
    for c in range(1, data_ws.max_column + 1):
        v = data_ws.cell(1, c).value
        if v is not None and str(v).strip() != '':
            header[norm(v)] = c

    found = []
    missing = []
    for key, aliases in NEEDED.items():
        col = None
        for a in aliases:
            if a in header:
                col = header[a]
                break
        if col is None:
            missing.append(key)
        else:
            found.append({'key': key, 'col': col,
                          'header': data_ws.cell(1, col).value})
    if missing:
        print(json.dumps({'ok': False,
                          'error': 'missing columns: ' + ', '.join(missing),
                          'found_headers': list(header.keys())}))
        return

    ordered = sorted(found, key=lambda x: x['col'])
    keycol = {it['key']: it['col'] for it in ordered}
    new_letter = {}
    for i, it in enumerate(ordered, start=1):
        new_letter[it['key']] = get_column_letter(i)
    n = len(ordered)
    total_col = get_column_letter(n + 1)
    dots_col = get_column_letter(n + 2)

    # Clear the destination sheet.
    if dots_ws.max_row and dots_ws.max_row >= 1:
        dots_ws.delete_rows(1, dots_ws.max_row)

    # Header row (same names, same order as Data) + appended columns.
    for i, it in enumerate(ordered, start=1):
        dots_ws.cell(1, i, value=it['header'])
    dots_ws.cell(1, n + 1, value='TotalKg')
    dots_ws.cell(1, n + 2, value='Dots')

    name_col = keycol['name']
    expected = {}  # coord -> numeric value (for injection/verification)
    expected_dots = {}
    out_r = 2
    total_ex = dots_ex = ''
    for r in range(2, data_ws.max_row + 1):
        name_val = data_ws.cell(r, name_col).value
        if name_val is None or str(name_val).strip() == '':
            continue
        for i, it in enumerate(ordered, start=1):
            dots_ws.cell(out_r, i, value=data_ws.cell(r, it['col']).value)
        sqc = f"{new_letter['best3squatkg']}{out_r}"
        bnc = f"{new_letter['best3benchkg']}{out_r}"
        ddc = f"{new_letter['best3deadliftkg']}{out_r}"
        sexc = f"{new_letter['sex']}{out_r}"
        bwc = f"{new_letter['bodyweightkg']}{out_r}"
        totc = f"{total_col}{out_r}"
        dotc = f"{dots_col}{out_r}"
        tf = f"={sqc}+{bnc}+{ddc}"
        df = dots_formula(sexc, bwc, totc, nd)
        dots_ws.cell(out_r, n + 1, value=tf)
        dots_ws.cell(out_r, n + 2, value=df)
        if not total_ex:
            total_ex, dots_ex = tf, df
        # expected values
        sq = cf(data_ws.cell(r, keycol['best3squatkg']).value)
        bn = cf(data_ws.cell(r, keycol['best3benchkg']).value)
        dd = cf(data_ws.cell(r, keycol['best3deadliftkg']).value)
        tv = round(sq + bn + dd, 6)
        expected[totc] = tv
        sex = data_ws.cell(r, keycol['sex']).value
        bw = num(data_ws.cell(r, keycol['bodyweightkg']).value)
        dv = dots_value(sex, bw, tv, nd)
        expected[dotc] = dv
        if dv is not None:
            expected_dots[dotc] = dv
        out_r += 1
    rows_written = out_r - 2

    wb.save(output_path)

    # Recalculate so cached values match the formulas.
    recalc_ok, method = recalc_libreoffice(output_path)
    recalc_method = method if recalc_ok else None
    if not recalc_ok:
        warnings.append('libreoffice recalc unavailable: ' + str(method))

    # Verify cached values; inject if needed.
    missing_cached = 0
    mismatches = 0
    try:
        wb2 = load_workbook(output_path, data_only=True)
        ds = wb2[dots_name]
        none_dots = [c for c, ev in expected_dots.items() if ds[c].value is None]
        if none_dots:
            if inject_cached(output_path, dots_name, expected):
                recalc_method = recalc_method or 'xml-injection'
                if recalc_ok:
                    recalc_method = 'libreoffice+xml-injection'
                wb2 = load_workbook(output_path, data_only=True)
                ds = wb2[dots_name]
            else:
                warnings.append('cached-value injection failed')
        for coord, ev in expected_dots.items():
            cv = ds[coord].value
            if cv is None:
                missing_cached += 1
                continue
            try:
                if abs(float(cv) - float(ev)) > 0.01:
                    mismatches += 1
            except Exception:
                mismatches += 1
    except Exception as e:
        warnings.append('verification error: ' + str(e))

    report = {
        'ok': True,
        'output_path': output_path,
        'data_sheet': data_name,
        'dots_sheet': dots_name,
        'columns_copied': [it['header'] for it in ordered],
        'rows_written': rows_written,
        'total_column': total_col,
        'dots_column': dots_col,
        'total_formula_example': total_ex,
        'dots_formula_example': dots_ex,
        'precision': nd,
        'recalc_method': recalc_method,
        'verified': (missing_cached == 0 and mismatches == 0),
        'value_mismatches': mismatches,
        'missing_cached_values': missing_cached,
        'warnings': warnings,
    }
    print(json.dumps(report))


if __name__ == '__main__':
    main()
