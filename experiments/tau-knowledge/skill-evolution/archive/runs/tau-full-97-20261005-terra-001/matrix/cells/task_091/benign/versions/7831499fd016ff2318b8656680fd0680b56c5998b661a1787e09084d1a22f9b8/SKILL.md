---
name: pin-lock-fraud-assessment
description: Safely handle debit-card PIN locks and PIN-attempts-exceeded reports. Use this Skill to enforce caller-supplied identity verification, assess every locked card under the PIN Lock Investigation Protocol, and select a documented unlock, reset, or security escalation path.
---

# PIN Lock Fraud Assessment

## Non-negotiable identity-verification gate

1. Locate a possible customer record using the normal lookup process, but treat lookup results as reference data only. A retrieved profile field is **not** evidence that the caller supplied or verified that field.
2. Confirm at least two of these four fields using values actually supplied by the caller: date of birth, email, phone number, and full address. Compare each caller-supplied value to the profile.
3. Call `log_verification` only after the required matching caller-supplied fields establish successful verification. Record the matching evidence; never replace a caller's supplied value with a value read from the profile in order to make a verification log succeed.
4. If a requested or required field conflicts with the profile, verification is unresolved. In particular, if the caller supplies a DOB that does not match the profile DOB, do **not** regard the DOB as verified, do not state or imply that identity is verified, and do not call `log_verification` based on the profile DOB or other retrieved values.
5. Do not disclose the correct profile value, suggest alternate DOBs or other personal data, or say which profile value is on file. Say neutrally that identity verification could not be completed.
6. While verification is unresolved, do not access or disclose account-specific card or transaction details; do not investigate a PIN lock; and do not reset, change, unlock, freeze, unfreeze, close, or order a card.
7. For an unresolved verification failure involving a PIN lock or security concern, transfer to a human/security team with `transfer_to_human_agents`, using `reason: "fraud_or_security_concern"` and a factual summary that identity verification could not be completed and PIN-lock assistance was not performed. Await a successful transfer result before representing the escalation as complete.

Clarification answers and supplied read-only observations are interaction history. Do not re-ask an answer already supplied, but never treat a mismatch as a match. A name lookup, a user ID, or profile data returned by a tool does not itself prove caller identity.

## Assessment prerequisites after verification

Only after successful verification:

1. Use `get_all_user_accounts_by_user_id_3847` to identify the customer's OPEN checking accounts.
2. Use `get_debit_cards_by_account_id_7823` for each relevant checking account. Identify every requested PIN-locked card and inspect other cards for other locked cards and security issues.
3. Use `get_bank_account_transactions_9173` for each relevant account to obtain the transaction evidence needed for review.
4. Obtain actual available card-detail data for lock reason, lock history, fraud/velocity status, declined attempts, successful PIN use, limits, and issuance date. Do not infer unavailable values from the basic card lookup.
5. Assess every PIN-locked card separately. If more than one card is locked, complete every locked-card assessment before any unlock decision.

## Automatic escalation checks

Before scoring each target card, check the following:

- `pin_lock_reason == "security_hold"`: a chat agent cannot unlock it; transfer to the security team.
- Another card on the same account is PIN-locked: finish assessment of all locked cards before any unlock.
- A card was issued for `stolen` within the last 90 days: enhanced verification is required before an otherwise eligible unlock.
- Three or more prior PIN locks in 90 days: do not unlock; a PIN reset is required, subject to the reset requirements.

## Internal risk scoring

Use `scripts/assess_pin_lock.py` after extracting normalized, verified assessment data. This is an internal aid. Never reveal numerical scores, flags, thresholds, calculations, or an internal fraud designation to the customer.

The script receives one JSON object on stdin and emits one JSON object on stdout.

```json
{
  "now": "ISO-8601 timestamp with timezone",
  "target_card_id": "string",
  "customer_home": {"city": "string", "state": "string", "country": "string"},
  "card": {
    "pin_lock_reason": null,
    "date_issued": "ISO-8601 date or timestamp",
    "daily_atm_limit": 0,
    "prior_pin_locks_90d": 0
  },
  "account": {"date_opened": "ISO-8601 date or timestamp", "balance": 0, "overdraft_fee_count": 0},
  "all_cards": [{"card_id": "string", "pin_locked": false, "issue_reason": "string", "date_issued": "ISO-8601 date or timestamp", "velocity_blocked": false, "fraud_alert_active": false}],
  "declined_attempts": [{"timestamp": "ISO-8601 timestamp with timezone", "type": "atm_withdrawal_declined or pos_declined", "amount": 0, "location": {"city": "string", "state": "string", "country": "string"}}],
  "successful_pin_last_used_at": "ISO-8601 timestamp with timezone",
  "successful_last_7d_locations": [{"city": "string", "state": "string", "country": "string"}],
  "historical_atm_amounts": [0],
  "identity": {"standard_verified": true, "enhanced_verified": false},
  "all_locked_cards_assessed": true,
  "customer_answers": {"location_confirmed": null, "amount_pattern_confirmed": null, "time_confirmed": null, "said_asleep_at_attempt_time": false, "high_risk_explanation_satisfactory": null}
}
```

Run it as:

```text
run_skill_script(relative_path="scripts/assess_pin_lock.py", input_json=<assessment JSON>)
```

Require `status: "ok"` before using a score. If the result is `insufficient_data`, retrieve the named data rather than treating missing information as zero. Validate that all A1–E3 flags and the automatic-trigger result are present. The script does not authorize an undocumented banking action.

## Risk questions and decisions

For scores of 5 or higher, ask only the applicable documented questions:

- Location mismatch: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” A confirmation removes location flags and requires recalculation.
- Decreasing amounts: “The attempts were for [amounts]. Do you remember trying those specific amounts?” A confirmation removes only the amount-pattern flag and requires recalculation.
- Time flag of 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” A confirmation removes the time flag and requires recalculation. If the customer says they were asleep or otherwise denies the attempt, do not unlock.

Use neutral language such as “a security review is needed.” Apply the final protocol:

- Score 0–4: unlock only after standard identity verification.
- Score 5–7: unlock only after the customer confirms the failed PIN attempts were theirs.
- Score 8–10: unlock only after the required confirmation(s) and a satisfactory explanation.
- Score 11–14: do not unlock in this interaction; require callback or enhanced verification (last four SSN plus security question).
- Score 15+: do not unlock; review for successful unauthorized transactions and recommend closure/replacement when fraud is suspected.
- Any three-point flag requires supervisor review regardless of the total.

If an unlock is eligible, use only an actually available, documented unlock action. The supplied documentation does not define a PIN-unlock tool; do not invent one. If no supported secure action is available, transfer to the appropriate team.

## Reset, post-unlock, and cannot-unlock paths

A PIN reset requires verified identity, card ownership, ACTIVE status, card last four digits, and a compliant new four-digit PIN. Only then use `reset_debit_card_pin_6284`. Do not repeat or display a PIN.

After a valid unlock: offer notifications after one prior lock; offer a reset after two prior locks; and require reset rather than unlock after three or more prior locks.

When an unlock cannot proceed after verification, review the suspicious period and ask whether successful transactions were unauthorized. If unauthorized transactions are found, follow the documented dispute process and applicable closure/replacement requirements. Otherwise, explain that an immediate unlock cannot be completed and offer the appropriate documented option: security-team transfer, eligible PIN reset, or closure/replacement where fraud is suspected.
