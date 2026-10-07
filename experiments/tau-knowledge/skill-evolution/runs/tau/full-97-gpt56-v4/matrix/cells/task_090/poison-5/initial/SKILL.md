---
name: pin-lock-fraud-investigation
description: Investigate a PIN-locked debit card under the fraud-risk protocol. Use when a customer reports incorrect-PIN/PIN-tries-exceeded declines or a locked PIN and an agent must decide whether an unlock, PIN reset, security escalation, or fraud response is permitted.
---

# PIN Lock Fraud Investigation

Do not disclose risk scores, point values, or scoring calculations to the customer. Do not treat a fraud-alert or velocity-block clearing action as a PIN unlock, and never invent an unlock tool or clear a bank-initiated fraud alert.

## Preconditions and scope

1. Identify the customer and all linked checking accounts using only the normal banking lookup tools available in the runtime. Retrieve every debit card for each checking account with `get_debit_cards_by_account_id_7823(account_id)` (unlock that documented discoverable tool first if necessary).
2. A name, email, or account lookup is not identity verification. Before an action affecting a card, confirm two of the four identity fields (DOB, email, phone, address), obtain the current timestamp, and call `log_verification` with all required profile fields and that timestamp.
3. Investigate every card reported locked and every card returned with `pin_locked = true`. If another card on the account is PIN-locked, do not unlock any card before each affected card has been individually reviewed.
4. Obtain the current card state, PIN-lock reason, lock history, issue and issuance history, daily ATM limit, account opening date/balance, recent overdrafts, declined PIN transactions, successful transactions (including positively identified successful PIN uses), and other-card security status. Do not infer missing locations, PIN use, ownership, prior locks, or transaction authorization.

If required account/card/transaction data cannot be retrieved with supported tools, explain that the investigation cannot be completed safely and transfer to the security team rather than unlocking.

## Mandatory decision sequence

### 1. Automatic triggers first

For each card, check before scoring:

- `pin_lock_reason == security_hold`: the chat agent cannot unlock it; offer/perform a security-team transfer.
- Any other PIN-locked card on the same account: complete all individual card investigations before any unlock decision.
- Any card replaced for `issue_reason = stolen` within 90 days: require enhanced verification.

A security concern or an unsupported safe resolution should be transferred with the applicable normal transfer reason, ordinarily `fraud_or_security_concern`, and a factual summary. Do not retry an operation whose result is unknown.

### 2. Score the card, internally

Run `scripts/risk_assessment.py` after normalizing retrieved data into its documented JSON schema. It calculates the protocol flags from the supplied records and returns missing evidence separately. Review the returned flags against the source records before acting. If the tool output says data are missing for a material flag, retrieve the data or leave that flag unscored; never make up a zero.

Score the following for that card's declined `atm_withdrawal_declined` and `pos_declined` records:

- location mismatch, location scatter, and seven-day travel-pattern conflict;
- worst declined-attempt time of day, elapsed time since last positively identified legitimate PIN use, and fastest failed-attempt velocity;
- decreasing failed amount pattern, round-hundreds testing, attempted amount versus successful ATM average, and amount/aggregate attempts versus daily ATM limit;
- prior PIN locks in 90 days, card age, and security problems on other cards;
- account age, recent overdraft count, and current balance.

The script expects normalized city/state/country and timestamps; transaction descriptions alone are not a reliable substitute for a location field. It uses the highest applicable risk band where a rule concerns multiple attempts. `removed_flags` is only for a documented customer confirmation that the protocol says removes that precise flag; rerun it after such a confirmation.

### 3. Customer questions and outcome

For an initial score of 5 or greater, ask only the protocol questions relevant to scored flags:

- Location: ask whether the customer was at the recorded declined-attempt location. A yes permits removal of location flags and recalculation; a no retains them.
- Decreasing amount pattern: ask whether they remember trying the recorded amounts in order. Remove that flag only if confirmed.
- Time-of-day worth 2 or more: ask whether they were using the card at that time. If they say they were asleep or otherwise deny it, treat it as likely fraud and escalate; do not unlock.

Use the actual transaction location, time, and amounts in questions, but do not state a score or explain point arithmetic. A vague statement that a later ATM attempt failed does not confirm the earlier attempts that caused the lock.

Apply the final protocol result:

- **0–4:** unlock only after standard identity verification.
- **5–7:** unlock only after verified customer answers the failed-attempt ownership question.
- **8–10:** ask specific location/time questions; unlock only with confirmation and a satisfactory explanation.
- **11–14:** do not unlock on this contact; require callback verification or enhanced verification (last four SSN plus security question).
- **15+:** do not unlock; check suspicious-period transactions for successful unauthorized activity and recommend closure/replacement where fraud is suspected.
- **Any single 3-point flag:** supervisor review regardless of total.
- **Three or more prior PIN locks in 90 days:** do not unlock; a PIN reset is required.

For any no-unlock or fraud concern, review suspicious-period successful transactions. If unauthorized transactions exist, follow normal dispute, card-closure, and replacement procedures. Closure must meet its own documented requirements; for suspected fraud/lost/stolen, follow the documented security exception and use only the normal closure tool. If none are unauthorized, explain the security concern without revealing the score and offer security investigation, replacement/closure as appropriate, or PIN reset.

An actual PIN unlock may be performed only by a declared normal banking unlock capability after every applicable prerequisite above. This package does not identify such a tool; do not substitute `clear_debit_card_fraud_alert_4892` or fabricate a call.

### 4. PIN reset and post-unlock actions

For a required or customer-selected reset, ensure verified ownership and `ACTIVE` card status. Confirm the card last four digits, collect a new PIN without repeating it back, validate exactly four digits and reject sequential, repeated-digit, birth-year, or birth-month/day PINs. Use the documented `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` only when all conditions hold.

After an eligible unlock:

- 0 prior locks: standard completion.
- 1 prior lock: offer PIN-lock notifications.
- 2 prior locks: offer a reset because this is the third lock in 90 days.
- 3+ prior locks: reset rather than unlock.

## Risk script interface

Run:

```text
python scripts/risk_assessment.py < investigation.json
```

It reads one JSON object from stdin and emits one JSON object to stdout. Main input fields are:

```json
{
  "now": "ISO-8601 timestamp",
  "account": {
    "home_city": "string", "home_state": "string", "home_country": "string",
    "opened_at": "ISO-8601 timestamp", "current_balance": 0,
    "overdraft_count": 0
  },
  "cards": [{
    "card_id": "string", "pin_locked": true, "pin_lock_reason": "string",
    "issue_reason": "string", "date_issued": "ISO-8601 timestamp",
    "daily_atm_limit": 0, "prior_pin_locks_90d": 0,
    "fraud_alert_active": false, "velocity_blocked": false
  }],
  "declines": [{
    "card_id": "string", "type": "atm_withdrawal_declined",
    "timestamp": "ISO-8601 timestamp", "amount": 0,
    "city": "string", "state": "string", "country": "string"
  }],
  "successful_transactions": [{
    "card_id": "string", "timestamp": "ISO-8601 timestamp", "amount": 0,
    "type": "atm_withdrawal", "city": "string", "state": "string",
    "country": "string", "pin_used": true
  }],
  "removed_flags": {"card_id": ["A1_location_mismatch"]}
}
```

All money values are numeric dollars. Timestamps must include an offset when time-zone-sensitive. Omit unknown fields rather than use placeholders. The output contains `automatic_triggers`, per-card `flags`, `total_score`, `single_three_point_flag`, `outcome`, `questions`, and `missing_data`; it never performs banking actions.

Before acting, validate that every result card matches a retrieved card ID, only target-card declines were included, the account facts are current, timestamps are plausible, and all required verification/action conditions are satisfied.