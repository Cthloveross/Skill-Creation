#!/usr/bin/env python3
"""Create a source-grounded, ready-to-send documented-card recommendation."""
from __future__ import annotations

import json
import sys
from typing import Any

from evaluate_documented_cards import extract_cards
from match_cards import evaluate_payload, number


def pct(value: Any) -> str:
    parsed = number(value)
    if parsed is None:
        return 'unknown'
    text = format(parsed.normalize(), 'f')
    return (text if '.' in text else text + '.0') + '%'


def score(value: Any) -> str:
    parsed = number(value)
    return format(parsed, 'f').split('.')[0] if parsed is not None else 'unknown'


def confirmed_message(cards: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ', '.join(str(card.get('name', 'Documented card')) for card in cards)
    verb = 'is' if len(cards) == 1 else 'are'
    paragraphs = [f'Based on the supplied product documents, {names} {verb} a confirmed match for the published criteria you gave.']
    supplied_score = number(customer.get('credit_score'))

    for card in cards:
        pieces: list[str] = []
        threshold = number(card.get('minimum_credit_score'))
        if threshold == 0:
            if supplied_score is None:
                pieces.append('there is no credit-score requirement (the published minimum is 0)')
            else:
                pieces.append(f'there is no credit-score requirement (the published minimum is 0), so your stated {score(supplied_score)} score does not exclude you from applying')
        elif threshold is not None and supplied_score is not None:
            pieces.append(f'the documented minimum credit score is {score(threshold)}, which your stated score meets')
        if requirements.get('max_foreign_transaction_fee_percent') is not None:
            pieces.append(f'the foreign transaction fee is {pct(card.get("foreign_transaction_fee_percent"))}, within your {pct(requirements.get("max_foreign_transaction_fee_percent"))} maximum')
        if requirements.get('max_minimum_payment_percent') is not None:
            pieces.append(f'the minimum monthly payment is {pct(card.get("minimum_payment_percent"))} of the outstanding balance, within your {pct(requirements.get("max_minimum_payment_percent"))} maximum')
        if requirements.get('requires_virtual_card_management') is True:
            pieces.append('virtual-card management is available, which can help organize spending')
        paragraphs.append(f'{card.get("name", "This card")}: ' + '; '.join(pieces) + '.')

    if customer.get('income') is not None:
        paragraphs.append('No applicable documented income threshold was used in this comparison.')
    paragraphs.append('This meets published criteria only and does not guarantee approval.')
    return '\n\n'.join(paragraphs)


def nonmatch_message(result: dict[str, Any]) -> tuple[str, str]:
    if result['needs_review']:
        details = [
            '%s: %s' % (card.get('name', 'A card'), '; '.join(card['evaluation']['unknown']))
            for card in result['needs_review']
        ]
        return 'needs_review', 'I could not confirm a match because relevant documented terms remain unknown: ' + ' | '.join(details) + '.'
    if result['not_qualified']:
        details = [
            '%s: %s' % (card.get('name', 'A card'), '; '.join(card['evaluation']['failed']))
            for card in result['not_qualified']
        ]
        return 'no_confirmed_match', 'I found no confirmed match under the published criteria. Documented blockers: ' + ' | '.join(details) + '. This is not an approval decision.'
    return 'no_confirmed_match', 'No product documents were supplied for comparison. This is not an approval decision.'


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get('documents'), list):
            raise ValueError('documents must be an array of current-task product documents')
        customer, requirements = payload.get('customer', {}), payload.get('requirements', {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError('customer and requirements must be objects')
        cards = extract_cards(payload['documents'])
        result = evaluate_payload({'customer': customer, 'requirements': requirements, 'cards': cards})
        if result['qualified']:
            status, message = 'confirmed_match', confirmed_message(result['qualified'], customer, requirements)
        else:
            status, message = nonmatch_message(result)
        output = {'status': status, 'message': message, 'extracted_cards': cards, **result}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {'status': 'invalid_input', 'error': 'invalid_input', 'message': str(exc)}
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
