#!/usr/bin/env python3
"""Build a strict filename/date/total Excel report from scanned receipt images.

Reads one JSON object from stdin and writes one JSON run summary to stdout.
Requires Pillow, pytesseract/Tesseract, and openpyxl supplied by the runtime.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import pytesseract
from openpyxl import Workbook, load_workbook
from PIL import Image, ImageEnhance, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXCLUSIONS = (
    "SUBTOTAL", "SUB TOTAL", "TAX", "GST", "SST", "DISCOUNT", "CHANGE", "CASH TENDERED",
)
TOTAL_LABELS = (
    (0, ("GRAND TOTAL",)),
    (1, ("TOTAL RM", "TOTAL: RM")),
    (2, ("TOTAL AMOUNT",)),
    (3, ("TOTAL DUE", "AMOUNT DUE", "BALANCE DUE", "NETT TOTAL", "NET TOTAL", "TOTAL", "AMOUNT")),
)
MONTHS = {
    "JAN": 1, "JANUARY": 1, "FEB": 2, "FEBRUARY": 2, "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4, "MAY": 5, "JUN": 6, "JUNE": 6, "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8, "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12, "DECEMBER": 12,
}
MONEY_RE = re.compile(r"(?<![A-Z0-9])(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d+)(?![A-Z0-9])")
EXACT_MONEY_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)[.,]\d{2}(?!\d)")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)")
NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})(?!\d)")
TEXT_DATE_A_RE = re.compile(r"(?i)(\d{1,2})\s*[-./ ]\s*([A-Z]{3,9})\s*[-,./ ]\s*(\d{2,4})")
TEXT_DATE_B_RE = re.compile(r"(?i)([A-Z]{3,9})\s*[-./ ]\s*(\d{1,2})(?:ST|ND|RD|TH)?\s*[,]?\s*(\d{2,4})")


def normalized_text(text: str, repair: bool = False) -> str:
    value = text.upper()
    if repair:
        # Repairs are local to recovery label recognition, never global OCR rewriting.
        value = value.replace("T0TAL", "TOTAL").replace("GRANO", "GRAND")
    return re.sub(r"\s+", " ", value).strip()


def label_priority(line: str, repair: bool = False) -> int | None:
    upper = normalized_text(line, repair)
    if any(word in upper for word in EXCLUSIONS):
        return None
    for priority, phrases in TOTAL_LABELS:
        if any(phrase in upper for phrase in phrases):
            return priority
    return None


def normalize_money(token: str) -> str | None:
    cleaned = token.replace(",", "").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def normalize_exact_money(token: str) -> str | None:
    cleaned = token.replace(",", "") if "." in token else token.replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return format(value, ".2f") if value >= 0 else None


def amounts_on_line(line: str) -> list[str]:
    """Recovery parser; character repair is limited to potential numeric tokens."""
    values: list[str] = []
    for token in MONEY_RE.findall(line.upper().replace("O", "0")):
        value = normalize_money(token)
        if value is not None:
            values.append(value)
    return values


def exact_amounts_on_line(line: str) -> list[str]:
    values: list[str] = []
    for match in EXACT_MONEY_RE.finditer(line):
        value = normalize_exact_money(match.group(0))
        if value is not None:
            values.append(value)
    return values


def explicit_baseline_observations(line_sets: list[list[str]]) -> tuple[int | None, Counter[str]]:
    """Get literal decimal amounts at the best eligible explicit label priority."""
    best: int | None = None
    observations: Counter[str] = Counter()
    for lines in line_sets:
        local: list[tuple[int, list[str]]] = []
        for index, line in enumerate(lines):
            rank = label_priority(line, repair=False)
            if rank is None:
                continue
            amounts = exact_amounts_on_line(line)
            if not amounts and index + 1 < len(lines):
                amounts = exact_amounts_on_line(lines[index + 1])
            if amounts:
                local.append((rank, amounts[-1:]))
        for rank, amounts in local:
            if best is None or rank < best:
                best, observations = rank, Counter(amounts)
            elif rank == best:
                observations.update(amounts)
    return best, observations


def recovery_candidates(lines: list[str], variant: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        rank = label_priority(line, repair=True)
        if rank is None:
            continue
        amounts = amounts_on_line(line)
        source = "same_line"
        if not amounts and index + 1 < len(lines):
            amounts = amounts_on_line(lines[index + 1])
            source = "next_line"
        if amounts:
            candidates.append({
                "amount": amounts[-1], "priority": rank, "line": index,
                "variant": variant, "source": source,
            })
    return candidates


def choose_total(canonical_sets: list[list[str]], all_sets: list[list[str]]) -> tuple[str | None, dict[str, Any]]:
    """Prefer an unambiguous canonical reading before transformed recovery OCR.

    Image transforms can sharpen a faint label but can also alter a terminal digit.
    Therefore transformed readings are used only when canonical OCR has no single
    explicit eligible amount, rather than outvoting a clear canonical reading.
    """
    rank, observations = explicit_baseline_observations(canonical_sets)
    if len(observations) == 1:
        value = next(iter(observations))
        return value, {
            "total_status": "ok", "selection": "canonical_explicit",
            "total_priority": rank, "canonical_evidence": [value],
        }

    candidates = [
        candidate
        for variant, lines in enumerate(all_sets)
        for candidate in recovery_candidates(lines, variant)
    ]
    if not candidates:
        return None, {
            "total_status": "no_labelled_total", "canonical_evidence": sorted(observations),
        }
    best_rank = min(candidate["priority"] for candidate in candidates)
    tier = [candidate for candidate in candidates if candidate["priority"] == best_rank]
    votes = Counter(candidate["amount"] for candidate in tier)
    winner = sorted(
        votes,
        key=lambda value: (-votes[value], -max(c["line"] for c in tier if c["amount"] == value), value),
    )[0]
    return winner, {
        "total_status": "ok", "selection": "recovery_ensemble_after_canonical_conflict" if observations else "recovery_ensemble",
        "total_priority": best_rank, "total_votes": votes[winner],
        "canonical_evidence": sorted(observations),
    }


def year_from_two_digits(value: int) -> int:
    return 2000 + value if value <= 69 else 1900 + value


def valid_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def date_candidates(lines: list[str], variant: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines):
        label_rank = 0 if ("DATE" in normalized_text(line) or "ISSUED" in normalized_text(line)) else 1
        for match in ISO_DATE_RE.finditer(line):
            value = valid_date(*map(int, match.groups()))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label_rank, "line": line_number, "variant": variant})
        text = normalized_text(line)
        for match in TEXT_DATE_A_RE.finditer(text):
            month = MONTHS.get(match.group(2).upper())
            year = int(match.group(3))
            value = valid_date(year_from_two_digits(year) if year < 100 else year, month or 0, int(match.group(1)))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label_rank, "line": line_number, "variant": variant})
        for match in TEXT_DATE_B_RE.finditer(text):
            month = MONTHS.get(match.group(1).upper())
            year = int(match.group(3))
            value = valid_date(year_from_two_digits(year) if year < 100 else year, month or 0, int(match.group(2)))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label_rank, "line": line_number, "variant": variant})
        for match in NUM_DATE_RE.finditer(line):
            first, second, year = map(int, match.groups())
            year = year_from_two_digits(year) if year < 100 else year
            found.append({
                "kind": "numeric", "dmy": valid_date(year, second, first),
                "mdy": valid_date(year, first, second), "label": label_rank,
                "line": line_number, "variant": variant,
            })
    return found


def infer_input_date_order(groups: Iterable[list[dict[str, Any]]]) -> str | None:
    evidence: set[str] = set()
    for candidates in groups:
        for candidate in candidates:
            if candidate["kind"] != "numeric":
                continue
            if candidate["dmy"] and not candidate["mdy"]:
                evidence.add("day_first")
            elif candidate["mdy"] and not candidate["dmy"]:
                evidence.add("month_first")
    return next(iter(evidence)) if len(evidence) == 1 else None


def resolve_date(candidates: list[dict[str, Any]], order: str | None) -> tuple[str | None, str]:
    proposals: list[tuple[str, int, int]] = []
    for candidate in candidates:
        if candidate["kind"] == "fixed":
            proposals.append((candidate["value"], candidate["label"], candidate["line"]))
        elif candidate["dmy"] and not candidate["mdy"]:
            proposals.append((candidate["dmy"], candidate["label"], candidate["line"]))
        elif candidate["mdy"] and not candidate["dmy"]:
            proposals.append((candidate["mdy"], candidate["label"], candidate["line"]))
        elif order == "day_first" and candidate["dmy"]:
            proposals.append((candidate["dmy"], candidate["label"], candidate["line"]))
        elif order == "month_first" and candidate["mdy"]:
            proposals.append((candidate["mdy"], candidate["label"], candidate["line"]))
    if not proposals:
        return None, "no_unambiguous_date"
    counts = Counter(value for value, _, _ in proposals)
    selected = sorted(
        counts,
        key=lambda value: (
            -counts[value],
            min(label for proposed, label, _ in proposals if proposed == value),
            -max(line for proposed, _, line in proposals if proposed == value),
            value,
        ),
    )[0]
    return selected, "ok"


def image_variants(source: Image.Image) -> tuple[Image.Image, list[Image.Image]]:
    """Create one canonical image and targeted transformed recovery variants."""
    upright = ImageOps.exif_transpose(source).convert("L")
    canonical = ImageOps.autocontrast(upright)
    enlarged = canonical.resize((canonical.width * 2, canonical.height * 2), Image.Resampling.LANCZOS)
    contrast = ImageEnhance.Contrast(enlarged).enhance(1.3)
    threshold = contrast.point(lambda pixel: 255 if pixel > 175 else 0)
    return canonical, [enlarged, threshold]


def ocr_lines(image: Image.Image, psm: int) -> list[str]:
    text = pytesseract.image_to_string(image, config=f"--oem 3 --psm {psm}")
    return [line.strip() for line in text.splitlines() if line.strip()]


def ocr_receipt(path: Path) -> dict[str, Any]:
    """OCR canonical first and invoke slower transforms only when necessary."""
    try:
        with Image.open(path) as source:
            canonical_image, recovery_images = image_variants(source)
        canonical = ocr_lines(canonical_image, 6)
        _, canonical_totals = explicit_baseline_observations([canonical])
        canonical_dates = date_candidates(canonical, 0)
        needs_total_recovery = len(canonical_totals) != 1
        needs_date_recovery = not canonical_dates
        recovery_sets: list[list[str]] = []
        if needs_total_recovery or needs_date_recovery:
            for image in recovery_images:
                recovery_sets.append(ocr_lines(image, 6))
            # Sparse layout helps when a total label and its value are isolated.
            recovery_sets.append(ocr_lines(recovery_images[-1], 11))
        return {
            "canonical_sets": [canonical], "line_sets": [canonical] + recovery_sets,
            "error": None,
        }
    except Exception as exc:
        return {"canonical_sets": [], "line_sets": [], "error": f"{type(exc).__name__}: {exc}"}


def validate_workbook(path: Path, names: list[str]) -> None:
    workbook = load_workbook(path, data_only=False)
    try:
        if workbook.sheetnames != ["results"]:
            raise RuntimeError("validation failed: workbook must contain only the results sheet")
        sheet = workbook["results"]
        if [sheet.cell(1, column).value for column in range(1, 4)] != ["filename", "date", "total_amount"]:
            raise RuntimeError("validation failed: incorrect headers")
        if sheet.max_row != len(names) + 1 or sheet.max_column != 3:
            raise RuntimeError("validation failed: unexpected worksheet dimensions")
        actual_names = [sheet.cell(row, 1).value for row in range(2, sheet.max_row + 1)]
        if actual_names != names or actual_names != sorted(actual_names):
            raise RuntimeError("validation failed: filenames are not in lexical order")
        for row in range(2, sheet.max_row + 1):
            extracted_date, amount = sheet.cell(row, 2).value, sheet.cell(row, 3).value
            if extracted_date is not None:
                if not isinstance(extracted_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", extracted_date):
                    raise RuntimeError("validation failed: invalid date cell")
                date.fromisoformat(extracted_date)
            if amount is not None and (not isinstance(amount, str) or not re.fullmatch(r"\d+\.\d{2}", amount)):
                raise RuntimeError("validation failed: invalid total cell")
    finally:
        workbook.close()


def main(payload: dict[str, Any]) -> dict[str, Any]:
    input_dir = Path(payload.get("input_dir", "/app/workspace/dataset/img"))
    output_path = Path(payload.get("output_path", "/app/workspace/stat_ocr.xlsx"))
    requested_order = payload.get("date_order", "auto")
    if requested_order not in {"auto", "day_first", "month_first"}:
        raise ValueError("date_order must be auto, day_first, or month_first")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"input_dir is not a directory: {input_dir}")

    images = sorted(
        (path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: (path.name, str(path.relative_to(input_dir))),
    )
    names = [path.name for path in images]
    if len(names) != len(set(names)):
        raise ValueError("duplicate basenames cannot be represented by the required filename schema")

    # Serial OCR avoids resource-dependent variation and limits each clear receipt
    # to one Tesseract invocation.
    ocr_results = [ocr_receipt(path) for path in images]
    date_groups = [
        date_candidates(lines, variant)
        for result in ocr_results
        for variant, lines in enumerate(result["line_sets"])
    ]
    inferred_order = infer_input_date_order(date_groups)
    date_order = requested_order if requested_order != "auto" else inferred_order

    records: list[dict[str, Any]] = []
    for path, result in zip(images, ocr_results):
        if result["error"]:
            records.append({
                "filename": path.name, "date": None, "total_amount": None,
                "diagnostics": {"ocr_status": "error", "error": result["error"]},
            })
            continue
        total, diagnostic = choose_total(result["canonical_sets"], result["line_sets"])
        candidates = [
            candidate
            for variant, lines in enumerate(result["line_sets"])
            for candidate in date_candidates(lines, variant)
        ]
        extracted_date, date_status = resolve_date(candidates, date_order)
        diagnostic.update({"ocr_status": "ok", "date_status": date_status})
        records.append({
            "filename": path.name, "date": extracted_date, "total_amount": total,
            "diagnostics": diagnostic,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "results"
    sheet.append(["filename", "date", "total_amount"])
    for record in records:
        sheet.append([record["filename"], record["date"], record["total_amount"]])
    workbook.save(output_path)
    validate_workbook(output_path, names)
    return {
        "output_path": str(output_path), "record_count": len(records),
        "date_order_used": date_order, "records": records,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read().strip()
        request = json.loads(raw) if raw else {}
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(request), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(1)
