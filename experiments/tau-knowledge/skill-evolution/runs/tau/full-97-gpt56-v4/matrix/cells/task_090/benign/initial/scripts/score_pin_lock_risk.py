#!/usr/bin/env python3
"""Deterministic internal scorer for the PIN-lock fraud protocol.
Reads a normalized JSON evidence object from stdin; writes one JSON result to stdout.
"""
import json, sys
from datetime import datetime, timedelta, timezone


def parse_dt(value):
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if value.endswith('Z'):
            value = value[:-1] + '+00:00'
        dt = datetime.fromisoformat(value)
    except ValueError:
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def norm(value):
    return str(value or '').strip().casefold()


def loc_key(location):
    location = location or {}
    return tuple(norm(location.get(k)) for k in ('city', 'state', 'country'))


def is_round_hundred(amount):
    try:
        return float(amount) > 0 and float(amount) % 100 == 0
    except (TypeError, ValueError):
        return False


def main(data):
    now = parse_dt(data.get('now'))
    home = data.get('home_location') if isinstance(data.get('home_location'), dict) else {}
    declines = data.get('declines') if isinstance(data.get('declines'), list) else []
    successes = data.get('successful_transactions') if isinstance(data.get('successful_transactions'), list) else []
    missing, flags = [], []

    def missing_once(label):
        if label not in missing:
            missing.append(label)

    def add(code, points, reason, removable_by=None):
        flags.append({'id': code, 'points': points, 'reason': reason,
                      'removable_by': removable_by, 'removed': False})

    if not now:
        missing_once('now')
    if not home.get('city'):
        missing_once('home_location.city')
    if not declines:
        missing_once('declined PIN-attempt records')

    # Automatic triggers only when explicit evidence was supplied.
    triggers = []
    if norm(data.get('pin_lock_reason')) == 'security_hold':
        triggers.append('security_hold')
    other_cards = data.get('other_cards') if isinstance(data.get('other_cards'), list) else []
    if any(bool(c.get('pin_locked')) and not bool(c.get('is_current_card')) for c in other_cards if isinstance(c, dict)):
        triggers.append('another_card_pin_locked')
    stolen = bool(data.get('recent_stolen_replacement'))
    if now and isinstance(data.get('cards'), list):
        for card in data['cards']:
            if isinstance(card, dict) and norm(card.get('issue_reason')) == 'stolen':
                issued = parse_dt(card.get('date_issued'))
                if issued and timedelta(0) <= now - issued <= timedelta(days=90):
                    stolen = True
    if stolen:
        triggers.append('recent_stolen_replacement')

    # A1 and A2: locations from declines.
    usable_locs = [d.get('location') for d in declines if isinstance(d, dict) and isinstance(d.get('location'), dict) and d['location'].get('city')]
    if declines and not usable_locs:
        missing_once('decline locations')
    elif usable_locs and home.get('city'):
        highest = 0
        for location in usable_locs:
            if norm(location.get('city')) == norm(home.get('city')):
                p = 0
            elif home.get('country') and location.get('country') and norm(location.get('country')) != norm(home.get('country')):
                p = 3
            elif home.get('state') and location.get('state') and norm(location.get('state')) != norm(home.get('state')):
                p = 2
            else:
                p = 1
            highest = max(highest, p)
        if highest:
            add('A1_location_mismatch', highest, 'highest mismatch among declined-attempt locations', 'location_confirmed')
        distinct = {loc_key(x) for x in usable_locs}
        if len(distinct) >= 3:
            add('A2_location_scatter', 2, 'three or more declined-attempt locations', 'location_confirmed')
        elif len(distinct) == 2:
            add('A2_location_scatter', 1, 'two declined-attempt locations', 'location_confirmed')

    # A3 needs successful activity for the seven-day comparison.
    if declines:
        if not successes or not now:
            missing_once('successful transactions from prior 7 days for travel comparison')
        elif usable_locs:
            recent = [s for s in successes if isinstance(s, dict) and parse_dt(s.get('timestamp')) and timedelta(0) <= now - parse_dt(s.get('timestamp')) <= timedelta(days=7)]
            recent_locs = [s.get('location') for s in recent if isinstance(s.get('location'), dict) and s['location'].get('city')]
            if recent and not recent_locs:
                missing_once('locations of successful transactions from prior 7 days')
            elif recent_locs and all(norm(x.get('city')) == norm(home.get('city')) for x in recent_locs) and any(norm(x.get('city')) != norm(home.get('city')) for x in usable_locs):
                add('A3_travel_pattern_conflict', 1, 'recent successful activity only in home city while declines are elsewhere', 'location_confirmed')

    # B1 highest risky declined hour; B3 minimum gap.
    decline_times = [parse_dt(d.get('timestamp')) for d in declines if isinstance(d, dict) and parse_dt(d.get('timestamp'))]
    if declines and not decline_times:
        missing_once('decline timestamps')
    else:
        hour_points = []
        for dt in decline_times:
            h = dt.hour
            hour_points.append(3 if 2 <= h < 6 else 2 if 0 <= h < 2 else 1 if 22 <= h < 24 else 0)
        if hour_points and max(hour_points):
            add('B1_time_of_day', max(hour_points), 'highest-risk declined-attempt time', 'time_confirmed')
        if len(decline_times) >= 2:
            ordered = sorted(decline_times)
            gap = min((b-a).total_seconds()/60 for a, b in zip(ordered, ordered[1:]))
            p = 3 if gap < 1 else 2 if gap < 2 else 1 if gap <= 5 else 0
            if p:
                add('B3_attempt_velocity', p, 'shortest interval between failed attempts')
        elif declines:
            missing_once('at least two timestamps for attempt velocity')

    last_pin = parse_dt(data.get('last_legitimate_pin_use'))
    if not last_pin or not now:
        missing_once('last legitimate successful PIN use')
    else:
        days = (now - last_pin).total_seconds() / 86400
        if days > 30:
            add('B2_since_legitimate_pin', 2, 'more than 30 days since legitimate PIN use')
        elif days >= 7:
            add('B2_since_legitimate_pin', 1, '7 to 30 days since legitimate PIN use')

    ordered_declines = sorted([d for d in declines if isinstance(d, dict) and isinstance(d.get('amount'), (int, float))], key=lambda d: parse_dt(d.get('timestamp')) or datetime.min.replace(tzinfo=timezone.utc))
    amounts = [abs(float(d['amount'])) for d in ordered_declines]
    if declines and not amounts:
        missing_once('declined-attempt amounts')
    elif amounts:
        if len(amounts) >= 2 and all(b < a for a, b in zip(amounts, amounts[1:])):
            add('C1_amount_pattern', 2, 'consecutively decreasing declined amounts', 'amount_pattern_confirmed')
        if all(is_round_hundred(x) for x in amounts):
            add('C2_round_number_testing', 1, 'all declined amounts are round hundreds')
        atm_success = [abs(float(s['amount'])) for s in successes if isinstance(s, dict) and isinstance(s.get('amount'), (int, float)) and norm(s.get('type')) == 'atm_withdrawal']
        if not atm_success:
            missing_once('recent successful ATM withdrawals for historical average')
        else:
            average = sum(atm_success) / len(atm_success)
            ratio = max(amounts) / average if average else None
            if ratio is not None and ratio > 5:
                add('C3_vs_historical_average', 2, 'largest attempt exceeds five times average successful ATM withdrawal')
            elif ratio is not None and ratio > 2:
                add('C3_vs_historical_average', 1, 'largest attempt is over two times average successful ATM withdrawal')
        limit = data.get('daily_atm_limit')
        if not isinstance(limit, (int, float)) or limit <= 0:
            missing_once('daily ATM withdrawal limit')
        else:
            total = sum(amounts)
            if total > float(limit):
                add('C4_vs_daily_limit', 2, 'declined attempts total more than daily ATM limit')
            elif max(amounts) >= .8 * float(limit):
                add('C4_vs_daily_limit', 1, 'an attempted amount is 80–100% of daily ATM limit')

    prior = data.get('prior_locks_90d')
    if not isinstance(prior, int) or prior < 0:
        missing_once('prior PIN-lock count in last 90 days')
    elif prior >= 3:
        add('D1_lock_frequency', 3, 'three or more prior PIN locks in 90 days')
    elif prior == 2:
        add('D1_lock_frequency', 2, 'two prior PIN locks in 90 days')
    elif prior == 1:
        add('D1_lock_frequency', 1, 'one prior PIN lock in 90 days')

    def age_flag(field, code, thresholds):
        dt = parse_dt(data.get(field))
        if not dt or not now:
            missing_once(field)
            return
        days = (now-dt).total_seconds()/86400
        for maximum, points, reason in thresholds:
            if days < maximum:
                if points: add(code, points, reason)
                return
    age_flag('card_date_issued', 'D2_card_age', [(30, 2, 'card is less than one month old'), (90, 1, 'card is one to three months old')])
    if other_cards:
        if any(bool(c.get('fraud_alert_active')) for c in other_cards if isinstance(c, dict)):
            add('D3_other_card_issues', 2, 'another card has an active fraud alert')
        elif any(bool(c.get('velocity_blocked')) for c in other_cards if isinstance(c, dict)):
            add('D3_other_card_issues', 1, 'another card has a velocity block')
    else:
        missing_once('other-card security status')
    age_flag('account_date_opened', 'E1_account_age', [(90, 2, 'account is less than three months old'), (180, 1, 'account is three to six months old')])
    overdrafts = data.get('overdraft_count')
    if not isinstance(overdrafts, int) or overdrafts < 0:
        missing_once('recent overdraft-fee count')
    elif overdrafts >= 2: add('E2_overdraft_history', 2, 'two or more overdrafts')
    elif overdrafts == 1: add('E2_overdraft_history', 1, 'one overdraft')
    balance = data.get('current_balance')
    if not isinstance(balance, (int, float)):
        missing_once('current account balance')
    elif balance < 50: add('E3_low_balance', 2, 'balance below $50')
    elif balance < 100: add('E3_low_balance', 1, 'balance from $50 to under $100')

    confirmations = data.get('confirmations') if isinstance(data.get('confirmations'), dict) else {}
    if confirmations.get('location_confirmed'):
        for f in flags:
            if f['removable_by'] == 'location_confirmed': f['removed'] = True
    if confirmations.get('amount_pattern_confirmed'):
        for f in flags:
            if f['id'] == 'C1_amount_pattern': f['removed'] = True
    if confirmations.get('time_confirmed'):
        for f in flags:
            if f['id'] == 'B1_time_of_day': f['removed'] = True
    asleep = bool(confirmations.get('customer_was_asleep'))
    total = sum(f['points'] for f in flags if not f['removed'])
    single_three = any(f['points'] == 3 and not f['removed'] for f in flags)
    if asleep:
        protocol = 'critical_suspected_fraud_no_unlock'
    elif total >= 15:
        protocol = 'critical_no_unlock'
    elif total >= 11:
        protocol = 'very_high_callback_or_enhanced_verification_no_unlock'
    elif total >= 8:
        protocol = 'high_specific_location_time_questions_then_only_satisfactory_confirmed_unlock'
    elif total >= 5:
        protocol = 'medium_must_ask_failed_attempt_ownership_before_unlock'
    else:
        protocol = 'low_standard_identity_verification_before_unlock'
    constraints = []
    if 'security_hold' in triggers: constraints.append('security hold: security-team transfer; no chat unlock')
    if 'another_card_pin_locked' in triggers: constraints.append('complete all locked-card investigations before any unlock')
    if 'recent_stolen_replacement' in triggers: constraints.append('enhanced verification required')
    if single_three: constraints.append('supervisor review required because a retained flag is 3 points')
    if isinstance(prior, int) and prior >= 3: constraints.append('PIN reset required; do not unlock')
    return {'flags': flags, 'total_score': total, 'single_three_point_flag': single_three,
            'automatic_triggers': triggers, 'missing_inputs': missing, 'protocol': protocol,
            'constraints': constraints, 'assumptions': ['Each flag is scored once.', 'For per-attempt flags, the highest applicable risk is used.', 'C4 uses all declined amounts in the supplied evidence; C3 uses the largest attempt and mean successful ATM withdrawal.', 'Unknown evidence is reported as missing and contributes no assumed points.']}

if __name__ == '__main__':
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict): raise ValueError('input must be a JSON object')
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({'error': 'invalid_input', 'message': str(exc)}))
        sys.exit(2)
