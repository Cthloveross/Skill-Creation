#!/usr/bin/env python3
"""Extract source-backed card facts from supplied documents and evaluate them."""
from __future__ import annotations
import json
import re
import sys
from typing import Any
from match_cards import evaluate_payload


def product_name(title: str) -> str:
    return title.split(':', 1)[0].strip()


def first(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I | re.S)
        if found:
            return found.group(1)
    return None


def val(text: str) -> float:
    return float(text.replace('$', '').replace(',', ''))


def fact(card: dict[str, Any], key: str, value: Any, source: str) -> None:
    card.setdefault('field_sources', {}).setdefault(key, []).append(source)
    if key in card.get('ambiguous_fields', []):
        return
    if key not in card:
        card[key] = value
    elif card[key] != value:
        card.pop(key, None)
        card.setdefault('ambiguous_fields', []).append(key)


def extract_cards(documents: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, text = document.get('title'), document.get('content')
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            continue
        name = product_name(title)
        card = grouped.setdefault(name, {'name': name, 'field_sources': {}})
        source = str(document.get('document_id') or title)
        low_title = title.casefold()
        if 'business' in low_title:
            fact(card, 'product_type', 'business', source)
        elif 'card' in low_title:
            fact(card, 'product_type', 'personal', source)

        score = first(text, [
            r'minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9][0-9,]*)',
            r'minimum\s+(?:personal\s+)?(?:fico\s+)?(?:credit\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)',
            r'applications?\s+should\s+meet\s+at\s+least\s*\$?([0-9][0-9,]*)',
        ])
        if score is not None:
            fact(card, 'minimum_credit_score', val(score), source)
        foreign = first(text, [r'foreign\s+transaction\s+fee(?:\s+(?:on|for)[^:\n]*)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%'])
        if foreign is not None:
            fact(card, 'foreign_transaction_fee_percent', val(foreign), source)
        payment = first(text, [
            r'minimum\s+(?:monthly\s+)?payment\s+is\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%',
            r'minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%',
        ])
        if payment is not None:
            fact(card, 'minimum_payment_percent', val(payment), source)
        virtual = first(text, [
            r'virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)',
            r'virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)',
        ])
        if virtual is not None:
            fact(card, 'virtual_card_management', virtual.casefold() == 'yes', source)
        membership = first(text, [r'([A-Za-z0-9+ -]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes'])
        if membership:
            required = card.setdefault('required_memberships', [])
            item = membership.strip()
            if item not in required:
                required.append(item)
                card.setdefault('field_sources', {}).setdefault('required_memberships', []).append(source)
    for card in grouped.values():
        if card.get('ambiguous_fields'):
            card['ambiguous_fields'] = sorted(set(card['ambiguous_fields']))
    return list(grouped.values())


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get('documents'), list):
            raise ValueError('documents must be an array of current-task product documents')
        if not isinstance(payload.get('customer', {}), dict) or not isinstance(payload.get('requirements', {}), dict):
            raise ValueError('customer and requirements must be objects')
        cards = extract_cards(payload['documents'])
        output = {'extracted_cards': cards, **evaluate_payload({**payload, 'cards': cards})}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {'error': 'invalid_input', 'message': str(exc)}
    print(json.dumps(output, ensure_ascii=False, default=str))

if __name__ == '__main__':
    main()
