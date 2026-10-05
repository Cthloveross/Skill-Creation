#!/usr/bin/env python3
"""Classify documented sign-up awards supplied as JSON on stdin.

This program does not retrieve documents, inspect accounts, or take customer action.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def decimal(value, field, *, positive=False, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f"{field} must be {'positive' if positive else 'non-negative'}")
    return result


def money(value):
    return format(value.quantize(Decimal('0.01')), 'f')


def main(data):
    if not isinstance(data, dict):
        raise ValueError('input must be a JSON object')
    as_of = parse_date(data.get('as_of'), 'as_of')
    audience_wanted = data.get('desired_audience')
    if audience_wanted not in {'personal', 'business', 'any'}:
        raise ValueError('desired_audience must be personal, business, or any')
    is_new = data.get('is_new_customer')
    if is_new not in {True, False, None}:
        raise ValueError('is_new_customer must be true, false, or null')

    invitation_known = 'invited_offer_ids' in data
    invited = data.get('invited_offer_ids', [])
    if not isinstance(invited, list) or not all(isinstance(x, str) for x in invited):
        raise ValueError('invited_offer_ids must be an array of strings')
    invited = set(invited)
    offers = data.get('offers')
    if not isinstance(offers, list):
        raise ValueError('offers must be an array')

    groups = {key: [] for key in ('eligible', 'conditional', 'excluded', 'unverified')}
    seen = set()
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError('each offer must be an object')
        oid = offer.get('id')
        name = offer.get('card_name')
        audience = offer.get('audience')
        if not isinstance(oid, str) or not oid or oid in seen:
            raise ValueError('offer ids must be nonempty and unique')
        seen.add(oid)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'offer {oid}: card_name is required')
        if audience not in {'personal', 'business', 'any'}:
            raise ValueError(f'offer {oid}: invalid audience')
        amount = decimal(offer.get('reward_amount'), f'offer {oid} reward_amount', positive=True)
        unit = offer.get('reward_unit')
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f'offer {oid}: reward_unit is required')
        rate = decimal(offer.get('usd_per_reward_unit'), f'offer {oid} usd_per_reward_unit', positive=True, nullable=True)
        conditions = offer.get('conditions', [])
        if not isinstance(conditions, list) or not all(isinstance(x, str) for x in conditions):
            raise ValueError(f'offer {oid}: conditions must be an array of strings')

        reasons, unresolved = [], []
        if audience_wanted != 'any' and audience not in {'any', audience_wanted}:
            reasons.append('audience does not match')
        start_raw, end_raw = offer.get('start'), offer.get('end')
        if start_raw is None or end_raw is None:
            unresolved.append('promotion window is not fully documented')
        else:
            start = parse_date(start_raw, f'offer {oid} start')
            end = parse_date(end_raw, f'offer {oid} end')
            if end < start:
                raise ValueError(f'offer {oid}: end precedes start')
            if as_of < start:
                reasons.append('offer has not started')
            elif as_of > end:
                reasons.append('offer has ended')
        if offer.get('requires_invitation', False):
            if invitation_known and oid not in invited:
                reasons.append('required invitation is not held')
            elif not invitation_known:
                unresolved.append('invitation status is unknown')
        if offer.get('new_customer_required', False):
            if is_new is False:
                reasons.append('requires a new customer')
            elif is_new is None:
                unresolved.append('new-customer status is unknown')

        cash_value = amount * rate if rate is not None else None
        record = {
            'offer_id': oid, 'card_name': name, 'reward_amount': str(amount),
            'reward_unit': unit, 'usd_per_reward_unit': str(rate) if rate is not None else None,
            'cash_equivalent_usd': money(cash_value) if cash_value is not None else None,
            'start': start_raw, 'end': end_raw,
            'spend_requirement_usd': offer.get('spend_requirement_usd'),
            'qualification_months': offer.get('qualification_months'),
            'annual_fee_usd': offer.get('annual_fee_usd'),
            'conditions': conditions, 'reasons': reasons,
            'unresolved_conditions': unresolved,
        }
        if reasons:
            groups['excluded'].append(record)
        elif cash_value is None or start_raw is None or end_raw is None:
            if cash_value is None:
                record['unresolved_conditions'].append('no documented USD conversion')
            groups['unverified'].append(record)
        elif unresolved:
            groups['conditional'].append(record)
        else:
            groups['eligible'].append(record)

    for group in ('eligible', 'conditional'):
        groups[group].sort(key=lambda item: (-Decimal(item['cash_equivalent_usd']), item['offer_id']))
    selected_pool = 'eligible' if groups['eligible'] else 'conditional'
    recommendation = groups[selected_pool][0] if groups[selected_pool] else None
    return {
        'ok': True, 'as_of_date': as_of.isoformat(), **groups,
        'recommendation': recommendation,
        'validation': {
            'recommendation_is_current': recommendation is not None,
            'selected_pool': selected_pool if recommendation else None,
            'selection_is_maximum_in_selected_pool': recommendation is not None,
            'offer_count_processed': len(offers),
        },
    }


if __name__ == '__main__':
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False, sort_keys=True))
