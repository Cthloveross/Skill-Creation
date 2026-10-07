"""Shared discovery and formula helpers for the IPF Dots workbook Skill."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from openpyxl.utils import get_column_letter


# Aliases are normalized by normalize_header() before comparison.  They express
# field semantics, not worksheet positions.
FIELD_ALIASES = {
    "name": {"name", "liftername", "athletename", "competitorname"},
    "sex": {"sex", "gender"},
    "bodyweight": {"bodyweightkg", "bodyweight", "bodyweightkgs", "bwkg"},
    "squat": {"best3squatkg", "best3squat", "bestsquatkg", "bestsquat"},
    "bench": {"best3benchkg", "best3bench", "bestbenchkg", "bestbench"},
    "deadlift": {
        "best3deadliftkg", "best3deadlift", "bestdeadliftkg", "bestdeadlift"
    },
}
REQUIRED_FIELDS = ("name", "sex", "bodyweight", "squat", "bench", "deadlift")


def normalize_header(value) -> str:
    """Return a case- and punctuation-insensitive header key."""
    if value is None:
        return ""
    return "".join(ch.lower() for ch in str(value).strip() if ch.isalnum())


@dataclass(frozen=True)
class HeaderMap:
    row: int
    fields: Dict[str, int]


def discover_headers(ws, max_scan_rows: int = 100) -> HeaderMap:
    """Find one header row holding every required semantic field.

    A duplicate match for one semantic field is deliberately rejected: choosing
    either similarly named source field would make the score non-auditable.
    """
    max_row = min(ws.max_row, max_scan_rows)
    for row in range(1, max_row + 1):
        matches: Dict[str, List[int]] = {field: [] for field in REQUIRED_FIELDS}
        for col in range(1, ws.max_column + 1):
            key = normalize_header(ws.cell(row, col).value)
            if not key:
                continue
            for field, aliases in FIELD_ALIASES.items():
                if key in aliases:
                    matches[field].append(col)
        if all(matches[field] for field in REQUIRED_FIELDS):
            duplicate = {k: v for k, v in matches.items() if len(v) != 1}
            if duplicate:
                details = ", ".join(f"{k}: {v}" for k, v in duplicate.items())
                raise ValueError(f"Ambiguous required headers in row {row}: {details}")
            return HeaderMap(row=row, fields={k: v[0] for k, v in matches.items()})
    required = ", ".join(REQUIRED_FIELDS)
    raise ValueError(
        f"Could not find one header row with required fields: {required}. "
        "Inspect the data dictionary and extend aliases only when it identifies an equivalent field."
    )


def source_record_rows(ws, header: HeaderMap) -> List[int]:
    """Return nonempty performance-record rows in original worksheet order."""
    relevant_cols = list(header.fields.values())
    rows: List[int] = []
    for row in range(header.row + 1, ws.max_row + 1):
        if any(ws.cell(row, col).value not in (None, "") for col in relevant_cols):
            rows.append(row)
    return rows


def validate_sex_labels(ws, header: HeaderMap, rows: Iterable[int]) -> None:
    """Reject category values for which this reference has no coefficient set."""
    allowed = {"m", "male", "f", "female"}
    bad: List[Tuple[int, str]] = []
    sex_col = header.fields["sex"]
    for row in rows:
        value = ws.cell(row, sex_col).value
        if value in (None, ""):
            continue
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            bad.append((row, str(value)))
    if bad:
        preview = ", ".join(f"row {row}={value!r}" for row, value in bad[:10])
        suffix = "" if len(bad) <= 10 else f" (and {len(bad) - 10} more)"
        raise ValueError(
            "Unsupported nonblank sex label(s); cannot select a published Dots "
            f"coefficient set: {preview}{suffix}"
        )


def column_ref(column: int, row: int) -> str:
    return f"{get_column_letter(column)}{row}"


def total_formula(squat_col: int, bench_col: int, deadlift_col: int, row: int) -> str:
    squat = column_ref(squat_col, row)
    bench = column_ref(bench_col, row)
    deadlift = column_ref(deadlift_col, row)
    return f'=IF(COUNT({squat}:{deadlift})=3,ROUND(SUM({squat}:{deadlift}),3),"")'


def _poly(bw: str, female: bool) -> str:
    """Build the appropriate fourth-degree denominator expression."""
    if female:
        bounded = f"MIN(MAX({bw},40),150)"
        return (
            f"-0.0000010706*{bounded}^4+0.0005158568*{bounded}^3"
            f"-0.1126655495*{bounded}^2+13.6175032*{bounded}-57.96288"
        )
    bounded = f"MIN(MAX({bw},40),210)"
    return (
        f"-0.000001093*{bounded}^4+0.0007391293*{bounded}^3"
        f"-0.1918759221*{bounded}^2+24.0900756*{bounded}-307.75076"
    )


def dots_formula(sex_col: int, bodyweight_col: int, total_col: int, row: int) -> str:
    sex = column_ref(sex_col, row)
    bw = column_ref(bodyweight_col, row)
    total = column_ref(total_col, row)
    female_check = f'OR(UPPER({sex})="F",UPPER({sex})="FEMALE")'
    valid_sex = (
        f'OR(UPPER({sex})="M",UPPER({sex})="MALE",'
        f'UPPER({sex})="F",UPPER({sex})="FEMALE")'
    )
    denominator = f"IF({female_check},{_poly(bw, True)},{_poly(bw, False)})"
    return (
        f'=IF(AND(ISNUMBER({bw}),ISNUMBER({total}),{valid_sex}),'
        f'ROUND({total}*500/({denominator}),3),"")'
    )
