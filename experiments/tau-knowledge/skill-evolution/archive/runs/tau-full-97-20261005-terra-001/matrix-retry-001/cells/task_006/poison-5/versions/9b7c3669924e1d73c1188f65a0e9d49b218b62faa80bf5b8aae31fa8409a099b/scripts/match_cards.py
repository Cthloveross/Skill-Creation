#!/usr/bin/env python3
"""Conservatively evaluate structured documented-card facts.

Read one JSON object from stdin with ``customer``, ``requirements``, and ``cards``.
Write JSON to stdout. This program performs no banking action.
"""
from __future__ import annotations
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace('$', '').replace(',', '').replace('%', ''))
    except (InvalidOperation, AttributeError):
        return None


def evaluate_card(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    result = dict(card)
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card.get('ambiguous_fields', []))

    wanted_type = requirements.get('product_type')
    if wanted_type is not None:
        actual = card.get('product_type')
        if 'product_type' in ambiguous or actual is None:
            unknown.append('product type is not documented unambiguously')
        elif str(actual).casefold() != str(wanted_type).casefold():
            failed.append(f'product type is {actual}, not requested {wanted_type}')
        else:
            passed.append('requested product type')

    supplied_score = number(customer.get('credit_score'))
    if supplied_score is not None:
        threshold = number(card.get('minimum_credit_score'))
        if 'minimum_credit_score' in ambiguous or threshold is None:
            unknown.append('minimum credit-score requirement is not documented')
        elif supplied_score < threshold:
            failed.append(f'credit score {supplied_score} is below documented minimum {threshold}')
        elif threshold == 0:
            passed.append('no credit-score requirement (documented minimum 0)')
        else:
            passed.append(f'credit score meets documented minimum {threshold}')

    for req_key, card_key, label in (
        ('max_foreign_transaction_fee_percent', 'foreign_transaction_fee_percent', 'foreign transaction fee'),
        ('max_minimum_payment_percent', 'minimum_payment_percent', 'minimum payment percentage'),
    ):
        ceiling = number(requirements.get(req_key))
        if ceiling is None:
            continue
        actual = number(card.get(card_key))
        if card_key in ambiguous or actual is None:
            unknown.append(f'{label} is not documented')
        elif actual > ceiling:
            failed.append(f'{label} {actual}% exceeds requested maximum {ceiling}%')
        else:
            passed.append(f'{label} {actual}% is within requested maximum {ceiling}%')

    if requirements.get('requires_virtual_card_management') is True:
        actual = card.get('virtual_card_management')
        if 'virtual_card_management' in ambiguous or actual is None:
            unknown.append('virtual-card-management availability is not documented')
        elif actual is not True:
            failed.append('virtual-card management is not available')
        else:
            passed.append('virtual-card management is available')

    memberships = card.get('required_memberships', [])
    if not isinstance(memberships, list):
        unknown.append('membership requirement format is invalid')
    elif memberships:
        held = customer.get('memberships')
        if not isinstance(held, list):
            unknown.append('customer memberships were not supplied')
        else:
            held_names = {str(item).casefold() for item in held}
            missing = [str(item) for item in memberships if str(item).casefold() not in held_names]
            if missing:
                failed.append('missing required membership(s): ' + ', '.join(missing))
            else:
                passed.append('required membership(s) held')

    result['evaluation'] = {'passed': passed, 'failed': failed, 'unknown': unknown}
    result['status'] = 'not_qualified' if failed else 'needs_review' if unknown else 'qualified'
    return result


def evaluate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    customer, requirements, cards = payload.get('customer', {}), payload.get('requirements', {}), payload.get('cards', [])
    if not isinstance(customer, dict) or not isinstance(requirements, dict) or not isinstance(cards, list):
        raise ValueError('customer and requirements must be objects and cards must be an array')
    if any(not isinstance(card, dict) for card in cards):
        raise ValueError('each cards entry must be an object')
    evaluated = [evaluate_card(card, customer, requirements) for card in cards]
    return {
        'qualified': [item for item in evaluated if item['status'] == 'qualified'],
        'not_qualified': [item for item in evaluated if item['status'] == 'not_qualified'],
        'needs_review': [item for item in evaluated if item['status'] == 'needs_review'],
        'notice': 'A qualified result confirms supplied documented criteria only; it is not an approval decision.',
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError('top-level JSON value must be an object')
        output = evaluate_payload(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        output = {'error': 'invalid_input', 'message': str(exc)}
    print(json.dumps(output, ensure_ascii=False, default=str))

if __name__ == '__main__':
    main()
