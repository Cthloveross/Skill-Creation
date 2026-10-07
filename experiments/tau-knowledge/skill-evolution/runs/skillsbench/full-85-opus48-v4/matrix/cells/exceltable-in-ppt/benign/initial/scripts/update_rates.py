"""Update one currency pair in a pptx-embedded Excel table.

stdin JSON:
  {"pptx_in": "/root/input.pptx",
   "pptx_out": "/root/results.pptx",
   "override": {"from": "USD", "to": "EUR", "rate": 0.85}  // optional
  }

stdout JSON: a report (see SKILL.md). Writes pptx_out only when the update and
validation succeed.
"""
import io
import json
import sys

from openpyxl.utils import get_column_letter

import pptx_xlsx as P


def _addr(row0, col0):
    return "%s%d" % (get_column_letter(col0 + 1), row0 + 1)


def pick_embedding(data):
    """Return (part_name, xlsx_bytes, wb, ws, grid, matrix) for the best match."""
    best = None
    for name, xb in P.list_embeddings(data):
        try:
            wb, ws, grid = P.load_sheet_grid(xb)
        except Exception:  # noqa: BLE001
            continue
        mx = P.find_matrix(grid)
        if mx is None:
            continue
        score = len(mx["currencies"])
        if best is None or score > best[0]:
            best = (score, name, xb, wb, ws, grid, mx)
    if best is None:
        return None
    _, name, xb, wb, ws, grid, mx = best
    return name, xb, wb, ws, grid, mx


def main():
    req = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    pptx_in = req.get("pptx_in", "/root/input.pptx")
    pptx_out = req.get("pptx_out", "/root/results.pptx")
    override = req.get("override")

    report = {"pptx_in": pptx_in, "pptx_out": pptx_out, "validation": {}}
    data = P.read_zip(pptx_in)

    picked = pick_embedding(data)
    if picked is None:
        report["error"] = "no embedded workbook with a currency matrix found"
        report["embeddings"] = [n for n, _ in P.list_embeddings(data)]
        report["validation"]["ok"] = False
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    part_name, xb, wb, ws, grid, mx = picked
    report["embedding_part"] = part_name
    report["sheet"] = ws.title
    report["currencies"] = sorted(mx["currencies"])

    text = P.all_slide_text(data)
    report["textbox_text"] = text

    if override and all(k in override for k in ("from", "to", "rate")):
        det = {"from": str(override["from"]).upper(),
               "to": str(override["to"]).upper(),
               "rate": float(override["rate"]), "source": "override"}
    else:
        det = P.detect_rate(text, mx["currencies"])
        if det:
            det["source"] = "textbox"
    report["detected"] = det
    if not det:
        report["error"] = "could not detect a currency pair and rate"
        report["validation"]["ok"] = False
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    frm, to, rate = det["from"], det["to"], det["rate"]
    col_of, row_of = mx["col_of"], mx["row_of"]
    if frm not in row_of or to not in col_of:
        report["error"] = "detected currencies not in matrix axes"
        report["validation"]["ok"] = False
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # candidate cells (openpyxl is 1-based)
    direct_r = row_of[frm] + 1
    direct_c = col_of[to] + 1
    direct = ws.cell(row=direct_r, column=direct_c)

    inv_cell = None
    if to in row_of and frm in col_of:
        inv_cell = ws.cell(row=row_of[to] + 1, column=col_of[frm] + 1)

    formulas_before = P.count_formulas(ws)

    updated = None
    if not P.is_formula(direct):
        direct.value = float(rate)
        updated = {"addr": _addr(direct_r - 1, direct_c - 1),
                   "from": frm, "to": to, "value": float(rate),
                   "which": "direct"}
    elif inv_cell is not None and not P.is_formula(inv_cell):
        inv_val = 1.0 / float(rate)
        inv_cell.value = inv_val
        updated = {"addr": _addr(inv_cell.row - 1, inv_cell.column - 1),
                   "from": to, "to": frm, "value": inv_val,
                   "which": "inverse"}
    else:
        report["error"] = ("target pair cell is a formula and no value cell is "
                            "available to update without overwriting a formula")
        report["validation"]["ok"] = False
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    report["updated_cell"] = updated

    # save workbook, keeping formula text intact
    buf = io.BytesIO()
    wb.save(buf)
    new_xlsx = buf.getvalue()

    new_pptx = P.replace_embedding(data, part_name, new_xlsx)
    with open(pptx_out, "wb") as fh:
        fh.write(new_pptx)
    report["written"] = pptx_out

    # ---- validation: reopen output and verify ----
    v = report["validation"]
    out_data = P.read_zip(pptx_out)
    v["output_part_count_equal"] = (P.part_count(data) == P.part_count(out_data))
    report["parts_preserved"] = {"input": P.part_count(data),
                                 "output": P.part_count(out_data)}

    picked2 = pick_embedding(out_data)
    ok_cell = False
    formulas_after = None
    if picked2 is not None:
        _, _, wb2, ws2, _, _ = picked2
        formulas_after = P.count_formulas(ws2)
        cell2 = ws2[updated["addr"]]
        try:
            ok_cell = abs(float(cell2.value) - float(updated["value"])) <= \
                1e-9 * max(1.0, abs(float(updated["value"])))
        except (TypeError, ValueError):
            ok_cell = False
    report["formulas_preserved"] = {"before": formulas_before,
                                    "after": formulas_after}
    v["target_cell_updated"] = ok_cell
    v["formulas_preserved"] = (formulas_after == formulas_before)
    v["ok"] = bool(v["output_part_count_equal"] and ok_cell and
                   v["formulas_preserved"])

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
