---
name: pin-lock-fraud-investigation
description: Investigate one or more PIN-locked debit cards before any unlock. Use for PIN decline/lock requests requiring identity verification, account/card/history review, fraud-risk scoring, customer questions, escalation, PIN reset, or an eligible unlock.
---

# PIN Lock Fraud Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and guardrails

Use this workflow whenever a PIN-related decline has `pin_locked = TRUE`. Do not unlock simply because the customer describes a legitimate failed attempt. Do not disclose internal risk scores, point values, fraud-code details, or scoring calculations to the customer.

Treat every locked card independently. If more than one card on the account is PIN-locked, investigate and score every locked card before performing an unlock on any of them. Do not invent card states, transactions, timestamps, a PIN-unlock tool, or a successful result.

## Required information and tools

1. Verify the caller's identity and authority as the cardholder before any banking action. Confirm two of date of birth, email, phone number, and address against the user record, then use `log_verification` with all required fields and the current timestamp. A verbal ownership assertion alone is not sufficient.
2. Use `get_current_time` for the verification/audit time and as the assessment reference time.
3. Retrieve accounts using `get_all_user_accounts_by_user_id_3847(user_id)`. When it is a discoverable agent tool, first unlock it, then call it through the discoverable-agent interface.
4. For each checking account, retrieve all cards using `get_debit_cards_by_account_id_7823(account_id)`, after unlocking it if necessary. Identify the actual card ID, owner, status, last four, issue reason, issue date, ATM limit, and any returned PIN-lock fields.
5. Retrieve account history using `get_bank_account_transactions_9173(account_id)`, after unlocking it if necessary. Preserve the records needed to assess dates, descriptions/locations, amounts, statuses, successful PIN/ATM use, and overdraft fees.
6. Ask targeted follow-up questions when records cannot establish whether an attempt, location, time, or amount was authorized. The customer must identify the card (normally last four digits) before a card-specific action.

Only use a dedicated unlock action if that action is actually available in the runtime and all conditions below permit an unlock. Follow that tool's required arguments and confirmations. Never substitute an unrelated card action. If the required unlock capability is unavailable, explain that the case needs the appropriate card-support/security handling rather than claiming the card was unlocked.

## Investigation sequence

### 1. Discover the complete card situation

- Confirm each target card belongs to the verified user and is eligible for the contemplated action.
- Inspect all card records, including historical/replaced cards, to determine whether another card is locked and whether any card was replaced in the last 90 days with `issue_reason = stolen`.
- If any other card is locked, complete the evidence collection and individual assessment for all locked cards first.
- A `pin_lock_reason` of `security_hold` means the card cannot be unlocked by chat. Offer transfer to the security team for that card.
- A stolen replacement within 90 days requires enhanced verification before an otherwise eligible outcome. Do not treat it as permission to skip the risk assessment.

### 2. Build the evidence set per locked card

Review declined records whose type is `atm_withdrawal_declined` or `pos_declined` when such records are returned. Consider the suspicious period around the lock and successful transactions in the preceding seven days. Parse location only when the transaction description reliably supplies it; otherwise ask the customer rather than guessing.

Determine, for the individual card:

- declined attempt locations, times, amounts, order, and spacing;
- last successful legitimate PIN use, where records support identifying it;
- recent successful ATM withdrawals for an average amount;
- the card's prior PIN locks in the last 90 days, card age, and other-card velocity/fraud-alert status when returned by the available data;
- account opening date, recent overdraft fees, and current balance.

If necessary information is unavailable, do not fabricate a zero score. State the missing evidence, ask the relevant question, or escalate where a safe determination cannot be made.

### 3. Score flags

Use `scripts/risk_score.py` for deterministic arithmetic after normalizing the retrieved evidence into its documented JSON input. Retain the flag names and supporting facts in internal notes, not in customer-facing language. The flags are:

- **A1 location mismatch:** same city 0; different city/same state 1; different state 2; different country 3.
- **A2 location scatter:** one location 0; two 1; three or more 2.
- **A3 travel conflict:** add 1 only when all successful transactions in the prior seven days are in the home city and declines are elsewhere.
- **B1 time:** 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3.
- **B2 last legitimate PIN use:** through 7 days 0; 7–30 days 1; over 30 days 2.
- **B3 velocity:** over 5 minutes 0; 2–5 minutes 1; 1–2 minutes 2; under 1 minute 3. Assess consecutive failed attempts.
- **C1 amount pattern:** same retried amount or increasing 0; decreasing 2.
- **C2 round-number testing:** all attempted amounts are round hundreds 1; otherwise 0.
- **C3 amount versus average successful ATM withdrawal:** within 2x 0; 2–5x 1; over 5x 2.
- **C4 amount versus daily ATM limit:** below 80% 0; 80–100% 1; attempts totaling over the limit 2.
- **D1 prior locks (90 days):** 0/1/2/3+ locks score 0/1/2/3. Three or more requires PIN reset and cannot be unlocked.
- **D2 card age:** under one month 2; one to three months 1; otherwise 0.
- **D3 other-card issues:** velocity block 1; fraud alert 2; no issues 0. Apply the documented applicable condition; do not double-count unsupported overlapping conditions.
- **E1 account age:** under three months 2; three to six months 1; otherwise 0.
- **E2 overdrafts:** none 0, one 1, two or more 2.
- **E3 balance:** under $50 is 2; $50–100 is 1; otherwise 0.

A single 3-point flag requires supervisor review regardless of the total.

### 4. Customer verification based on results

For a score of 5 or higher, ask only the applicable questions before deciding:

- Location flag: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, remove location flags and recalculate; if no, retain them.
- Decreasing-amount flag: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Remove that flag only if confirmed.
- Time flag of 2 or more: “These attempts occurred at [time]. Were you trying to use your card at that time?” Remove the time flag if confirmed. If the customer says they were asleep or gives an equivalent denial, treat as likely fraud and do not unlock.

Do not reveal the internal numerical calculation while asking these questions.

### 5. Decide and act

- **0–4, low:** unlock only after standard identity verification and all ownership/card prerequisites are satisfied.
- **5–7, medium:** unlock only after asking whether the failed attempts were the customer's and receiving an adequate response.
- **8–10, high:** ask specific location/time questions. Unlock only if the customer confirms and gives a satisfactory explanation.
- **11–14, very high:** do not unlock on the call. Require callback verification or enhanced verification (last four SSN plus security question).
- **15+, critical:** never unlock. Check for successful unauthorized transactions and recommend closure/replacement.
- **Any 3-point flag:** supervisor review is required even if the total is lower.
- **D1 = 3+:** do not unlock; require a PIN reset.

Where an unlock is allowed, complete the D1 follow-up: no extra step after zero prior locks; offer PIN-lock notifications after one prior lock; after two prior locks offer a PIN reset and explain this is the third lock in 90 days.

When a reset is required, verify the active card and ownership, obtain/confirm last four digits and a customer-selected new PIN, validate it is exactly four digits and is neither sequential, all identical, nor a birth-year or birth-month/day value, then use `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` if available. Never repeat or display the PIN.

When the card cannot be unlocked, review the suspicious period for successful unauthorized transactions. If found, follow the available dispute, closure, and replacement procedures. If not found, explain the security concern without disclosing protected fraud details and offer appropriate options: security-team investigation, PIN reset, or closure/replacement where fraud is suspected. Use `transfer_to_human_agents` with `fraud_or_security_concern` when security review is needed.

## Script interface

`scripts/risk_score.py` reads one JSON object from standard input and emits one JSON object on standard output. It calculates only supplied, normalized facts; `null` means unavailable and is returned in `missing_inputs`. Review missing inputs before using its output to authorize a banking action.

Example invocation through the skill runtime:

```json
{
  "relative_path": "scripts/risk_score.py",
  "input_json": {
    "location_mismatch": "different_state",
    "distinct_decline_locations": 2,
    "decline_hours": [23],
    "last_legitimate_pin_days": 10,
    "attempt_gaps_minutes": [1.5],
    "amounts": [80, 50, 30],
    "average_successful_atm_amount": 40,
    "daily_atm_limit": 300,
    "prior_locks_90d": 1,
    "card_age_days": 80,
    "account_age_days": 400,
    "overdraft_count": 0,
    "current_balance": 200
  }
}
```

Validate that the returned total equals the sum of returned flags, that each score is tied to retrieved evidence, and that a `single_flag_escalation` or `pin_reset_required` result overrides a total-score unlock path.
