---
name: pin-lock-fraud-investigation
description: Safely investigate one or more PIN-locked debit cards. Use for PIN lock or PIN-decline requests that require customer verification, card/account-history review, per-card fraud-risk scoring, escalation, PIN reset, or an eligible unlock.
---

# PIN-Locked Debit Card Investigation

## Safety rules

Use this workflow when a card record has `pin_locked: true`. Do not unlock a card merely because the customer says an attempt was legitimate. Do not disclose internal scores, points, fraud flags, or decline codes. Never request or repeat a full card number, CVV, or existing PIN. Request a new PIN only in the documented PIN-reset step.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Verify the caller by matching **two** of date of birth, email, phone number, and address against the customer record. Obtain the current time and then call `log_verification` with the complete retrieved profile and timestamp. A name or an assertion of ownership is not verification.

When more than one card is locked, collect evidence and make an individual assessment for **every** locked card before unlocking any card. Do not invent a card status, transaction, timestamp, tool, or result. Only call a dedicated PIN-unlock tool if it is actually available and the assessment permits it; never substitute a different card action or claim an unavailable action succeeded.

## Lookup and evidence collection

1. Locate the customer, verify identity as above, and retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. If it is discoverable, unlock it first.
2. For every checking account, use `get_debit_cards_by_account_id_7823(account_id)` and retain card ID, owner, status, last four, issue reason/date, ATM limit, lock state/reason/time, prior-lock count, and alert/block fields when returned.
3. For each relevant checking account, use `get_bank_account_transactions_9173(account_id)`. Review declined `atm_withdrawal_declined` and `pos_declined` records around the lock, successful transactions during the prior seven days, recent successful **legitimate** ATM withdrawals (excluding the suspicious period), and overdraft fees. Treat an account field labeled `current_holdings` as the current balance when that is the balance field returned by the lookup.
4. Confirm that a target card belongs to the verified user and is active before a reset or other card action. Ask the customer to identify a card by last four digits before a card-specific action.

Automatic restrictions:

- `pin_lock_reason = security_hold`: do not unlock in chat; transfer to security.
- A card replaced for `stolen` within 90 days: obtain enhanced verification before any otherwise permitted outcome.
- Another locked card is not itself a reason to unlock or deny a card; it means all locked cards must first be assessed.

If the records do not establish a required fact, leave it unknown rather than scoring it as zero. Ask a targeted question or escalate when a safe determination cannot be made.

## Per-card scoring

Normalize only supported evidence and run:

```sh
python3 scripts/risk_score.py <<'JSON'
{"location_mismatch":"same_city","distinct_decline_locations":1,"home_city_successes_and_declines_elsewhere":false,"decline_hours":[14],"last_legitimate_pin_days":1,"attempt_gaps_minutes":[3],"amounts":[20],"average_successful_atm_amount":50,"daily_atm_limit":500,"prior_locks_90d":0,"card_age_days":365,"other_card_issue":"none","account_age_days":800,"overdraft_count":0,"current_balance":200}
JSON
```

Supply dates as day differences from the assessment reference time; amounts and limits are non-negative USD numbers; `decline_hours` is a list of 24-hour integer hours; and `other_card_issue` is `none`, `velocity_block`, or `fraud_alert`. The script reads one JSON object from stdin and prints one JSON object containing `flags`, `total`, `risk_level`, `assessment_complete`, `single_flag_escalation`, `pin_reset_required`, and `missing_inputs`. A nonzero exit or `assessment_complete: false` is not an unlock decision: obtain the missing evidence or escalate. Validate a completed result by confirming `total` equals the sum of `flags`, every flag has supporting retrieved evidence, and either `single_flag_escalation` or `pin_reset_required` overrides a total-based unlock path.

Apply these flags per card:

| Flag | Points |
|---|---|
| A1 location mismatch | same city 0; different city/same state 1; different state 2; different country 3 |
| A2 distinct decline locations | one 0; two 1; three or more 2 |
| A3 travel conflict | 1 only if all successful prior-7-day transactions were in the home city and declines were elsewhere |
| B1 decline time | 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3 |
| B2 since last legitimate PIN use | through 7 days 0; 7–30 days 1; over 30 days 2 |
| B3 failed-attempt gap | over 5 min 0; 2–5 min 1; 1–2 min 2; under 1 min 3 |
| C1 amounts across consecutive failures | same or increasing 0; decreasing 2 |
| C2 amounts | all round hundreds 1; otherwise 0 |
| C3 amount vs average successful ATM withdrawal | within 2× 0; 2–5× 1; over 5× 2 |
| C4 amount vs daily ATM limit | below 80% 0; 80–100% 1; failed attempts totaling over limit 2 |
| D1 PIN locks in 90 days | 0/1/2/3+ locks = 0/1/2/3; 3+ requires reset, never unlock |
| D2 card age | under 1 month 2; 1–3 months 1; otherwise 0 |
| D3 other-card issue | none 0; velocity block 1; fraud alert 2 |
| E1 account age | under 3 months 2; 3–6 months 1; otherwise 0 |
| E2 overdrafts | none 0; one 1; two or more 2 |
| E3 balance | below $50: 2; $50–100: 1; above $100: 0 |

Use the maximum applicable B1/B3/C3/C4 exposure for multiple failures. A single 3-point flag requires supervisor/security review regardless of total. Keep the facts and score internal.

## Customer questions and decision

For a score of 5 or more, ask only the applicable questions before deciding:

- Location: “I see failed PIN attempts at [location]. Were you there?” A confirmed yes removes location flags; a no retains them.
- Decreasing amounts: ask whether the customer remembers the listed attempts in their actual chronological order. Remove C1 only if confirmed.
- B1 of 2 or more: ask whether they were trying to use the card at that time. If they say they were asleep or otherwise deny it, do not unlock.

Then apply the outcome per card:

- **0–4:** eligible for an available unlock after verification and all prerequisites.
- **5–7:** eligible only after asking whether the failed attempts were theirs and receiving an adequate response.
- **8–10:** ask specific location/time questions; unlock only with confirmation and a satisfactory explanation.
- **11–14:** do not unlock in chat; require callback verification or enhanced verification (last four SSN plus a security question).
- **15+:** never unlock. Check the suspicious period for completed unauthorized transactions; recommend closure/replacement.
- **Any 3-point flag:** do not unlock pending supervisor/security review.
- **D1 of 3:** do not unlock; a PIN reset is required. Use `reset_debit_card_pin_6284` only after identity/ownership verification, last-four confirmation, and a valid new PIN (exactly four digits; not sequential, repeated, birth year, or birth month/day).

If the customer denies suspicious failed attempts, review successful transactions in the same period and ask whether each is authorized. If unauthorized successful transactions are confirmed, follow the fraud outcome: protect the card using the documented closure procedure if its prerequisites are met, seek the available dispute process, and transfer to security/supervisor review using the applicable transfer reason. Do not represent a dispute, replacement, or PIN action as completed unless its actual tool reports success.

After an eligible unlock, offer PIN-lock notifications after one prior lock; after two prior locks, offer a PIN reset. For a fraud-related closure, tell the customer the card cannot be reactivated, recurring payments need updating, and recommend changing online-banking credentials. Discuss replacement only under the applicable replacement procedure, including its fees and confirmation.
