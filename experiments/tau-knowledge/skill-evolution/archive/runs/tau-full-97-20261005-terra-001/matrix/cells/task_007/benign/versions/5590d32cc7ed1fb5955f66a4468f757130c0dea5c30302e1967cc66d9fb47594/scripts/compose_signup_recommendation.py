#!/usr/bin/env python3
"""Compose customer-facing prose from one verified, extracted sign-up offer.

The program performs no retrieval or customer action. All input facts must come from
supplied task documents.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def text(data, key, optional=False):
    value = data.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} is required text')
    return value.strip()


def number(data, key, optional=False, positive=False):
    value = data.get(key)
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise ValueError(f'{key} must be numeric')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{key} must be numeric') from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f'{key} must be {"positive" if positive else "non-negative"}')
    return result


def iso_date(data, key):
    value = text(data, key)
    try:
        date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f'{key} must be an ISO date') from exc
    return value[:10]


def display(value, dollars=False):
    rendered = format(value.quantize(Decimal('0.01')), 'f')
    whole, fraction = rendered.split('.')
    output = f'{int(whole):,}' if fraction == '00' else f'{int(whole):,}.{fraction}'
    return '$' + output if dollars else output


def singular(unit):
    return unit[:-1] if unit.lower().endswith('s') else unit


def main(data):
    if not isinstance(data, dict):
        raise ValueError('input must be a JSON object')
    as_of, start, end = iso_date(data, 'as_of'), iso_date(data, 'start'), iso_date(data, 'end')
    if not start <= as_of <= end:
        raise ValueError('selected offer is not current on as_of')
    card, unit = text(data, 'card_name'), text(data, 'reward_unit')
    reward = number(data, 'reward_amount', positive=True)
    spend = number(data, 'spend_requirement_usd', positive=True)
    period = text(data, 'qualification_period')
    new_customer = data.get('new_customer_required', False)
    good_standing = data.get('good_standing_required', False)
    if not isinstance(new_customer, bool) or not isinstance(good_standing, bool):
        raise ValueError('customer-status flags must be booleans')

    paragraphs = [
        f'**Recommendation: {card}.** Based on the documented offers supplied, it is the highest currently available eligible sign-up award for you as of {as_of}.',
        f'The promotion runs from {start} through {end}. Earn **{display(reward)} {unit}** after at least **{display(spend, dollars=True)} in eligible purchases** within {period} after account opening.',
    ]
    conditions = []
    if new_customer:
        conditions.append('You must be a new customer')
    if good_standing:
        conditions.append('the account must be open and in good standing when the bonus is awarded')
    if conditions:
        paragraphs.append('Qualification conditions: ' + '; '.join(conditions) + '.')

    rate = number(data, 'usd_per_reward_unit', optional=True, positive=True)
    if rate is not None:
        channel = text(data, 'redemption_channel')
        paragraphs.append(f'At the documented redemption rate of {display(rate, dollars=True)} per {singular(unit)}, the bonus equals {display(reward * rate, dollars=True)} when redeemed as {channel}.')
    fee = number(data, 'annual_fee_usd', optional=True)
    if fee is not None:
        paragraphs.append(f'The documented annual fee is {display(fee, dollars=True)}.')

    exclusions = data.get('exclusions', [])
    if not isinstance(exclusions, list):
        raise ValueError('exclusions must be an array')
    for item in exclusions:
        if not isinstance(item, dict):
            raise ValueError('each exclusion must be an object')
        paragraphs.append(f"{text(item, 'card_name')} is not an available recommendation for you because {text(item, 'reason')}.")
    source = text(data, 'source', optional=True)
    if source:
        paragraphs.append(f'This comparison is limited to the documented offers supplied for this request ({source}).')
    return {'ok': True, 'message': '\n\n'.join(paragraphs)}


if __name__ == '__main__':
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False, sort_keys=True))
