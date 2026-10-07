---
name: pin-lock-fraud-investigation
description: Investigate PIN-locked debit cards using the required fraud-risk protocol. Use when a verified customer reports a locked PIN or PIN decline (such as codes 55 or 75) and requests an unlock, PIN reset, fraud help, closure, or replacement.
---

# PIN Lock Fraud Investigation

Use this Skill for each PIN-locked debit card separately. It is especially important when multiple cards on one account are locked: do not unlock any card until every locked card has been investigated and its disposition is known. Never disclose fraud-score calculations, internal flag values, or thresholds to the customer.

## Inputs and prerequisites

Obtain at runtime:

- Customer identity and ownership of the card/account.
- All debit cards for the customer/account, including `pin_locked`, lock reason, status, issue reason, issue/replace dates, ATM withdrawal limit, linked account, and security flags.
- Linked checking-account opening date, current balance, tier if a replacement is requested, and overdraft setting when relevant.
- Transaction history for each linked account, including posted and pending activity. Retrieve it with the documented `get_bank_account_transactions_9173(account_id)` procedure when available through the runtime's discoverable-tool mechanism.
- Declined PIN-attempt data with timestamp, amount, and location; successful PIN-use and successful ATM history; prior PIN-lock dates; and relevant card replacement history.
- The customer's answers about whether the attempts and any suspicious successful transactions were theirs.

Before *any* banking action, verify identity, authority, ownership, card/account eligibility and status, available balance where relevant, applicable fees/limits/cutoffs, card/recipient details, and confirmation requirements. Verification requires confirmation of two of the four profile fields (date of birth, email, phone number, address); after successful verification, obtain the current timestamp and log the verification record using the runtime's logging tool. A name lookup alone is not one of those two fields. Do not perform an unlock, reset, closure, or replacement until this is complete.

If required records, dates, locations, transaction types, or relevant tool access are unavailable, do not assume that the risk is low. Tell the customer that the investigation cannot yet be completed and transfer to the security team/supervisor as appropriate.

## Runtime workflow

1. Identify the customer and verify two profile fields. Confirm that the customer owns the card. Log successful verification before any banking action.
2. Retrieve all debit cards and accounts. Identify every card with `pin_locked = TRUE`; inspect each one, even if the customer initially chooses one card.
3. For each locked card, first check automatic escalation triggers:
   - `pin_lock_reason = security_hold`: chat must not unlock; offer transfer to the security team.
   - Another card on the same account is PIN locked: finish investigations of all cards before any unlock.
   - Any account card replaced for `stolen` within the last 90 days: require enhanced verification.
4. Gather the card's declined `atm_withdrawal_declined` and `pos_declined` records, successful activity in the prior seven days, recent successful ATM withdrawals, and the card/account history needed for all flags. Normalize the facts and run `scripts/assess_pin_lock.py` once per card. The script reports missing inputs as `unknown_fields`; resolve them before relying on a low-risk result.
5. Apply the protocol based on the assessment, without revealing calculations:
   - Any 3-point single flag requires supervisor review regardless of total.
   - 0–4: unlock only after standard verification and only if no automatic trigger blocks it.
   - 5–7: ask whether the failed attempts were theirs before unlocking.
   - 8–10: ask specifically about the location and time; unlock only after confirmation and a satisfactory explanation.
   - 11–14: do not unlock on this contact; require callback verification or enhanced verification (last four SSN plus security question).
   - 15+: do not unlock; check for successful unauthorized transactions and recommend closure/replacement.
6. For a score of 5+, ask only the questions matching scored flags:
   - Location: ask whether they were at the declined-attempt location. If yes, remove location flags and recalculate; if no, retain them.
   - Decreasing amount pattern: ask whether they remember the particular attempted amounts. Remove that flag only if confirmed.
   - Time-of-day score of 2+: ask whether they were using the card then. If they say they were asleep or equivalent, treat it as likely fraud and do not unlock.
   Record the answers in the input and rerun the assessment after removing only the protocol-authorized flags.
7. If eligible to unlock, use only the normal runtime banking unlock action if it is available and its requirements have been met. Do not substitute a PIN reset for an unlock. Apply post-unlock follow-up using *prior* lock count: none—standard unlock; one—offer PIN-lock notifications; two—offer a PIN reset; three or more—do not unlock and require PIN reset.
8. If the card cannot be unlocked, inspect the suspicious period for successful unauthorized transactions. If found, begin the supported dispute process and, after separately checking closure eligibility (ownership, active/pending status, pending transactions/refunds), close and replace as appropriate. If none are found, explain the security concern and offer security-team investigation, PIN reset, or closure/replacement.
9. A PIN reset requires verified ownership, an ACTIVE card, last four card digits, and a customer-selected compliant four-digit PIN (not sequential, repeated, birth year, or birth month/day). Use the documented reset procedure only after these conditions are satisfied; never expose or repeat a PIN.
10. If replacing a closed card, determine the linked account tier and count replacement cards issued in the previous 12 months with reasons lost, stolen, fraud, or damaged. Explain that applicable delivery, design, and excess-replacement fees are automatically debited from checking, obtain confirmation, and provide the exact tier- and shipping/design-dependent fees to the normal card-order action. Do not invent the order action or its parameters.

## Assessment script

Run `scripts/assess_pin_lock.py` with JSON on stdin. It emits JSON on stdout and makes no banking changes.

Input schema (all timestamps should be ISO-8601 with offsets where possible):

```json
{
  "now": "ISO timestamp",
  "home": {"city": "string", "state": "string", "country": "string"},
  "card": {
    "daily_atm_limit": 0,
    "active_since": "ISO date or timestamp",
    "prior_pin_locks_90d": 0,
    "other_card_issue": "none|velocity_block|fraud_alert"
  },
  "account": {"opened_at": "ISO date or timestamp", "current_balance": 0},
  "declines": [
    {"timestamp": "ISO timestamp", "amount": 0, "city": "string", "state": "string", "country": "string", "type": "atm_withdrawal_declined|pos_declined"}
  ],
  "successful_transactions_7d": [
    {"timestamp": "ISO timestamp", "city": "string", "state": "string", "country": "string"}
  ],
  "successful_pin_uses": [{"timestamp": "ISO timestamp"}],
  "successful_atm_withdrawals": [{"timestamp": "ISO timestamp", "amount": 0}],
  "overdraft_fee_count": 0,
  "removed_flags": ["A1", "A2", "A3", "B1", "C1"]
}
```

Amounts are non-negative dollar values. Supply all known declines in chronological order or allow the script to sort them. `removed_flags` is exclusively for flags the customer has affirmatively resolved under the prescribed questions. The output contains per-flag points, total, risk level, single-flag escalation, missing fields, and a disposition. Validate that no material required field is missing, every result refers to the intended card/account, and human facts match retrieved records before deciding an outcome.

## Customer communication

State the outcome and next required step plainly, but do not reveal the score, flag arithmetic, internal thresholds, or investigative heuristics. Never claim a transaction is unauthorized solely because of a score; ask the customer and follow the supported dispute process. Do not claim an unlock, reset, closure, dispute, or replacement occurred unless the corresponding runtime action returned success.
