#!/usr/bin/env python3
"""Create a validated employee PDF (old) versus XLSX (new) JSON diff report.

stdin:  {"pdf_path": str, "xlsx_path": str, "output_path": str}
stdout: {"ok": true, "output_path": str, "deleted_count": int,
         "modified_count": int}
"""
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

ID_RE = re.compile(r"^EMP\s*(\d{1,5})$", re.IGNORECASE)
NUMERIC_FIELDS = {"salary", "years", "score"}
ID_HEADERS = {"id", "employeeid"}


class DiffInputError(ValueError):
    """A source cannot safely be interpreted as the required employee dataset."""


def clean_cell(value):
    """Return PDF/XLSX cell content with visual whitespace normalized."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.replace("\u00a0", " ").split())
    return value


def canonical_header(value):
    text = clean_cell(value)
    if not isinstance(text, str):
        text = str(text)
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def normalize_id(value):
    text = clean_cell(value)
    if not isinstance(text, str):
        text = str(text).strip()
    match = ID_RE.fullmatch(text)
    if not match:
        raise DiffInputError("invalid employee ID: {!r}; expected EMP followed by 5 digits".format(text))
    return "EMP" + match.group(1).zfill(5)


def try_normalize_id(value):
    try:
        return normalize_id(value)
    except DiffInputError:
        return None


def header_layout(row):
    """Return canonical-header -> column-index map for a possible header row."""
    result = {}
    for index, value in enumerate(row):
        key = canonical_header(value)
        if key:
            if key in result:
                return None
            result[key] = index
    if not (set(result) & ID_HEADERS) or len(result) < 2:
        return None
    return result


def id_column(layout):
    for name in ("employeeid", "id"):
        if name in layout:
            return layout[name]
    raise DiffInputError("internal error: header layout has no ID column")


def clean_row(row):
    return [clean_cell(value) for value in row]


def extract_with_settings(pdf, settings):
    """Extract records from all pages for one pdfplumber table strategy."""
    current_layout = None
    display_names = None
    records = {}
    header_count = 0

    for page in pdf.pages:
        tables = page.extract_tables() if settings is None else page.extract_tables(table_settings=settings)
        for table in tables or []:
            for raw_row in table or []:
                row = clean_row(raw_row)
                layout = header_layout(row)
                if layout is not None:
                    current_layout = layout
                    display_names = {
                        key: str(clean_cell(row[column])).strip()
                        for key, column in layout.items()
                    }
                    header_count += 1
                    continue
                if current_layout is None:
                    continue
                column = id_column(current_layout)
                if column >= len(row):
                    continue
                employee_id = try_normalize_id(row[column])
                # A table footer or continuation fragment is not a data row.
                if employee_id is None:
                    continue
                record = {}
                for field, field_column in current_layout.items():
                    record[field] = row[field_column] if field_column < len(row) else ""
                record["__id__"] = employee_id
                if employee_id in records:
                    raise DiffInputError("duplicate employee ID in PDF extraction: " + employee_id)
                records[employee_id] = record

    if not records or display_names is None:
        return None
    non_id_fields = len([name for name in display_names if name not in ID_HEADERS])
    # Prefer actual record coverage, then a richer header, then repeated-header evidence.
    quality = (len(records), non_id_fields, header_count)
    return {"records": records, "display_names": display_names, "quality": quality}


def read_pdf_records(pdf_path):
    try:
        import pdfplumber
    except ImportError as exc:
        raise DiffInputError("pdfplumber is required for PDF table extraction") from exc

    strategies = [
        None,
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        },
    ]
    candidates = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise DiffInputError("PDF contains no pages")
            for settings in strategies:
                try:
                    candidate = extract_with_settings(pdf, settings)
                except Exception as exc:
                    # Try another table strategy. A malformed table in every strategy is
                    # surfaced below rather than silently becoming an empty dataset.
                    if isinstance(exc, DiffInputError) and "duplicate employee ID" in str(exc):
                        raise
                    candidate = None
                if candidate is not None:
                    candidates.append(candidate)
    except DiffInputError:
        raise
    except Exception as exc:
        raise DiffInputError("unable to read PDF: {}".format(exc)) from exc

    if not candidates:
        raise DiffInputError(
            "no employee table could be extracted from the PDF; it may be scanned, "
            "non-tabular, or missing an ID header"
        )
    return max(candidates, key=lambda candidate: candidate["quality"])


def read_xlsx_records(xlsx_path):
    try:
        import openpyxl
    except ImportError as exc:
        raise DiffInputError("openpyxl is required for XLSX reading") from exc

    try:
        workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as exc:
        raise DiffInputError("unable to read XLSX workbook: {}".format(exc)) from exc
    try:
        worksheet = workbook.active
        header_row_number = None
        layout = None
        raw_header = None
        # Permit introductory title/blank rows without guessing arbitrary data rows.
        for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
            candidate = header_layout(clean_row(row))
            if candidate is not None:
                header_row_number, layout, raw_header = row_number, candidate, clean_row(row)
                break
            if row_number >= 30:
                break
        if layout is None:
            raise DiffInputError("could not find an employee ID header in the first 30 worksheet rows")

        display_names = {
            field: str(clean_cell(raw_header[column])).strip()
            for field, column in layout.items()
        }
        records = {}
        for row in worksheet.iter_rows(min_row=header_row_number + 1, values_only=True):
            values = clean_row(row)
            col = id_column(layout)
            raw_id = values[col] if col < len(values) else ""
            if raw_id == "":
                # Blank worksheet rows are harmless; a populated non-ID footer is ignored.
                continue
            employee_id = normalize_id(raw_id)
            if employee_id in records:
                raise DiffInputError("duplicate employee ID in XLSX: " + employee_id)
            record = {
                field: (values[column] if column < len(values) else "")
                for field, column in layout.items()
            }
            record["__id__"] = employee_id
            records[employee_id] = record
        if not records:
            raise DiffInputError("XLSX contains no employee data rows")
        return {"records": records, "display_names": display_names}
    finally:
        workbook.close()


def numeric_value(value, field, employee_id):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DiffInputError("blank numeric {} for {}".format(field, employee_id))
    if isinstance(value, bool):
        raise DiffInputError("boolean is not a numeric {} for {}".format(field, employee_id))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise DiffInputError("non-finite numeric {} for {}".format(field, employee_id))
        number = Decimal(str(value))
    else:
        text = str(clean_cell(value)).replace(",", "")
        text = re.sub(r"[$£€%]", "", text).strip()
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise DiffInputError("invalid numeric {} for {}: {!r}".format(field, employee_id, value)) from exc
    if not number.is_finite():
        raise DiffInputError("non-finite numeric {} for {}".format(field, employee_id))
    return int(number) if number == number.to_integral_value() else float(number)


def text_value(value):
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(clean_cell(value))).strip()


def normalized_value(value, field, employee_id):
    if field in NUMERIC_FIELDS:
        return numeric_value(value, field, employee_id)
    return text_value(value)


def make_report(old_data, new_data):
    old_fields = set(old_data["display_names"])
    new_fields = set(new_data["display_names"])
    old_fields -= ID_HEADERS
    new_fields -= ID_HEADERS
    if old_fields != new_fields:
        missing_in_pdf = sorted(new_fields - old_fields)
        missing_in_xlsx = sorted(old_fields - new_fields)
        raise DiffInputError(
            "source columns do not match (missing in PDF: {}; missing in XLSX: {})".format(
                missing_in_pdf, missing_in_xlsx
            )
        )

    old_records, new_records = old_data["records"], new_data["records"]
    deleted = sorted(set(old_records) - set(new_records))
    modifications = []
    # Sort canonical fields for stable output even if source column orders differ.
    for employee_id in sorted(set(old_records) & set(new_records)):
        old_record, new_record = old_records[employee_id], new_records[employee_id]
        for field in sorted(old_fields):
            old_value = normalized_value(old_record.get(field), field, employee_id)
            new_value = normalized_value(new_record.get(field), field, employee_id)
            if old_value != new_value:
                modifications.append({
                    "id": employee_id,
                    "field": new_data["display_names"][field],
                    "old_value": old_value,
                    "new_value": new_value,
                })
    modifications.sort(key=lambda item: (item["id"], item["field"]))
    return {"deleted_employees": deleted, "modified_employees": modifications}


def validate_report(report):
    if set(report) != {"deleted_employees", "modified_employees"}:
        raise DiffInputError("report has an invalid top-level schema")
    deleted = report["deleted_employees"]
    modified = report["modified_employees"]
    if not isinstance(deleted, list) or not isinstance(modified, list):
        raise DiffInputError("report lists are invalid")
    if deleted != sorted(deleted) or any(not ID_RE.fullmatch(item) for item in deleted):
        raise DiffInputError("deleted employee IDs are invalid or unsorted")
    expected_keys = {"id", "field", "old_value", "new_value"}
    ordering = []
    for item in modified:
        if set(item) != expected_keys or not ID_RE.fullmatch(item["id"]):
            raise DiffInputError("modified employee entry has an invalid schema")
        field_key = canonical_header(item["field"])
        if field_key in NUMERIC_FIELDS:
            for side in ("old_value", "new_value"):
                if isinstance(item[side], bool) or not isinstance(item[side], (int, float)):
                    raise DiffInputError("numeric modification values must be JSON numbers")
        else:
            if not isinstance(item["old_value"], str) or not isinstance(item["new_value"], str):
                raise DiffInputError("text modification values must be JSON strings")
        ordering.append((item["id"], item["field"]))
    if ordering != sorted(ordering):
        raise DiffInputError("modified employees are not sorted by ID and field")


def write_json_atomically(path, report):
    target = Path(path)
    if not target.parent.exists():
        raise DiffInputError("output directory does not exist: " + str(target.parent))
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".diff_report_", suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise DiffInputError("stdin must be a JSON object")
        required = ("pdf_path", "xlsx_path", "output_path")
        if any(not isinstance(request.get(key), str) or not request[key] for key in required):
            raise DiffInputError("pdf_path, xlsx_path, and output_path must be nonempty strings")
        old_data = read_pdf_records(request["pdf_path"])
        new_data = read_xlsx_records(request["xlsx_path"])
        report = make_report(old_data, new_data)
        validate_report(report)
        write_json_atomically(request["output_path"], report)
        print(json.dumps({
            "ok": True,
            "output_path": request["output_path"],
            "deleted_count": len(report["deleted_employees"]),
            "modified_count": len(report["modified_employees"]),
        }))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
