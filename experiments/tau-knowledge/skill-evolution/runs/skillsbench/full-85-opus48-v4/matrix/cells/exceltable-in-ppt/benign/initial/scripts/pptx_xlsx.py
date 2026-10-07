"""Helpers for inspecting/editing an Excel workbook embedded in a .pptx.

All discovery is done at runtime from the supplied package; nothing about the
current file's sheets, cells, currencies or rate is hard-coded.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

CODE_RE = re.compile(r"\b([A-Za-z]{3})\b")
NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def read_zip(path):
    with open(path, "rb") as fh:
        return fh.read()


def list_embeddings(data):
    """Return [(part_name, bytes)] for embedded .xlsx parts."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            low = name.lower()
            if "embeddings" in low and low.endswith(".xlsx"):
                out.append((name, zf.read(name)))
    return out


def slide_texts(data):
    """Return {slide_part: joined_text} for all slide XML parts."""
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    texts = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            low = name.lower()
            if re.search(r"ppt/slides/slide\d+\.xml$", low):
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue
                runs = [el.text or "" for el in root.iter("{%s}t" % ns_a)]
                texts[name] = " ".join(r for r in runs if r.strip())
    return texts


def all_slide_text(data):
    return "  ".join(slide_texts(data).values())


def load_sheet_grid(xlsx_bytes):
    """Return (openpyxl workbook, worksheet, 2D list of displayed values).

    Uses data_only=False so formulas are kept as text.
    """
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
    best = None
    best_score = -1
    for ws in wb.worksheets:
        grid = [[c.value for c in row] for row in ws.iter_rows()]
        score = _matrix_score(grid)
        if score > best_score:
            best_score = score
            best = (ws, grid)
    ws, grid = best
    return wb, ws, grid


def _is_code(v):
    return isinstance(v, str) and len(v.strip()) == 3 and v.strip().isalpha()


def _matrix_score(grid):
    """Rough score: number of 3-letter codes present; prefers a real matrix."""
    return sum(1 for row in grid for v in row if _is_code(v))


def find_matrix(grid):
    """Locate the header row and label column of currency codes.

    Returns dict with:
      header_row (0-based index), label_col (0-based index),
      col_of {CODE: col_index}, row_of {CODE: row_index}, currencies set.
    header_row/label_col are indices into the full grid.
    """
    nrows = len(grid)
    ncols = max((len(r) for r in grid), default=0)

    def code_at(r, c):
        if r < len(grid) and c < len(grid[r]):
            v = grid[r][c]
            if _is_code(v):
                return v.strip().upper()
        return None

    # header row = row with the most currency codes
    header_row, hr_count = None, 0
    for r in range(nrows):
        cnt = sum(1 for c in range(ncols) if code_at(r, c))
        if cnt > hr_count:
            hr_count, header_row = cnt, r
    # label col = column with the most currency codes
    label_col, lc_count = None, 0
    for c in range(ncols):
        cnt = sum(1 for r in range(nrows) if code_at(r, c))
        if cnt > lc_count:
            lc_count, label_col = cnt, c
    if header_row is None or label_col is None or hr_count < 2 or lc_count < 2:
        return None

    col_of = {}
    for c in range(ncols):
        code = code_at(header_row, c)
        if code and c != label_col:
            col_of.setdefault(code, c)
    row_of = {}
    for r in range(nrows):
        code = code_at(r, label_col)
        if code and r != header_row:
            row_of.setdefault(code, r)
    currencies = set(col_of) | set(row_of)
    return {
        "header_row": header_row,
        "label_col": label_col,
        "col_of": col_of,
        "row_of": row_of,
        "currencies": currencies,
    }


def detect_rate(text, currencies):
    """Parse (from, to, rate) from text-box text.

    Default: first code = from (row), second = to (column) -> value[from,to]=rate
    matching '1 FROM = rate TO'. If 'per' separates them ('TO per FROM') the
    direction is inverted.
    Returns dict or None.
    """
    if not text:
        return None
    upper = text.upper()
    # codes that are actually matrix currencies, in order of appearance
    found = []
    for m in CODE_RE.finditer(text):
        code = m.group(1).upper()
        if code in currencies:
            found.append((m.start(), code))
    nums = [float(m.group(0)) for m in NUM_RE.finditer(text)]
    if len(found) < 2 or not nums:
        return None
    # choose the rate: prefer a non-integer / non-1 number if present
    rate = None
    for n in nums:
        if abs(n - 1.0) > 1e-12:
            rate = n
            break
    if rate is None:
        rate = nums[-1]
    c1, c2 = found[0][1], found[1][1]
    if "PER" in re.split(r"[^A-Z]+", upper):
        # 'TO per FROM' -> c1 per c2 -> from=c2, to=c1
        frm, to = c2, c1
    else:
        frm, to = c1, c2
    return {"from": frm, "to": to, "rate": rate,
            "all_codes": [c for _, c in found], "all_numbers": nums}


def is_formula(cell):
    if cell.data_type == "f":
        return True
    v = cell.value
    return isinstance(v, str) and v.startswith("=")


def count_formulas(ws):
    return sum(1 for row in ws.iter_rows() for c in row if is_formula(c))


def replace_embedding(pptx_bytes, part_name, new_xlsx_bytes):
    """Rewrite the pptx ZIP, replacing one embedded part, preserving all others."""
    src = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == part_name:
                data = new_xlsx_bytes
            # preserve per-item compression type
            zi = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            zi.compress_type = item.compress_type
            zi.external_attr = item.external_attr
            zi.internal_attr = item.internal_attr
            zi.create_system = item.create_system
            dst.writestr(zi, data)
    src.close()
    return out_buf.getvalue()


def part_count(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return len(zf.namelist())
