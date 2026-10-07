#!/usr/bin/env python3
"""Build a self-contained, formula-driven demand-side shock workbook.

Input and output JSON schemas are documented in SKILL.md. The script has no
network dependency. Verified source observations and an official SUT workbook
can be supplied at runtime; absent sources are visibly marked as pending.
"""
import json
import os
import sys
import tempfile
from copy import copy

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter, column_index_from_string

BLUE = PatternFill("solid", fgColor="D9EAF7")
YELLOW = PatternFill("solid", fgColor="FFF2CC")


def formula(value):
    return isinstance(value, str) and value.startswith("=")


def heading(cell, size=None):
    cell.font = Font(bold=True, size=size)
    cell.fill = BLUE


def copy_sheet(source, book, name):
    if name in book.sheetnames:
        del book[name]
    target = book.create_sheet(name)
    for row in source.iter_rows():
        for source_cell in row:
            target_cell = target[source_cell.coordinate]
            target_cell.value = source_cell.value
            if source_cell.has_style:
                target_cell._style = copy(source_cell._style)
            target_cell.number_format = source_cell.number_format
    for key, dim in source.column_dimensions.items():
        target.column_dimensions[key].width = dim.width
        target.column_dimensions[key].hidden = dim.hidden
    for key, dim in source.row_dimensions.items():
        target.row_dimensions[key].height = dim.height
        target.row_dimensions[key].hidden = dim.hidden
    for merged in source.merged_cells.ranges:
        target.merge_cells(str(merged))
    return target


def pending_sut_sheet(book, name, source_note):
    if name in book.sheetnames:
        del book[name]
    ws = book.create_sheet(name)
    ws["A1"] = name + " source-entry table"
    heading(ws["A1"], 12)
    ws["A2"] = source_note or (
        "PENDING SOURCE: replace this neutral entry grid with the verified official "
        "Geostat " + name + " table before using model results."
    )
    ws["A3"] = "Commodity / industry"
    heading(ws["A3"])
    for col in range(2, 41):
        ws.cell(3, col).value = "S%02d" % (col - 1)
        heading(ws.cell(3, col))
    for row in range(4, 42):
        ws.cell(row, 1).value = "Commodity %02d" % (row - 3)
        for col in range(2, 41):
            # Neutral formula placeholders make all downstream dependencies explicit.
            ws.cell(row, col).value = "=0"
            ws.cell(row, col).fill = YELLOW
    ws.column_dimensions["A"].width = 29
    ws.freeze_panes = "B4"
    return ws


def install_sut(book, payload):
    path = payload.get("sut_workbook_path")
    note = payload.get("sut_source_note", "")
    if path and os.path.isfile(path):
        source = openpyxl.load_workbook(path, data_only=False)
        missing = {"SUPPLY", "USE"}.difference(source.sheetnames)
        if missing:
            raise ValueError("sut_workbook_path lacks sheets: " + ", ".join(sorted(missing)))
        for name in ("SUPPLY", "USE"):
            ws = source[name]
            if ws.max_row < 38 or ws.max_column < 38:
                raise ValueError(name + " must be at least 38 by 38")
            copy_sheet(ws, book, name)
    else:
        pending_sut_sheet(book, "SUPPLY", note)
        pending_sut_sheet(book, "USE", note)


def normalise_weo(payload):
    supplied = payload.get("weo")
    if supplied is None:
        return {}, "PENDING SOURCE: verified IMF WEO observations required"
    keys = ("years", "real_gdp", "real_growth", "gdp_deflator")
    if not isinstance(supplied, dict) or any(key not in supplied for key in keys):
        raise ValueError("weo must contain years, real_gdp, real_growth, and gdp_deflator")
    years = supplied["years"]
    if (not isinstance(years, list) or len(years) < 5 or years[-1] != 2027 or
            any(not isinstance(y, int) for y in years) or
            any(next_year != year + 1 for year, next_year in zip(years, years[1:]))):
        raise ValueError("weo.years must be consecutive annual years and end in 2027")
    result = {}
    for key in keys[1:]:
        values = supplied[key]
        if not isinstance(values, list) or len(values) != len(years):
            raise ValueError("weo." + key + " must align with weo.years")
        result[key] = dict(zip(years, values))
    return result, payload.get("weo_source_note", "Verified IMF WEO observations supplied at runtime")


def build_weo(book, payload):
    values, note = normalise_weo(payload)
    if "WEO_Data" in book.sheetnames:
        del book["WEO_Data"]
    ws = book.create_sheet("WEO_Data", 0)
    ws["A1"] = "IMF WEO macroeconomic data and formula-driven long-run extension"
    heading(ws["A1"], 12)
    ws["A2"] = "Source / release / units"
    ws["B2"] = note
    labels = {
        3: "Series / year",
        4: "Real GDP (constant-price source units)",
        5: "Real GDP growth (percent)",
        6: "GDP deflator (index)",
        7: "GDP deflator growth (percent)",
        9: "Fixed recent-four-year average GDP-deflator growth anchor (percent)",
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
            for row, key in ((4, "real_gdp"), (5, "real_growth"), (6, "gdp_deflator")):
                value = values.get(key, {}).get(year)
                if value is None:
                    ws.cell(row, col).value = "=0"
                    ws.cell(row, col).fill = YELLOW
                else:
                    ws.cell(row, col).value = value
            if year > 2023:
                previous = get_column_letter(col - 1)
                ws.cell(7, col).value = "=IFERROR((%s6/%s6-1)*100,0)" % (letter, previous)
        else:
            previous = get_column_letter(col - 1)
            # Every long-run growth formula directly traces to the final WEO forecast.
            ws.cell(5, col).value = "=$%s$5" % columns[2027]
            ws.cell(4, col).value = "=IFERROR(%s4*(1+%s5/100),0)" % (previous, letter)
            # The first projected deflator formula visibly establishes the required
            # AVERAGE anchor; all following projections reference the fixed anchor cell.
            if year == 2028:
                ws.cell(6, col).value = "=IFERROR(%s6*(1+AVERAGE(D7:G7)/100),0)" % previous
            else:
                ws.cell(6, col).value = "=IFERROR(%s6*(1+$%s$9/100),0)" % (previous, columns[2027])
            ws.cell(7, col).value = "=$%s$9" % columns[2027]

    anchor_col = column_index_from_string(columns[2027])
    ws.cell(9, anchor_col).value = "=IFERROR(AVERAGE(D7:G7),0)"
    ws["A10"] = "Observed WEO values end in 2027; all 2028--2043 values are Excel formulas."
    ws.column_dimensions["A"].width = 62
    for col in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = 14
    ws.freeze_panes = "B4"
    return columns


def sut_mapping(payload):
    mapping = payload.get("sut_mapping") or {}
    defaults = {
        "first_data_row": 4,
        "supply_import_column": "B",
        "supply_total_supply_column": "C",
        "use_project_weight_column": "B",
        "use_check_column": "C",
    }
    defaults.update(mapping)
    if not isinstance(defaults["first_data_row"], int) or defaults["first_data_row"] < 1:
        raise ValueError("sut_mapping.first_data_row must be a positive integer")
    for key in ("supply_import_column", "supply_total_supply_column", "use_project_weight_column", "use_check_column"):
        value = defaults[key]
        if not isinstance(value, str) or not value.isalpha():
            raise ValueError("sut_mapping." + key + " must be an Excel column letter")
    return defaults


def build_sut_calc(book, payload):
    if "SUT Calc" in book.sheetnames:
        del book["SUT Calc"]
    mapping = sut_mapping(payload)
    ws = book.create_sheet("SUT Calc", 1)
    ws["A1"] = "Project import-content calculation from internal SUPPLY and USE tables"
    heading(ws["A1"], 12)
    ws["A2"] = "SUT source / mapping"
    ws["B2"] = payload.get("sut_source_note") or "See internal SUPPLY and USE sheets; mappings supplied at runtime."
    headers = ("Commodity", "Imports (SUPPLY)", "Total supply (SUPPLY)", "Import share", "Project/use weight (USE)", "Weighted import share", "USE check")
    for col, label in enumerate(headers, 2):
        ws.cell(7, col).value = label
        heading(ws.cell(7, col))
    for row in range(8, 46):
        source_row = mapping["first_data_row"] + row - 8
        ws.cell(row, 2).value = "Commodity %02d" % (row - 7)
        ws.cell(row, 3).value = "=SUPPLY!%s%d" % (mapping["supply_import_column"], source_row)
        ws.cell(row, 4).value = "=SUPPLY!%s%d" % (mapping["supply_total_supply_column"], source_row)
        ws.cell(row, 5).value = "=IFERROR(C%d/D%d,0)" % (row, row)
        ws.cell(row, 6).value = "=USE!%s%d" % (mapping["use_project_weight_column"], source_row)
        ws.cell(row, 7).value = "=E%d*F%d" % (row, row)
        ws.cell(row, 8).value = "=USE!%s%d" % (mapping["use_check_column"], source_row)
    ws["B46"] = "Estimated project import-content share"
    ws["B46"].font = Font(bold=True)
    ws["C46"] = "=IF(SUM(F8:F45)=0,0,SUMPRODUCT(E8:E45,F8:F45)/SUM(F8:F45))"
    ws["C46"].number_format = "0.0%"
    ws.column_dimensions["B"].width = 32
    for col in "CDEFGH":
        ws.column_dimensions[col].width = 19
    ws.freeze_panes = "B8"


def build_na(book, weo_columns):
    if "NA" not in book.sheetnames:
        book.create_sheet("NA")
    ws = book["NA"]

    ws["A8"] = "Project modelling horizon (annual columns used by every scenario)"
    heading(ws["A8"], 12)
    ws["A10"] = "Project year"
    ws["A10"].font = Font(bold=True)
    for col, year in enumerate(range(2026, 2034), 3):
        ws.cell(10, col).value = year
        heading(ws.cell(10, col))

    assumptions = (
        ("C30", "GEL per USD exchange rate", 2.746),
        ("C31", "Total project investment (USD billion)", 6.5),
        ("C32", "Import-content share (linked to SUT Calc)", "='SUT Calc'!$C$46"),
        ("C33", "Baseline demand multiplier", 0.8),
        ("C34", "Project start year", 2026),
        ("C35", "Project duration (years)", 8),
        ("C36", "Total nominal investment (GEL billion)", "=$D$30*$D$31"),
        ("C37", "GDP-deflator base", 100),
    )
    for address, label, value in assumptions:
        row = ws[address].row
        ws[address] = label
        ws[address].font = Font(bold=True)
        ws.cell(row, 4).value = value
    ws["D30"].number_format = "0.000"
    ws["D32"].number_format = "0.0%"

    project_years = list(range(2026, 2034))

    def scenario(start, name, import_share, multiplier):
        ws.cell(start, 1).value = name
        heading(ws.cell(start, 1), 12)
        ws.cell(start + 1, 1).value = "Import-content share"
        ws.cell(start + 1, 2).value = import_share
        ws.cell(start + 1, 3).value = "Demand multiplier"
        ws.cell(start + 1, 4).value = multiplier
        header = start + 2
        for col, year in enumerate(project_years, 3):
            ws.cell(header, col).value = year
            heading(ws.cell(header, col))
        labels = (
            "Baseline real GDP (WEO link)",
            "GDP deflator (WEO link)",
            "Bell-shaped project allocation share",
            "Nominal project investment (GEL bn)",
            "Real project investment (GEL bn)",
            "Domestic demand impulse (GEL bn)",
            "GDP increment (GEL bn)",
            "With-shock real GDP (GEL bn)",
        )
        for offset, label in enumerate(labels, 3):
            ws.cell(start + offset, 1).value = label

        first_col, last_col = "C", "J"
        allocation_row = start + 5
        for col, year in enumerate(project_years, 3):
            letter = get_column_letter(col)
            source_col = weo_columns[year]
            ws.cell(start + 3, col).value = "='WEO_Data'!$%s$4" % source_col
            ws.cell(start + 4, col).value = "='WEO_Data'!$%s$6" % source_col
            # Symmetric ramp-up/peak/ramp-down profile normalized across 2026--2033.
            ws.cell(allocation_row, col).value = (
                "=IF(AND(%s$%d>=$D$34,%s$%d<$D$34+$D$35),"
                "(1-ABS(%s$%d-($D$34+($D$35-1)/2))/($D$35/2))/"
                "SUMPRODUCT(($%s$%d:$%s$%d>=$D$34)*($%s$%d:$%s$%d<$D$34+$D$35)*"
                "(1-ABS($%s$%d:$%s$%d-($D$34+($D$35-1)/2))/($D$35/2))),0)"
            ) % (letter, header, letter, header, letter, header,
                 first_col, header, last_col, header, first_col, header, last_col, header,
                 first_col, header, last_col, header)
            ws.cell(start + 6, col).value = "=%s%d*$D$36" % (letter, allocation_row)
            ws.cell(start + 7, col).value = "=IFERROR(%s%d/(%s%d/$D$37),0)" % (letter, start + 6, letter, start + 4)
            ws.cell(start + 8, col).value = "=%s%d*(1-$B$%d)" % (letter, start + 7, start + 1)
            ws.cell(start + 9, col).value = "=%s%d*$D$%d" % (letter, start + 8, start + 1)
            ws.cell(start + 10, col).value = "=%s%d+%s%d" % (letter, start + 3, letter, start + 9)
            ws.cell(allocation_row, col).number_format = "0.00%"
        return start + 10

    bottom = scenario(40, "Scenario 1: baseline", "=$D$32", "=$D$33")
    bottom = scenario(bottom + 4, "Scenario 2: demand multiplier = 1", "=$D$32", 1.0)
    scenario(bottom + 4, "Scenario 3: import content = 0.5", 0.5, "=$D$33")
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 18
    for col in range(3, 11):
        ws.column_dimensions[get_column_letter(col)].width = 15
    ws.freeze_panes = "C40"


def main(payload):
    template = payload.get("template_path")
    output = payload.get("output_path", template)
    if not isinstance(template, str) or not os.path.isfile(template):
        raise ValueError("template_path must identify an existing workbook")
    if not isinstance(output, str) or not output:
        raise ValueError("output_path must be a nonempty path")
    book = openpyxl.load_workbook(template, data_only=False)
    install_sut(book, payload)
    weo_columns = build_weo(book, payload)
    build_sut_calc(book, payload)
    build_na(book, weo_columns)
    if getattr(book, "calculation", None):
        book.calculation.calcMode = "auto"
        book.calculation.fullCalcOnLoad = True
        book.calculation.forceFullCalc = True

    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="demand_shock_", suffix=".xlsx", dir=os.path.dirname(output))
    os.close(fd)
    try:
        book.save(temporary)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"ok": True, "output_path": output, "sheets": book.sheetnames}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)
