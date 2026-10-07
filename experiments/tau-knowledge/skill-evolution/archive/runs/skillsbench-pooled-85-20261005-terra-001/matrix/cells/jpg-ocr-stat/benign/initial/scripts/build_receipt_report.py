#!/usr/bin/env python3
"""Create a strict receipt OCR workbook from JSON stdin.

Requires Pillow, pytesseract/Tesseract, and openpyxl, all of which are supplied
by the stated receipt-processing runtime.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from PIL import Image, ImageEnhance, ImageOps
import pytesseract

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXCLUSIONS = ("SUBTOTAL", "SUB TOTAL", "TAX", "GST", "SST", "DISCOUNT", "CHANGE", "CASH TENDERED")
# Lower score is higher priority. Longer variants are tested before generic TOTAL.
TOTAL_LABELS = (
    (0, ("GRAND TOTAL",)),
    (1, ("TOTAL RM", "TOTAL: RM")),
    (2, ("TOTAL AMOUNT",)),
    (3, ("TOTAL DUE", "AMOUNT DUE", "BALANCE DUE", "NETT TOTAL", "NET TOTAL")),
    (4, ("TOTAL", "AMOUNT")),
)
MONTHS = {
    "JAN": 1, "JANUARY": 1, "FEB": 2, "FEBRUARY": 2, "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4, "MAY": 5, "JUN": 6, "JUNE": 6, "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8, "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12, "DECEMBER": 12,
}
# Monetary tokens deliberately require either decimals, separators, or a whole
# token. A semantic total label is required before a whole token is accepted.
MONEY_RE = re.compile(r"(?<![A-Z0-9])(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d+)(?![A-Z0-9])")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)")
NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})(?!\d)")
TEXT_DATE_A_RE = re.compile(r"(?i)(\d{1,2})\s*[-./ ]\s*([A-Z]{3,9})\s*[-,./ ]\s*(\d{2,4})")
TEXT_DATE_B_RE = re.compile(r"(?i)([A-Z]{3,9})\s*[-./ ]\s*(\d{1,2})(?:ST|ND|RD|TH)?\s*[,]?\s*(\d{2,4})")


def semantic_text(text: str) -> str:
    """Normalize only a label copy, preserving raw text for numeric parsing."""
    upper = text.upper()
    # Confusions are corrected only in the field-label view, never globally.
    upper = upper.replace("T0TAL", "TOTAL").replace("GRANO", "GRAND")
    upper = re.sub(r"\s+", " ", upper)
    return upper.strip()


def normalize_money(token: str) -> str | None:
    cleaned = token.replace(",", "").replace(" ", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def amounts_on_line(line: str) -> list[str]:
    out: list[str] = []
    for token in MONEY_RE.findall(line.upper().replace("O", "0")):
        normalized = normalize_money(token)
        if normalized is not None:
            out.append(normalized)
    return out


def label_priority(line: str) -> int | None:
    cleaned = semantic_text(line)
    if any(word in cleaned for word in EXCLUSIONS):
        return None
    for priority, phrases in TOTAL_LABELS:
        if any(phrase in cleaned for phrase in phrases):
            return priority
    return None


def total_candidates(lines: list[str], variant: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        priority = label_priority(line)
        if priority is None:
            continue
        values = amounts_on_line(line)
        source = "same_line"
        if not values and i + 1 < len(lines):
            # The fallback is intentionally only one line and only after a valid label.
            values = amounts_on_line(lines[i + 1])
            source = "next_line"
        if values:
            candidates.append({"amount": values[-1], "priority": priority,
                               "line": i, "variant": variant, "source": source})
    return candidates


def choose_total(candidate_sets: list[list[dict[str, Any]]]) -> tuple[str | None, dict[str, Any]]:
    candidates = [c for one_set in candidate_sets for c in one_set]
    if not candidates:
        return None, {"total_status": "no_labelled_total"}
    best_priority = min(c["priority"] for c in candidates)
    tier = [c for c in candidates if c["priority"] == best_priority]
    votes = Counter(c["amount"] for c in tier)
    # Prefer consensus between OCR variants, then a later occurrence on a receipt.
    winning_amount = sorted(
        votes,
        key=lambda value: (-votes[value], -max(c["line"] for c in tier if c["amount"] == value), value),
    )[0]
    chosen = [c for c in tier if c["amount"] == winning_amount]
    return winning_amount, {
        "total_status": "ok",
        "total_priority": best_priority,
        "total_votes": votes[winning_amount],
        "total_sources": sorted({c["source"] for c in chosen}),
    }


def year_from_two_digits(value: int) -> int:
    # Receipt dates conventionally refer to recent dates; retain a documented,
    # deterministic pivot rather than allowing a non-ISO two-digit year through.
    return 2000 + value if value <= 69 else 1900 + value


def valid_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def date_candidates(lines: list[str], variant: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for line_index, line in enumerate(lines):
        upper = semantic_text(line)
        label_score = 0 if ("DATE" in upper or "ISSUED" in upper) else 1
        for match in ISO_DATE_RE.finditer(line):
            value = valid_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label_score,
                              "line": line_index, "variant": variant})
        for match in TEXT_DATE_A_RE.finditer(upper):
            month = MONTHS.get(match.group(2).upper())
            year = int(match.group(3))
            if month:
                value = valid_date(year_from_two_digits(year) if year < 100 else year, month, int(match.group(1)))
                if value:
                    found.append({"kind": "fixed", "value": value, "label": label_score,
                                  "line": line_index, "variant": variant})
        for match in TEXT_DATE_B_RE.finditer(upper):
            month = MONTHS.get(match.group(1).upper())
            year = int(match.group(3))
            if month:
                value = valid_date(year_from_two_digits(year) if year < 100 else year, month, int(match.group(2)))
                if value:
                    found.append({"kind": "fixed", "value": value, "label": label_score,
                                  "line": line_index, "variant": variant})
        for match in NUM_DATE_RE.finditer(line):
            first, second, year = map(int, match.groups())
            year = year_from_two_digits(year) if year < 100 else year
            dmy = valid_date(year, second, first)
            mdy = valid_date(year, first, second)
            if dmy or mdy:
                found.append({"kind": "numeric", "dmy": dmy, "mdy": mdy,
                              "label": label_score, "line": line_index, "variant": variant})
    return found


def infer_input_date_order(all_candidates: Iterable[list[dict[str, Any]]]) -> str | None:
    evidence: set[str] = set()
    for candidates in all_candidates:
        for candidate in candidates:
            if candidate["kind"] == "numeric":
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
        else:
            if candidate["dmy"] and not candidate["mdy"]:
                proposals.append((candidate["dmy"], candidate["label"], candidate["line"]))
            elif candidate["mdy"] and not candidate["dmy"]:
                proposals.append((candidate["mdy"], candidate["label"], candidate["line"]))
            elif order == "day_first" and candidate["dmy"]:
                proposals.append((candidate["dmy"], candidate["label"], candidate["line"]))
            elif order == "month_first" and candidate["mdy"]:
                proposals.append((candidate["mdy"], candidate["label"], candidate["line"]))
    if not proposals:
        return None, "no_unambiguous_date"
    vote_count = Counter(value for value, _, _ in proposals)
    value = sorted(vote_count, key=lambda item: (-vote_count[item],
                  min(label for candidate, label, _ in proposals if candidate == item),
                  -max(line for candidate, _, line in proposals if candidate == item), item))[0]
    return value, "ok"


def image_variants(image: Image.Image) -> list[Image.Image]:
    image = ImageOps.exif_transpose(image).convert("L")
    # Upscaling improves small thermal-print glyphs without applying destructive
    # transformations to every variant.
    enlarged = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    contrast = ImageOps.autocontrast(enlarged)
    threshold = contrast.point(lambda pixel: 255 if pixel > 175 else 0)
    return [enlarged, contrast, threshold]


def ocr_one(path_string: str) -> dict[str, Any]:
    path = Path(path_string)
    try:
        with Image.open(path) as source:
            variants = image_variants(source)
        result_sets: list[list[str]] = []
        for image in variants:
            # 6 suits receipt blocks; 11 recovers sparse/irregular layouts.
            for psm in (6, 11):
                text = pytesseract.image_to_string(image, config=f"--oem 3 --psm {psm}")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                result_sets.append(lines)
        return {"path": path_string, "line_sets": result_sets, "error": None}
    except Exception as exc:  # Preserve the required row for unreadable images.
        return {"path": path_string, "line_sets": [], "error": f"{type(exc).__name__}: {exc}"}


def validate_workbook(output_path: Path, expected_names: list[str]) -> None:
    workbook = load_workbook(output_path, data_only=False)
    if workbook.sheetnames != ["results"]:
        raise RuntimeError("validation failed: workbook must contain only results sheet")
    sheet = workbook["results"]
    if [sheet.cell(1, col).value for col in range(1, 4)] != ["filename", "date", "total_amount"]:
        raise RuntimeError("validation failed: incorrect header")
    if sheet.max_row != len(expected_names) + 1 or sheet.max_column != 3:
        raise RuntimeError("validation failed: unexpected workbook dimensions")
    names = [sheet.cell(row, 1).value for row in range(2, sheet.max_row + 1)]
    if names != expected_names or names != sorted(names):
        raise RuntimeError("validation failed: nondeterministic filename order")
    for row in range(2, sheet.max_row + 1):
        extracted_date, total = sheet.cell(row, 2).value, sheet.cell(row, 3).value
        if extracted_date is not None:
            if not isinstance(extracted_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", extracted_date):
                raise RuntimeError("validation failed: invalid date cell")
            if date.fromisoformat(extracted_date).isoformat() != extracted_date:
                raise RuntimeError("validation failed: non-calendar date")
        if total is not None and (not isinstance(total, str) or not re.fullmatch(r"-?\d+\.\d{2}", total)):
            raise RuntimeError("validation failed: invalid total cell")


def main(payload: dict[str, Any]) -> dict[str, Any]:
    input_dir = Path(payload.get("input_dir", "/app/workspace/dataset/img"))
    output_path = Path(payload.get("output_path", "/app/workspace/stat_ocr.xlsx"))
    requested_order = payload.get("date_order", "auto")
    if requested_order not in {"auto", "day_first", "month_first"}:
        raise ValueError("date_order must be auto, day_first, or month_first")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"input_dir is not a directory: {input_dir}")
    images = sorted((p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                    key=lambda p: (p.name, str(p.relative_to(input_dir))))
    names = [path.name for path in images]
    if len(set(names)) != len(names):
        raise ValueError("duplicate basenames found; filename output schema cannot represent them uniquely")
    workers = int(payload.get("workers", min(4, os.cpu_count() or 1)))
    workers = max(1, workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        ocr_results = list(executor.map(ocr_one, [str(path) for path in images]))

    all_date_candidates = [date_candidates(line, variant)
                           for result in ocr_results for variant, line in enumerate(result["line_sets"])]
    inferred = infer_input_date_order(all_date_candidates)
    date_order = requested_order if requested_order != "auto" else inferred
    records: list[dict[str, Any]] = []
    for path, result in zip(images, ocr_results):
        if result["error"]:
            records.append({"filename": path.name, "date": None, "total_amount": None,
                            "diagnostics": {"ocr_status": "error", "error": result["error"]}})
            continue
        candidate_sets = [total_candidates(lines, index) for index, lines in enumerate(result["line_sets"])]
        amount, total_info = choose_total(candidate_sets)
        candidates = [candidate for index, lines in enumerate(result["line_sets"])
                      for candidate in date_candidates(lines, index)]
        extracted_date, date_status = resolve_date(candidates, date_order)
        total_info.update({"ocr_status": "ok", "date_status": date_status})
        records.append({"filename": path.name, "date": extracted_date, "total_amount": amount,
                        "diagnostics": total_info})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "results"
    sheet.append(["filename", "date", "total_amount"])
    for record in records:
        sheet.append([record["filename"], record["date"], record["total_amount"]])
    workbook.save(output_path)
    validate_workbook(output_path, names)
    return {"output_path": str(output_path), "record_count": len(records),
            "date_order_used": date_order, "records": records}


if __name__ == "__main__":
    try:
        stdin = sys.stdin.read().strip()
        payload = json.loads(stdin) if stdin else {}
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
    except Exception as error:
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        sys.exit(1)
