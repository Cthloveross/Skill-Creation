#!/usr/bin/env python3
"""Deterministic PIN-lock fraud assessment. JSON stdin -> JSON stdout."""
import json
import sys
from datetime import datetime, timedelta, timezone


def parse_dt(value):
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def age_days(now, value):
    dt = parse_dt(value)
    return None if not dt else max(0, (now - dt).total_seconds() / 86400)


def norm(value):
    return str(value or '').strip().lower()


def money(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def add(flags, key, points, note, missing=None):
    flags[key] = {'points': points, 'note': note}
    if missing:
        missing.append(missing)


def location_key(tx):
    return tuple(norm(tx.get(x)) for x in ('city', 'state', 'country'))


def main(data):
    now = parse_dt(data.get('now'))
    if not now:
        raise ValueError('now must be an ISO-8601 timestamp')
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    card = data.get('card') or {}
    account = data.get('account') or {}
    cards = data.get('all_cards') or []
    attempts = [x for x in (data.get('declined_attempts') or [])
                if norm(x.get('type')) in ('atm_withdrawal_declined', 'pos_declined')]
    attempts.sort(key=lambda x: parse_dt(x.get('timestamp')) or datetime.min.replace(tzinfo=timezone.utc))
    successful = data.get('successful_transactions') or []
    recent = data.get('recent_transactions') or []
    flags, missing, triggers, questions = {}, [], [], []

    if not card.get('pin_locked'):
        missing.append('target card is not confirmed pin_locked=true')
    if norm(card.get('pin_lock_reason')) == 'security_hold':
        triggers.append('security_hold: security-team escalation; chat cannot unlock')
    target_id = card.get('card_id')
    if any(c.get('pin_locked') and c.get('card_id') != target_id for c in cards):
        triggers.append('other_card_locked: investigate and score every locked card before any unlock')
    for c in cards:
        days = age_days(now, c.get('date_issued'))
        if norm(c.get('issue_reason')) == 'stolen' and days is not None and days <= 90:
            triggers.append('recent_stolen_replacement: enhanced verification required')
            break

    addr = data.get('customer_address') or {}
    if attempts and addr.get('city'):
        max_points, detail = 0, ''
        for tx in attempts:
            city, state, country = norm(tx.get('city')), norm(tx.get('state')), norm(tx.get('country'))
            home_city, home_state, home_country = norm(addr.get('city')), norm(addr.get('state')), norm(addr.get('country'))
            if not city:
                continue
            if city == home_city:
                p = 0
            elif country and home_country and country != home_country:
                p = 3
            elif state and home_state and state != home_state:
                p = 2
            else:
                p = 1
            if p >= max_points:
                max_points, detail = p, ', '.join(str(v or 'unknown') for v in (tx.get('city'), tx.get('state'), tx.get('country')))
        if data.get('confirmed_location'):
            max_points = 0
            detail = 'removed after customer confirmed location'
        add(flags, 'A1_location_mismatch', max_points, detail)
        if flags['A1_location_mismatch']['points'] and not data.get('confirmed_location'):
            questions.append('Ask whether the customer was at the declined-attempt location.')
    else:
        add(flags, 'A1_location_mismatch', 0, 'unavailable', missing)

    locations = {location_key(x) for x in attempts if any(location_key(x))}
    add(flags, 'A2_location_scatter', 2 if len(locations) >= 3 else 1 if len(locations) == 2 else 0,
        '%d distinct declined locations' % len(locations))

    seven = now - timedelta(days=7)
    recent_success = [x for x in successful if parse_dt(x.get('timestamp')) and parse_dt(x['timestamp']) >= seven]
    home_only = recent_success and all(norm(x.get('city')) == norm(addr.get('city')) for x in recent_success if x.get('city'))
    declines_elsewhere = any(norm(x.get('city')) and norm(x.get('city')) != norm(addr.get('city')) for x in attempts)
    if recent_success:
        add(flags, 'A3_travel_pattern_conflict', 1 if home_only and declines_elsewhere else 0,
            'successful transactions considered in prior 7 days')
    else:
        add(flags, 'A3_travel_pattern_conflict', 0, 'unavailable: no dated successful transactions', missing)

    hours = [parse_dt(x.get('timestamp')).hour for x in attempts if parse_dt(x.get('timestamp'))]
    if hours:
        def hp(h): return 3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0
        p = max(hp(h) for h in hours)
        if data.get('confirmed_time'): p = 0
        if data.get('customer_said_asleep') and max(hp(h) for h in hours) >= 2:
            triggers.append('customer_asleep_during_high-risk_time: critical fraud indication')
        add(flags, 'B1_time_of_day', p, 'highest declined-attempt time band')
        if p >= 2 and not data.get('confirmed_time'):
            questions.append('Ask whether the customer was using the card at the relevant time.')
    else:
        add(flags, 'B1_time_of_day', 0, 'unavailable: timestamps required', missing)

    pin_success = [parse_dt(x.get('timestamp')) for x in successful if x.get('pin_used') and parse_dt(x.get('timestamp'))]
    if pin_success:
        days = (now - max(pin_success)).total_seconds() / 86400
        add(flags, 'B2_since_last_legitimate_pin_use', 2 if days > 30 else 1 if days >= 7 else 0, '%.1f days' % days)
    else:
        add(flags, 'B2_since_last_legitimate_pin_use', 0, 'unavailable: successful PIN-use history required', missing)

    times = [parse_dt(x.get('timestamp')) for x in attempts if parse_dt(x.get('timestamp'))]
    if len(times) >= 2:
        mins = min((b-a).total_seconds()/60 for a, b in zip(times, times[1:]))
        add(flags, 'B3_attempt_velocity', 3 if mins < 1 else 2 if mins < 2 else 1 if mins <= 5 else 0, 'minimum gap %.2f minutes' % mins)
    else:
        add(flags, 'B3_attempt_velocity', 0, 'unavailable: at least two timed attempts required', missing)

    amounts = [money(x.get('amount')) for x in attempts]
    amounts = [x for x in amounts if x is not None]
    decreasing = len(amounts) >= 3 and all(b < a for a, b in zip(amounts, amounts[1:]))
    p = 0 if data.get('confirmed_amount_pattern') else 2 if decreasing else 0
    add(flags, 'C1_amount_pattern', p, 'decreasing consecutive attempts' if decreasing else 'not decreasing')
    if p:
        questions.append('Ask whether the customer remembers the listed attempted amounts.')
    all_round = bool(amounts) and all(x > 0 and x % 100 == 0 for x in amounts)
    add(flags, 'C2_round_number_testing', 1 if all_round else 0, 'all amounts are round hundreds' if all_round else 'mixed or unavailable amounts')

    atm_success = [money(x.get('amount')) for x in successful if norm(x.get('type')) == 'atm_withdrawal' and money(x.get('amount')) is not None]
    if atm_success and amounts:
        avg, ratio = sum(atm_success)/len(atm_success), max(amounts)/(sum(atm_success)/len(atm_success))
        add(flags, 'C3_amount_vs_historical_average', 2 if ratio > 5 else 1 if ratio > 2 else 0, 'largest attempt %.2fx ATM average' % ratio)
    else:
        add(flags, 'C3_amount_vs_historical_average', 0, 'unavailable: successful ATM history and attempt amounts required', missing)

    limit = money(card.get('daily_atm_limit'))
    if limit and amounts:
        total, largest = sum(amounts), max(amounts)
        add(flags, 'C4_amount_vs_daily_limit', 2 if total > limit else 1 if largest >= .8 * limit else 0,
            'attempt total %.2f; limit %.2f' % (total, limit))
    else:
        add(flags, 'C4_amount_vs_daily_limit', 0, 'unavailable: daily ATM limit and amounts required', missing)

    locks = card.get('prior_pin_locks_90d')
    if isinstance(locks, int) and locks >= 0:
        add(flags, 'D1_lock_frequency', 3 if locks >= 3 else locks, '%d prior locks' % locks)
    else:
        add(flags, 'D1_lock_frequency', 0, 'unavailable: prior 90-day lock count required', missing)
    days = age_days(now, card.get('date_issued'))
    if days is None:
        add(flags, 'D2_card_age', 0, 'unavailable: card issuance date required', missing)
    else:
        add(flags, 'D2_card_age', 2 if days < 30 else 1 if days < 90 else 0, '%.0f days active' % days)
    other = [c for c in cards if c.get('card_id') != target_id]
    d3 = 2 if any(c.get('fraud_alert_active') for c in other) else 1 if any(c.get('velocity_blocked') for c in other) else 0
    add(flags, 'D3_other_card_issues', d3, 'other-card security flags')

    days = age_days(now, account.get('date_opened'))
    if days is None:
        add(flags, 'E1_account_age', 0, 'unavailable: account opening date required', missing)
    else:
        add(flags, 'E1_account_age', 2 if days < 90 else 1 if days < 180 else 0, '%.0f days open' % days)
    overdrafts = sum(1 for x in recent if norm(x.get('type')) == 'overdraft_fee')
    add(flags, 'E2_overdraft_history', 2 if overdrafts >= 2 else 1 if overdrafts == 1 else 0, '%d overdraft fees' % overdrafts)
    balance = account.get('balance')
    try:
        balance = float(balance)
        add(flags, 'E3_low_balance', 2 if balance < 50 else 1 if balance < 100 else 0, 'balance %.2f' % balance)
    except (TypeError, ValueError):
        add(flags, 'E3_low_balance', 0, 'unavailable: current balance required', missing)

    raw = sum(x['points'] for x in flags.values())
    critical_flag = any(x['points'] == 3 for x in flags.values())
    if raw <= 4: risk, protocol = 'LOW', 'standard identity verification before unlock'
    elif raw <= 7: risk, protocol = 'MEDIUM', 'ask ownership of failed attempts before unlock'
    elif raw <= 10: risk, protocol = 'HIGH', 'ask location/time questions; unlock only with confirmation and satisfactory explanation'
    elif raw <= 14: risk, protocol = 'VERY_HIGH', 'do not unlock; callback or enhanced verification required'
    else: risk, protocol = 'CRITICAL', 'do not unlock; inspect unauthorized successful activity and recommend closure/replacement'
    prior = card.get('prior_pin_locks_90d')
    cannot = bool(triggers) or raw >= 11 or critical_flag or (isinstance(prior, int) and prior >= 3)
    if isinstance(prior, int) and prior >= 3:
        protocol = 'PIN reset required; unlock prohibited due to three or more prior locks'
    print(json.dumps({'automatic_triggers': triggers, 'flags': flags, 'raw_score': raw,
        'adjusted_score': raw, 'risk_level': risk, 'required_protocol': protocol,
        'supervisor_review': critical_flag, 'cannot_unlock': cannot,
        'required_questions': questions, 'missing_data': missing}, indent=2))

if __name__ == '__main__':
    try:
        main(json.load(sys.stdin))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
