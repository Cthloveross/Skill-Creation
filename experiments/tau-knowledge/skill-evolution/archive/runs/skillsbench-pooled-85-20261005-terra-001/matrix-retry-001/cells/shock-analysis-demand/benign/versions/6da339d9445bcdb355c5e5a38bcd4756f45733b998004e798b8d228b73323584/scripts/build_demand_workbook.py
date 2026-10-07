#!/usr/bin/env python3
import json, os, sys, tempfile
from copy import copy
import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from recalculate_workbook import recalculate

BLUE = PatternFill('solid', fgColor='D9EAF7')
YELLOW = PatternFill('solid', fgColor='FFF2CC')

def heading(cell, size=None):
    cell.font = Font(bold=True, size=size)
    cell.fill = BLUE

def replace_sheet(book, name, index=None):
    if name in book.sheetnames:
        del book[name]
    return book.create_sheet(name, index) if index is not None else book.create_sheet(name)

def copy_sheet(source, book, name):
    target = replace_sheet(book, name)
    for row in source.iter_rows():
        for old in row:
            new = target[old.coordinate]
            new.value = old.value
            if old.has_style:
                new._style = copy(old._style)
            new.number_format = old.number_format
    for key, dimension in source.column_dimensions.items():
        target.column_dimensions[key].width = dimension.width
        target.column_dimensions[key].hidden = dimension.hidden
    for key, dimension in source.row_dimensions.items():
        target.row_dimensions[key].height = dimension.height
    for merged in source.merged_cells.ranges:
        target.merge_cells(str(merged))

def pending_sut(book, name, note):
    ws = replace_sheet(book, name)
    ws['A1'] = name + ' source-entry table'
    heading(ws['A1'], 12)
    ws['A2'] = note or 'PENDING SOURCE: replace with verified official Geostat source table.'
    for col in range(1, 41):
        ws.cell(3, col).value = 'Commodity / industry' if col == 1 else 'S%02d' % (col - 1)
        heading(ws.cell(3, col))
    for row in range(4, 42):
        ws.cell(row, 1).value = 'Commodity %02d' % (row - 3)
        for col in range(2, 41):
            ws.cell(row, col).value = '=0'
            ws.cell(row, col).fill = YELLOW
    ws.column_dimensions['A'].width = 30
    ws.freeze_panes = 'B4'

def install_sut(book, payload):
    source_path = payload.get('sut_workbook_path')
    note = payload.get('sut_source_note', '')
    if source_path and os.path.isfile(source_path):
        source = openpyxl.load_workbook(source_path, data_only=False)
        for name in ('SUPPLY', 'USE'):
            if name not in source.sheetnames or source[name].max_row < 38 or source[name].max_column < 38:
                raise ValueError('source SUT must contain a 38-by-38-or-larger ' + name + ' sheet')
            copy_sheet(source[name], book, name)
    else:
        pending_sut(book, 'SUPPLY', note)
        pending_sut(book, 'USE', note)

def parse_weo(payload):
    raw = payload.get('weo')
    if raw is None:
        return {}, 'PENDING SOURCE: verified IMF WEO observations required'
    keys = ('years', 'real_gdp', 'real_growth', 'gdp_deflator')
    if not isinstance(raw, dict) or any(key not in raw for key in keys):
        raise ValueError('weo must contain years, real_gdp, real_growth, and gdp_deflator')
    years = raw['years']
    if not isinstance(years, list) or len(years) < 5 or years[-1] != 2027:
        raise ValueError('weo.years must be consecutive annual observations ending in 2027')
    if any(not isinstance(year, int) for year in years) or any(b != a + 1 for a, b in zip(years, years[1:])):
        raise ValueError('weo.years must be consecutive integer years')
    data = {}
    for key in keys[1:]:
        if not isinstance(raw[key], list) or len(raw[key]) != len(years):
            raise ValueError('weo.' + key + ' must align with weo.years')
        data[key] = dict(zip(years, raw[key]))
    return data, payload.get('weo_source_note', 'Verified IMF WEO observations supplied at runtime')

def build_weo(book, payload):
    data, note = parse_weo(payload)
    ws = replace_sheet(book, 'WEO_Data', 0)
    ws['A1'] = 'IMF WEO macroeconomic data and long-run Excel extension'
    heading(ws['A1'], 12)
    ws['A2'], ws['B2'] = 'Source / release / units', note
    labels = {
        3: 'Series / year',
        4: 'Real GDP (constant-price source units)',
        5: 'Real GDP growth (percent)',
        6: 'GDP deflator (index)',
        7: 'GDP deflator growth (percent)',
        9: 'Fixed recent-four-year average GDP-deflator growth anchor (percent)'
    }
    for row, label in labels.items():
        ws.cell(row, 1).value = label
        ws.cell(row, 1).font = Font(bold=True)
    columns = {}
    for col, year in enumerate(range(2023, 2044), 2):
        letter = get_column_letter(col)
        columns[year] = letter
        ws.cell(3, col).value = year
        heading(ws.cell(3, col))
        if year <= 2027:
            for row, key in ((4, 'real_gdp'), (5, 'real_growth'), (6, 'gdp_deflator')):
                value = data.get(key, {}).get(year)
                ws.cell(row, col).value = value if value is not None else '=0'
                if value is None:
                    ws.cell(row, col).fill = YELLOW
            if year > 2023:
                previous = get_column_letter(col - 1)
                ws.cell(7, col).value = '=IFERROR((%s6/%s6-1)*100,0)' % (letter, previous)
        else:
            previous = get_column_letter(col - 1)
            ws.cell(5, col).value = '=$F$5'
            ws.cell(4, col).value = '=IFERROR(%s4*(1+%s5/100),0)' % (previous, letter)
            if year == 2028:
                ws.cell(6, col).value = '=IFERROR(%s6*(1+AVERAGE(C7:F7)/100),0)' % previous
            else:
                ws.cell(6, col).value = '=IFERROR(%s6*(1+$F$9/100),0)' % previous
            ws.cell(7, col).value = '=$F$9'
    ws['F9'] = '=IFERROR(AVERAGE(C7:F7),0)'
    ws['A10'] = 'Observed WEO values end in 2027; 2028--2043 cells are formulas.'
    ws.column_dimensions['A'].width = 62
    for col in range(2, 23):
        ws.column_dimensions[get_column_letter(col)].width = 14
    ws.freeze_panes = 'B4'
    return columns

def sut_mapping(payload):
    defaults = {'first_data_row': 4, 'supply_import_column': 'B', 'supply_total_supply_column': 'C',
                'use_project_weight_column': 'B', 'use_check_column': 'C'}
    defaults.update(payload.get('sut_mapping') or {})
    if not isinstance(defaults['first_data_row'], int) or defaults['first_data_row'] < 1:
        raise ValueError('sut_mapping.first_data_row must be positive')
    for key in list(defaults)[1:]:
        if not isinstance(defaults[key], str) or not defaults[key].isalpha():
            raise ValueError('SUT mapping columns must be Excel letters')
    return defaults

def build_sut_calc(book, payload):
    mapping = sut_mapping(payload)
    ws = replace_sheet(book, 'SUT Calc', 1)
    ws['A1'] = 'Project import-content calculation from internal SUPPLY and USE'
    heading(ws['A1'], 12)
    ws['A2'], ws['B2'] = 'SUT source / mapping', payload.get('sut_source_note', 'Internal source sheets')
    headers = ('Commodity', 'Imports (SUPPLY)', 'Total supply (SUPPLY)', 'Import share',
               'Project/use weight (USE)', 'Weighted import share', 'USE check')
    for col, label in enumerate(headers, 2):
        ws.cell(7, col).value = label
        heading(ws.cell(7, col))
    for row in range(8, 46):
        source_row = mapping['first_data_row'] + row - 8
        ws.cell(row, 2).value = 'Commodity %02d' % (row - 7)
        ws.cell(row, 3).value = '=SUPPLY!%s%d' % (mapping['supply_import_column'], source_row)
        ws.cell(row, 4).value = '=SUPPLY!%s%d' % (mapping['supply_total_supply_column'], source_row)
        ws.cell(row, 5).value = '=IFERROR(C%d/D%d,0)' % (row, row)
        ws.cell(row, 6).value = '=USE!%s%d' % (mapping['use_project_weight_column'], source_row)
        ws.cell(row, 7).value = '=E%d*F%d' % (row, row)
        ws.cell(row, 8).value = '=USE!%s%d' % (mapping['use_check_column'], source_row)
    ws['B46'] = 'Estimated project import-content share'
    ws['B46'].font = Font(bold=True)
    ws['C46'] = '=IF(SUM(F8:F45)=0,0,SUMPRODUCT(E8:E45,F8:F45)/SUM(F8:F45))'
    ws['C46'].number_format = '0.0%'
    ws.freeze_panes = 'B8'

def build_na(book, weo_columns):
    # Recreate the model sheet so pre-existing template labels cannot be mistaken
    # for allocation or scenario rows by users or downstream workbook checks.
    ws = replace_sheet(book, 'NA')
    ws['A1'] = 'Demand-side macroeconomic investment shock model'
    heading(ws['A1'], 14)
    ws['A3'] = 'All calculated cells retain Excel formulas; amounts are GEL billions unless stated otherwise.'
    ws['A5'] = 'Project modelling horizon (annual columns used by every scenario)'
    heading(ws['A5'], 12)
    ws['A6'] = 'Project year'
    for col, year in enumerate(range(2026, 2034), 3):
        ws.cell(6, col).value = year
        heading(ws.cell(6, col))
    assumptions = (
        (30, 'GEL per USD exchange rate', 2.746),
        (31, 'Total project investment (USD billion)', 6.5),
        (32, 'Import-content share (linked to SUT Calc)', "='SUT Calc'!$C$46"),
        (33, 'Baseline demand multiplier', 0.8),
        (34, 'Project start year', 2026),
        (35, 'Project duration (years)', 8),
        (36, 'Total nominal investment (GEL billion)', '=$D$30*$D$31'),
        (37, 'GDP-deflator base', 100)
    )
    for row, label, value in assumptions:
        ws.cell(row, 3).value, ws.cell(row, 4).value = label, value
        ws.cell(row, 3).font = Font(bold=True)

    def scenario(start, title, local_import, local_multiplier):
        ws.cell(start, 1).value = title
        heading(ws.cell(start, 1), 12)
        # Place each alternative assumption locally as a numeric, labelled input.
        ws.cell(start + 1, 1).value, ws.cell(start + 1, 2).value = 'Local import-content share', local_import
        ws.cell(start + 2, 1).value, ws.cell(start + 2, 2).value = 'Local demand multiplier', local_multiplier
        for row in (start + 1, start + 2):
            ws.cell(row, 1).font = Font(bold=True)
            ws.cell(row, 2).fill = YELLOW
        for col, year in enumerate(range(2026, 2034), 3):
            ws.cell(start + 3, col).value = year
            heading(ws.cell(start + 3, col))
        labels = ('Baseline real GDP (WEO link)', 'GDP deflator (WEO link)',
                  'Bell-shaped project allocation share', 'Nominal project investment (GEL bn)',
                  'Real project investment (GEL bn)', 'Domestic demand impulse (GEL bn)',
                  'GDP increment (GEL bn)', 'With-shock real GDP (GEL bn)')
        for offset, label in enumerate(labels, 4):
            ws.cell(start + offset, 1).value = label
        for col, year in enumerate(range(2026, 2034), 3):
            letter = get_column_letter(col)
            ws.cell(start + 4, col).value = "='WEO_Data'!$%s$4" % weo_columns[year]
            ws.cell(start + 5, col).value = "='WEO_Data'!$%s$6" % weo_columns[year]
            ws.cell(start + 6, col).value = '=CHOOSE(%s$%d-$D$34+1,1,2,3,4,4,3,2,1)/20' % (letter, start + 3)
            ws.cell(start + 7, col).value = '=%s%d*$D$36' % (letter, start + 6)
            ws.cell(start + 8, col).value = '=IFERROR(%s%d/(%s%d/$D$37),0)' % (letter, start + 7, letter, start + 5)
            ws.cell(start + 9, col).value = '=%s%d*(1-$B$%d)' % (letter, start + 8, start + 1)
            ws.cell(start + 10, col).value = '=%s%d*$B$%d' % (letter, start + 9, start + 2)
            ws.cell(start + 11, col).value = '=%s%d+%s%d' % (letter, start + 4, letter, start + 10)
            ws.cell(start + 6, col).number_format = '0.00%'
        return start + 11

    end = scenario(40, 'Scenario 1: baseline', '=$D$32', '=$D$33')
    end = scenario(end + 4, 'Scenario 2: demand multiplier = 1', '=$D$32', 1.0)
    scenario(end + 4, 'Scenario 3: import content = 0.5', 0.5, '=$D$33')
    ws.column_dimensions['A'].width = 42
    ws.column_dimensions['B'].width = 16
    for col in range(3, 11):
        ws.column_dimensions[get_column_letter(col)].width = 15
    ws.freeze_panes = 'C40'

def main(payload):
    template = payload.get('template_path')
    output = payload.get('output_path', template)
    if not isinstance(template, str) or not os.path.isfile(template):
        raise ValueError('template_path must identify an existing workbook')
    if not isinstance(output, str) or not output:
        raise ValueError('output_path must be nonempty')
    book = openpyxl.load_workbook(template, data_only=False)
    install_sut(book, payload)
    columns = build_weo(book, payload)
    build_sut_calc(book, payload)
    build_na(book, columns)
    if getattr(book, 'calculation', None):
        book.calculation.calcMode = 'auto'
        book.calculation.fullCalcOnLoad = True
        book.calculation.forceFullCalc = True
    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='demand_shock_', suffix='.xlsx', dir=os.path.dirname(output))
    os.close(fd)
    try:
        book.save(temporary)
        os.replace(temporary, output)
        recalculate(output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'ok': True, 'output_path': output, 'sheets': book.sheetnames, 'recalculated': True}

if __name__ == '__main__':
    try:
        result = main(json.load(sys.stdin))
    except Exception as exc:
        result = {'ok': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['ok'] else 1)
