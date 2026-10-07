#!/usr/bin/env python3
"""Return documented card terms for a named card.

Input: {"card": string, "fields": string|[string] (optional)}
Output: {"card": string, "terms": object, "source_document_ids": object,
         "missing_fields": [string]}.
"""
import json
import sys
from pathlib import Path

SUPPORTED_FIELDS = {
    "annual_fee_usd",
    "purchase_apr_percent",
    "foreign_transaction_fee_percent",
    "late_payment_fee_usd"
}


def load_terms():
    path = Path(__file__).resolve().parent.parent / "references" / "card_terms.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def requested_fields(value):
    if value is None:
        return None
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = value
    else:
        raise ValueError("fields must be a string or an array of strings")
    unknown = [item for item in values if item not in SUPPORTED_FIELDS]
    if unknown:
        raise ValueError("unsupported fields: " + ", ".join(unknown))
    return values


def main(payload):
    card = payload.get("card")
    if not isinstance(card, str) or not card.strip():
        raise ValueError("card must be a nonempty string")
    fields = requested_fields(payload.get("fields"))
    record = next(
        (item for item in load_terms()["cards"] if item["card"].casefold() == card.strip().casefold()),
        None
    )
    if record is None:
        return {"card": card.strip(), "terms": {}, "source_document_ids": {}, "missing_fields": fields or []}

    selected = fields if fields is not None else sorted(record.get("terms", {}).keys())
    terms = {}
    sources = {}
    missing = []
    for field in selected:
        if field in record.get("terms", {}):
            terms[field] = record["terms"][field]
            sources[field] = record.get("source_document_ids", {}).get(field, [])
        else:
            missing.append(field)
    return {"card": record["card"], "terms": terms, "source_document_ids": sources, "missing_fields": missing}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(request), ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
