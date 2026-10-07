#!/usr/bin/env python3
"""Create a strict receipt filename/date/total Excel workbook.

Input: one JSON object on stdin with optional input_dir, output_path, and
 date_order keys. Output: one JSON result object on stdout.
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
LABEL_TIERS = (
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
MONEY_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)[.,]\d{2}(?!\d)")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)")
TEXT_DATE_A_RE = re.compile(r"(?i)(\d{1,2})\s*[-./ ]\s*([A-Z]{3,9})\s*[-,./ ]\s*(\d{2,4})")
TEXT_DATE_B_RE = re.compile(r"(?i)([A-Z]{3,9})\s*[-./ ]\s*(\d{1,2})(?:ST|ND|RD|TH)?\s*,?\s*(\d{2,4})")


def upper_text(value: str, repair: bool = False) -> str:
    """Normalize spacing and apply narrowly scoped total-label OCR repairs."""
    value = value.upper()
    if repair:
        value = value.replace("T0TAL", "TOTAL").replace("GRANO", "GRAND")
    return re.sub(r"\s+", " ", value).strip()


def label_rank(line: str, repair: bool = False) -> int | None:
    text = upper_text(line, repair)
    if any(excluded in text for excluded in EXCLUSIONS):
        return None
    for rank, labels in LABEL_TIERS:
        if any(label in text for label in labels):
            return rank
    return None


def normalize_amount(token: str) -> str | None:
    """Normalize a recognized decimal token while preserving decimal-mark evidence."""
    token = token.strip()
    normalized = token.replace(",", "") if "." in token else token.replace(",", ".")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def amounts_in(line: str) -> list[str]:
    values: list[str] = []
    for match in MONEY_RE.finditer(line):
        normalized = normalize_amount(match.group(0))
        if normalized is not None:
            values.append(normalized)
    return values


def pass_total_candidates(lines: list[str], variant: str) -> list[dict[str, Any]]:
    """Return candidates from the strongest labelled total tier in one OCR pass."""
    best_rank: int | None = None
    candidates: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        rank = label_rank(line)
        if rank is None:
            continue
        values = amounts_in(line)
        source = "same_line"
        if not values and index + 1 < len(lines):
            values = amounts_in(lines[index + 1])
            source = "next_line"
        if not values:
            continue
        if best_rank is None or rank < best_rank:
            best_rank = rank
            candidates = []
        if rank == best_rank:
            candidates.append({
                "amount": values[-1], "rank": rank, "line": index,
                "source": source, "variant": variant,
            })
    return candidates


def single_amount(candidates: list[dict[str, Any]]) -> str | None:
    values = {candidate["amount"] for candidate in candidates}
    return next(iter(values)) if len(values) == 1 else None


def choose_total(passes: dict[str, list[str]]) -> tuple[str | None, dict[str, Any]]:
    """Select a payable amount without treating transformed OCR as authoritative.

    The unmodified block layout is the primary reading because it preserves normal
    receipt rows and punctuation. Sparse and image-transformed readings recover
    fields missing from that layout, and can corroborate but cannot silently
    replace a unique labelled primary reading.
    """
    all_by_variant = {
        variant: pass_total_candidates(lines, variant)
        for variant, lines in passes.items()
    }
    all_candidates = [candidate for values in all_by_variant.values() for candidate in values]
    if not all_candidates:
        return None, {"total_status": "no_eligible_decimal_total"}

    best_rank = min(candidate["rank"] for candidate in all_candidates)
    by_variant = {
        variant: [candidate for candidate in candidates if candidate["rank"] == best_rank]
        for variant, candidates in all_by_variant.items()
    }
    block = single_amount(by_variant.get("block", []))
    sparse = single_amount(by_variant.get("sparse", []))

    # A unique same-source ordinary layout reading is direct label/value evidence.
    # This deliberately prevents thresholding or sparse segmentation from changing
    # a leading digit on an otherwise well-recognized total row.
    if block is not None:
        corroborated = [name for name, candidates in by_variant.items()
                        if name != "block" and single_amount(candidates) == block]
        return block, {
            "total_status": "ok",
            "selection": "primary_block_label_association",
            "priority": best_rank,
            "corroborating_variants": corroborated,
        }

    # Sparse text is designed for label/value pairs separated into visual columns.
    if sparse is not None:
        return sparse, {
            "total_status": "ok",
            "selection": "sparse_when_primary_missing",
            "priority": best_rank,
        }

    # A recovery pass is used only when neither direct layout provided a unique
    # candidate. Require a strict vote lead, never lexical tie breaking.
    votes: Counter[str] = Counter()
    for candidates in by_variant.values():
        value = single_amount(candidates)
        if value is not None:
            votes[value] += 1
    ordered = sorted(votes, key=lambda value: (-votes[value], value))
    if ordered and (len(ordered) == 1 or votes[ordered[0]] > votes[ordered[1]]):
        return ordered[0], {
            "total_status": "ok",
            "selection": "recovery_consensus",
            "priority": best_rank,
            "supporting_passes": votes[ordered[0]],
        }
    return None, {
        "total_status": "conflicting_ocr_total_evidence",
        "priority": best_rank,
        "values": sorted(votes),
    }


def year_from_two_digits(value: int) -> int:
    return 2000 + value if value <= 69 else 1900 + value


def valid_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def date_candidates(lines: list[str], variant: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines):
        normalized = upper_text(line)
        label = 0 if ("DATE" in normalized or "ISSUED" in normalized) else 1
        for match in ISO_DATE_RE.finditer(line):
            value = valid_date(*map(int, match.groups()))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label, "line": line_number, "variant": variant})
        for match in TEXT_DATE_A_RE.finditer(normalized):
            month = MONTHS.get(match.group(2).upper())
            raw_year = int(match.group(3))
            value = valid_date(year_from_two_digits(raw_year) if raw_year < 100 else raw_year, month or 0, int(match.group(1)))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label, "line": line_number, "variant": variant})
        for match in TEXT_DATE_B_RE.finditer(normalized):
            month = MONTHS.get(match.group(1).upper())
            raw_year = int(match.group(3))
            value = valid_date(year_from_two_digits(raw_year) if raw_year < 100 else raw_year, month or 0, int(match.group(2)))
            if value:
                found.append({"kind": "fixed", "value": value, "label": label, "line": line_number, "variant": variant})
        for match in NUM_DATE_RE.finditer(line):
            first, second, raw_year = map(int, match.groups())
            year = year_from_two_digits(raw_year) if raw_year < 100 else raw_year
            found.append({
                "kind": "numeric", "dmy": valid_date(year, second, first),
                "mdy": valid_date(year, first, second), "label": label,
                "line": line_number, "variant": variant,
            })
    return found


def infer_date_order(groups: Iterable[list[dict[str, Any]]]) -> str | None:
    evidence: set[str] = set()
    for group in groups:
        for candidate in group:
            if candidate["kind"] != "numeric":
                continue
            if candidate["dmy"] and not candidate["mdy"]:
                evidence.add("day_first")
            elif candidate["mdy"] and not candidate["dmy"]:
                evidence.add("month_first")
    return next(iter(evidence)) if len(evidence) == 1 else None


def choose_date(candidates: list[dict[str, Any]], order: str | None) -> tuple[str | None, str]:
    proposals: list[tuple[str, int, int, str]] = []
    for candidate in candidates:
        if candidate["kind"] == "fixed":
            proposals.append((candidate["value"], candidate["label"], candidate["line"], candidate["variant"]))
        elif candidate["dmy"] and not candidate["mdy"]:
            proposals.append((candidate["dmy"], candidate["label"], candidate["line"], candidate["variant"]))
        elif candidate["mdy"] and not candidate["dmy"]:
            proposals.append((candidate["mdy"], candidate["label"], candidate["line"], candidate["variant"]))
        elif order == "day_first" and candidate["dmy"]:
            proposals.append((candidate["dmy"], candidate["label"], candidate["line"], candidate["variant"]))
        elif order == "month_first" and candidate["mdy"]:
            proposals.append((candidate["mdy"], candidate["label"], candidate["line"], candidate["variant"]))
    if not proposals:
        return None, "no_resolved_date"
    votes = Counter(value for value, _, _, _ in proposals)
    chosen = sorted(votes, key=lambda value: (
        -votes[value],
        min(label for proposed, label, _, _ in proposals if proposed == value),
        -max(line for proposed, _, line, _ in proposals if proposed == value),
        value,
    ))[0]
    return chosen, "ok"


def image_variants(source: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image]:
    base = ImageOps.autocontrast(ImageOps.exif_transpose(source).convert("L"))
    enlarged = ImageEnhance.Contrast(base.resize((base.width * 2, base.height * 2), Image.Resampling.LANCZOS)).enhance(1.25)
    thresholded = enlarged.point(lambda pixel: 255 if pixel > 175 else 0)
    return base, enlarged, thresholded


def ocr_lines(image: Image.Image, psm: int) -> list[str]:
    text = pytesseract.image_to_string(image, config=f"--oem 3 --psm {psm}")
    return [line.strip() for line in text.splitlines() if line.strip()]


def ocr_receipt(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as source:
            base, enlarged, thresholded = image_variants(source)
        return {
            "passes": {
                "block": ocr_lines(base, 6),
                "sparse": ocr_lines(base, 11),
                "enlarged_sparse": ocr_lines(enlarged, 11),
                "threshold_sparse": ocr_lines(thresholded, 11),
            },
            "error": None,
        }
    except Exception as exc:
        return {"passes": {}, "error": f"{type(exc).__name__}: {exc}"}


def validate_workbook(path: Path, names: list[str]) -> None:
    workbook = load_workbook(path, data_only=False)
    try:
        if workbook.sheetnames != ["results"]:
            raise RuntimeError("validation failed: workbook must contain only results")
        sheet = workbook["results"]
        if [sheet.cell(1, column).value for column in range(1, 4)] != ["filename", "date", "total_amount"]:
            raise RuntimeError("validation failed: incorrect headers")
        if sheet.max_row != len(names) + 1 or sheet.max_column != 3:
            raise RuntimeError("validation failed: unexpected table dimensions")
        written_names = [sheet.cell(row, 1).value for row in range(2, sheet.max_row + 1)]
        if written_names != names or written_names != sorted(written_names):
            raise RuntimeError("validation failed: source coverage or ordering")
        for row in range(2, sheet.max_row + 1):
            extracted_date = sheet.cell(row, 2).value
            total = sheet.cell(row, 3).value
            if extracted_date is not None:
                if not isinstance(extracted_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", extracted_date):
                    raise RuntimeError("validation failed: invalid date value")
                date.fromisoformat(extracted_date)
            if total is not None and (not isinstance(total, str) or not re.fullmatch(r"\d+\.\d{2}", total)):
                raise RuntimeError("validation failed: invalid total value")
    finally:
        workbook.close()


def main(request: dict[str, Any]) -> dict[str, Any]:
    input_dir = Path(request.get("input_dir", "/app/workspace/dataset/img"))
    output_path = Path(request.get("output_path", "/app/workspace/stat_ocr.xlsx"))
    requested_order = request.get("date_order", "auto")
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
        raise ValueError("duplicate source basenames cannot be represented by the required filename column")

    ocr_results = [ocr_receipt(path) for path in images]
    all_date_groups = [
        date_candidates(lines, variant)
        for result in ocr_results
        for variant, lines in result["passes"].items()
    ]
    inferred_order = infer_date_order(all_date_groups)
    date_order = requested_order if requested_order != "auto" else inferred_order

    records: list[dict[str, Any]] = []
    for path, result in zip(images, ocr_results):
        if result["error"]:
            records.append({"filename": path.name, "date": None, "total_amount": None,
                            "diagnostics": {"ocr_status": "error", "error": result["error"]}})
            continue
        total, diagnostics = choose_total(result["passes"])
        candidates = [
            candidate for variant, lines in result["passes"].items()
            for candidate in date_candidates(lines, variant)
        ]
        extracted_date, date_status = choose_date(candidates, date_order)
        diagnostics.update({"ocr_status": "ok", "date_status": date_status})
        records.append({"filename": path.name, "date": extracted_date, "total_amount": total,
                        "diagnostics": diagnostics})

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
        "output_path": str(output_path),
        "record_count": len(records),
        "date_order_used": date_order,
        "records": records,
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
