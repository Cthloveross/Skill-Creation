"""Shared helpers for the protein-expression workbook Skill."""
from openpyxl.utils import get_column_letter, column_index_from_string


def sheet_ref(name):
    """Return a formula-safe sheet reference (quote if it has spaces/odd chars)."""
    if any(c in name for c in " -+'"):
        return "'" + name.replace("'", "''") + "'"
    return name


def col_to_idx(c):
    if isinstance(c, int):
        return c
    return column_index_from_string(str(c))


def idx_to_col(i):
    return get_column_letter(i)


def norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip()
    return v
