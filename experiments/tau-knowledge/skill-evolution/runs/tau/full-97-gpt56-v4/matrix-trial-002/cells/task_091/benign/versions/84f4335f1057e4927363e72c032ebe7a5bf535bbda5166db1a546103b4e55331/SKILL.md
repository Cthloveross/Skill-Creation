---
name: pin-lock-fraud-review
version: 1.4.0
description: Handle requests to unlock PIN-locked debit cards. Use for PIN decline/lock cases needing identity verification, complete account/card and transaction review, fraud scoring, risk questions, and secure unlock, reset, replacement, or transfer decisions.
---

# PIN-lock fraud review

Never reveal score calculations/thresholds or sensitive card data. Do not disclose account activity, log verification, or change a card until the caller is verified.

## Verify

1. Use a name, email, or user ID only to find a possible profile; lookup is not verification.
2. Match **two distinct** fields among date of birth, email, phone, and address. A mismatch never counts. Ask for a different field after a mismatch.
3. When two fields match, get the current time and call `log_verification` with every profile field and the timestamp.
4. If verification fails, make no change; explain that verification is required and offer secure assistance where appropriate.

## Scope and automatic triggers

After verification, unlock/call `get_all_user_accounts_by_user_id_3847(user_id)`. For every checking account, unlock/call `get_debit_cards_by_account_id_7823(account_id)` and `get_bank_account_transactions_9173(account_id)`. Transactions arrive newest first, so sort relevant declines chronologically before comparing amounts or time gaps.

Inventory every currently PIN-locked card. For each card/account group, check:

- `pin_lock_reason = security_hold`: never unlock in chat; transfer to security.
- Another PIN-locked card on the **same account**: assess every locked card before any unlock. Locks on separate accounts are not this trigger.
- A card issued for `stolen` in the past 90 days: enhanced verification is required.

A trigger adds a gate; it does not replace the individual fraud review. Use the current date for the 90-day test.

## Score each locked card separately

For each card derive all policy flags from declined `atm_withdrawal_declined`/`pos_declined`, successful transactions, card records, other cards, account opening date, overdraft fees, and current balance:

- **A1–A3:** location mismatch to verified home city/state; distinct decline locations; conflict with last-seven-day successful activity.
- **B1–B3:** decline time band; time since successful PIN use; shortest gap between failed attempts.
- **C1–C4:** chronological amount pattern; round-hundreds pattern; comparison with recent successful ATM average; comparison/aggregate against daily ATM limit.
- **D1–D3:** 90-day lock frequency; card age; other cards' velocity block/fraud alert.
- **E1–E3:** account age; recent overdraft-fee count; current balance.

Apply the supplied policy's exact bands. A returned fact can establish a zero (for example, zero prior locks); do not assume unknown material evidence is zero. Retrieve it if possible; otherwise leave the card unresolved and escalate instead of authorizing an unlock.

Run `scripts/assess_pin_risk.py` with normalized flags. It reads one JSON object on stdin and writes one JSON object on stdout; it only validates/totals and performs no bank action:

```json
{"automatic_triggers":{"security_hold":false,"other_cards_locked":false,"recent_stolen_replacement":false},"flags":{"A1":0,"A2":0,"A3":0,"B1":0,"B2":0,"B3":0,"C1":0,"C2":0,"C3":0,"C4":0,"D1":0,"D2":0,"D3":0,"E1":0,"E2":0,"E3":0}}
```

All triggers must be explicit booleans; all flags must be in their stated integer range. Null/omitted flags make the assessment incomplete. Inspect `required_internal_gates`, not only `total_score`: gates can coexist, and a known three-point/D1 flag remains a gate even if another flag is unavailable. `unlock_eligible_after_gates` is never permission to skip a listed gate or invent an action tool. Do not show this output to the customer.

## Customer questions and decision

Once all reported cards are scoped and individually assessed, work on the customer's requested card first. Ask questions only for that card, rather than overwhelming the customer with all cards at once.

For medium or above, first ask: “I see failed PIN attempts on your card. Were those attempts yours?” Then, where applicable:

- Ask whether they were at a mismatched transaction location. On confirmation remove only supported location flag(s), then recalculate.
- For decreasing amounts, ask whether they remember the listed amounts in chronological order. Remove C1 only on confirmation.
- For a B1 score of at least two, ask whether they used the card at that time. If asleep/clearly denied, treat it as likely fraud: do not unlock and review unauthorized activity.

High requires the specific confirmations and satisfactory location/time explanation. Recalculate only supported changes. Apply final gates: low needs standard verification; medium needs ownership confirmation; high needs the above questions; very high cannot be unlocked on the call and needs callback or enhanced verification (last four SSN plus a security question); critical cannot be unlocked and requires review for successful unauthorized activity plus closure/replacement recommendation. D1 at three points requires a PIN reset, not an unlock. Any three-point flag requires supervisor review regardless of total.

For suspected/identified unauthorized activity, use available dispute, closure, and replacement procedures. If none is found, explain the security concern without scores and offer the allowed reset, security review, or closure/replacement option. Before a replacement, retrieve tier/history, apply limits/waits and exact delivery/design fees, and disclose automatic fee charging.

A reset requires verified ownership, ACTIVE status, confirmed last four, and a customer-chosen compliant 4-digit PIN (not sequential, identical, birth year, or birth month/day). Unlock/call `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)`; never repeat/display the PIN.

Use a PIN-unlock tool only when it is declared with documented parameters. Never guess one. If none is available for an otherwise eligible card, tell the customer secure card support must complete it and transfer for fraud/security assistance. A security hold may be transferred immediately; otherwise complete the current card's necessary fraud questions first. After an eligible unlock, offer notifications after one prior lock and a reset after two prior locks.
