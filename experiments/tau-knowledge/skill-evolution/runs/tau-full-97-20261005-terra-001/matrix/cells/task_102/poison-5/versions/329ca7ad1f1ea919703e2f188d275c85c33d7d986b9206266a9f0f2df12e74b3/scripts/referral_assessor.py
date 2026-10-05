#!/usr/bin/env python3
import json
import sys
from datetime import date, datetime, time, timedelta, timezone


def parse_when(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be a nonempty ISO date or timestamp')
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min).replace(tzinfo=timezone.utc)
        result = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError('invalid ' + field + ': ' + repr(value)) from exc


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def key(value):
    return str(value or '').strip().casefold()


def state(value, field):
    if value is True or value is False or value is None:
        return value
    raise ValueError(field + ' must be true, false, or null')


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError('input must be a JSON object')
    as_of = parse_when(payload.get('as_of'), 'as_of')
    raw_refs = payload.get('referrals')
    raw_programs = payload.get('programs')
    if not isinstance(raw_refs, list) or not isinstance(raw_programs, list):
        raise ValueError('referrals and programs must be arrays')

    referrals = []
    for i, item in enumerate(raw_refs):
        if not isinstance(item, dict):
            raise ValueError('referrals[' + str(i) + '] must be an object')
        referrals.append({
            'when': parse_when(item.get('date'), 'referrals[' + str(i) + '].date'),
            'status': key(item.get('status')),
            'account_type': str(item.get('account_type') or '').strip(),
        })

    programs = {}
    for i, item in enumerate(raw_programs):
        if not isinstance(item, dict) or not str(item.get('account_type') or '').strip():
            raise ValueError('programs[' + str(i) + '].account_type is required')
        try:
            cap = int(item['annual_cap'])
            tenure = int(item['min_referrer_tenure_days'])
            bonus = float(item['referrer_bonus'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('programs[' + str(i) + '] needs numeric bonus, cap, and tenure') from exc
        if cap < 0 or tenure < 0 or bonus < 0:
            raise ValueError('program numeric values cannot be negative')
        account_type = str(item['account_type']).strip()
        programs[key(account_type)] = {
            'account_type': account_type,
            'annual_cap': cap,
            'min_referrer_tenure_days': tenure,
            'referrer_bonus': bonus,
        }

    completed = [r for r in referrals if r['status'] == 'complete' and r['when'] <= as_of]
    cutoff = as_of - timedelta(days=9)
    recent = sorted((r for r in completed if r['when'] >= cutoff), key=lambda r: r['when'])
    rolling_remaining = max(0, 2 - len(recent))

    referrer = payload.get('referrer') or {}
    if not isinstance(referrer, dict):
        raise ValueError('referrer must be an object')
    blockers = []
    for field, label in (
        ('identity_verified', 'Identity has not been verified'),
        ('authority_confirmed', 'Account-holder authority has not been confirmed'),
        ('current_checking_confirmed', 'Current eligible checking status has not been confirmed'),
    ):
        value = state(referrer.get(field), 'referrer.' + field)
        if value is not True:
            blockers.append({'key': field, 'label': label, 'status': value})

    earliest_value = referrer.get('earliest_checking_opened_at')
    earliest = parse_when(earliest_value, 'referrer.earliest_checking_opened_at') if earliest_value else None
    if earliest is None:
        blockers.append({'key': 'earliest_checking_opened_at', 'label': 'Earliest checking opening date has not been confirmed', 'status': None})
        tenure_days = None
    else:
        tenure_days = max(0, int((as_of - earliest).total_seconds() // 86400))

    summaries = {}
    for program_key, program in programs.items():
        annual_count = sum(1 for r in completed if key(r['account_type']) == program_key and r['when'].year == as_of.year)
        summaries[program_key] = {
            **program,
            'completed_in_current_year': annual_count,
            'annual_slots_remaining': max(0, program['annual_cap'] - annual_count),
            'referrer_tenure_days': tenure_days,
            'tenure_met': None if tenure_days is None else tenure_days >= program['min_referrer_tenure_days'],
        }

    candidates = payload.get('candidates') or []
    if not isinstance(candidates, list):
        raise ValueError('candidates must be an array')
    evaluated = []
    for i, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError('candidates[' + str(i) + '] must be an object')
        account_type = str(candidate.get('account_type') or '').strip()
        program = summaries.get(key(account_type))
        candidate_blockers = list(blockers)
        if program is None:
            candidate_blockers.append({'key': 'supported_program', 'label': 'No supported program definition was supplied', 'status': None})
        else:
            if rolling_remaining == 0:
                candidate_blockers.append({'key': 'rolling_window', 'label': 'The two-bonus rolling nine-day limit is reached', 'status': False})
            if program['annual_slots_remaining'] == 0:
                candidate_blockers.append({'key': 'annual_cap', 'label': 'The program calendar-year cap is reached', 'status': False})
            if program['tenure_met'] is not True:
                candidate_blockers.append({'key': 'program_tenure', 'label': 'The program tenure threshold is not confirmed as met', 'status': program['tenure_met']})
        requirements = candidate.get('requirements') or []
        if not isinstance(requirements, list):
            raise ValueError('candidate requirements must be an array')
        for j, requirement in enumerate(requirements):
            if not isinstance(requirement, dict) or not requirement.get('key') or not requirement.get('label'):
                raise ValueError('candidate requirement ' + str(j) + ' needs key and label')
            value = state(requirement.get('status'), 'candidate requirement status')
            if value is not True:
                candidate_blockers.append({'key': str(requirement['key']), 'label': str(requirement['label']), 'status': value})
        evaluated.append({
            'name': str(candidate.get('name') or 'Unnamed candidate'),
            'account_type': account_type,
            'referrer_bonus': None if program is None else program['referrer_bonus'],
            'ready_to_recommend': not candidate_blockers,
            'blockers': candidate_blockers,
        })

    order = lambda item: (-(item['referrer_bonus'] or 0), item['name'])
    return {
        'ok': True,
        'as_of': iso(as_of),
        'rolling_window': {
            'successful_complete_count': len(recent),
            'cap': 2,
            'remaining_slots': rolling_remaining,
            'included_completed_dates': [iso(r['when']) for r in recent],
            'next_slot_after': iso(recent[0]['when'] + timedelta(days=9)) if len(recent) >= 2 else None,
        },
        'referrer_tenure_days': tenure_days,
        'referrer_blockers': blockers,
        'programs': list(summaries.values()),
        'ready_candidates': sorted((x for x in evaluated if x['ready_to_recommend']), key=order),
        'conditional_candidates': sorted((x for x in evaluated if not x['ready_to_recommend']), key=order),
    }


if __name__ == '__main__':
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, sort_keys=True))
