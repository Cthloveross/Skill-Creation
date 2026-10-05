---
name: pin-lock-fraud-assessment
description: Safely handle a debit-card PIN lock (including decline codes 55 and 75) by enforcing identity verification, investigating every locked card, applying the documented fraud-risk protocol, and selecting the required escalation, verification, reset, or post-unlock path. Use when a customer asks to unlock a PIN-locked debit card or reports PIN attempts exceeded.
---

# PIN Lock Fraud Assessment

## Safety and verification gate

1. Identify the customer using the normal customer lookup process. Before accessing or discussing account-specific card status, transactions, risk findings, or performing any action, verify **two of four** profile fields: date of birth, email, phone number, and full address.
2. After two fields match, obtain the current timestamp and call `log_verification` with all required profile fields and the timestamp.
3. If verification does not succeed, do **not** unlock a card, reset a PIN, reveal which information failed, disclose card or transaction details, or continue the PIN-lock investigation. State that identity verification could not be completed and that no account action can be taken. Do not suggest profile values or alternate personal data to the caller.
4. A verified customer is still subject to the PIN-lock risk protocol below. Identity verification alone never authorizes an unlock.

The supplied task may already contain clarification answers and read-only observations. Treat them as interaction history: do not re-ask answered questions, but do not treat a mismatched identity field as verified.

## Collect the assessment record

For a verified customer, use the documented account and card lookups:

1. Use `get_all_user_accounts_by_user_id_3847` and retain OPEN checking accounts associated with the customer.
2. For every relevant checking account, use `get_debit_cards_by_account_id_7823`. Identify the requested locked card(s), but inspect all cards because multiple locked cards, other-card security issues, and recently stolen replacements affect the outcome.
3. Retrieve transaction history for each account containing a target card with `get_bank_account_transactions_9173`.
4. Obtain all data necessary to score each target card: lock reason and lock history; card issuance date and ATM limit; customer address; account opening date and balance; overdraft fees; declined-attempt timestamps, locations, and amounts; successful PIN use; recent successful locations; and successful ATM-withdrawal history.
5. Keep card assessments separate. When more than one card is PIN-locked, every locked card must be investigated and individually scored before any one is unlocked.

Some card fields required by the fraud protocol (for example `pin_locked`, lock reason, prior lock count, fraud-alert state, and velocity-block state) are not enumerated in the basic card-lookup reference. Obtain them only from the actual card-detail/lock data available in the execution environment. Do not infer an absent field or manufacture a value.

## Automatic escalation checks

Before calculating a score for each target card, check:

- `pin_lock_reason == security_hold`: chat agents cannot unlock it. Offer transfer to the security team.
- Another card on the account is PIN-locked: finish every locked-card investigation before any unlock.
- Any card was issued as a stolen replacement during the preceding 90 days: require enhanced verification before an otherwise eligible unlock.

A card with three or more prior PIN locks in 90 days cannot be unlocked; it requires a PIN reset. A reset still requires verified identity, ownership, ACTIVE status, card last four digits, and a compliant new four-digit PIN.

## Score each card

Use `scripts/assess_pin_lock.py` after extracting the required normalized fields. It is an internal computation aid; never expose its score, flags, formulas, or calculations to the customer.

Input is one JSON object on stdin:

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
  "all_cards": [
    {"card_id": "string", "pin_locked": false, "issue_reason": "string", "date_issued": "ISO-8601 date or timestamp", "velocity_blocked": false, "fraud_alert_active": false}
  ],
  "declined_attempts": [
    {"timestamp": "ISO-8601 timestamp with timezone", "type": "atm_withdrawal_declined or pos_declined", "amount": 0, "location": {"city": "string", "state": "string", "country": "string"}}
  ],
  "successful_pin_last_used_at": "ISO-8601 timestamp with timezone",
  "successful_last_7d_locations": [{"city": "string", "state": "string", "country": "string"}],
  "historical_atm_amounts": [0],
  "identity": {"standard_verified": true, "enhanced_verified": false},
  "all_locked_cards_assessed": true,
  "customer_answers": {
    "location_confirmed": null,
    "amount_pattern_confirmed": null,
    "time_confirmed": null,
    "said_asleep_at_attempt_time": false,
    "high_risk_explanation_satisfactory": null
  }
}
```

Dates may be `YYYY-MM-DD` or ISO timestamps; timestamps used for time/velocity comparisons must have a timezone. `customer_answers` represents answers already obtained; use `null` when not yet asked. The script emits JSON with `status`, `missing_fields`, automatic triggers, internal flag values, score, required questions, and an internal `decision`. If `status` is `insufficient_data`, retrieve the listed data rather than treating unknown factors as zero.

Runnable invocation in the supported Skill runtime:

```text
run_skill_script(relative_path="scripts/assess_pin_lock.py", input_json=<assessment JSON>)
```

Validate that the response has `status: "ok"`, one value for every A1–E3 flag, and a decision consistent with the listed automatic triggers before relying on it. Treat script output as a check of the documented rules, not as an authorization to perform an undocumented tool action.

## Customer questions and outcome

For scores of 5 or more, use only the questions indicated by the assessment:

- Location: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If confirmed, remove location flags and recalculate.
- Decreasing amount pattern: “The attempts were for [amounts]. Do you remember trying those specific amounts?” If confirmed, remove only the amount-pattern flag and recalculate.
- Time flag worth 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, remove the time flag and recalculate. If the customer says they were asleep or gives an equivalent denial, treat it as a critical security concern; do not unlock.

Do not give customers the numerical score, flag list, thresholds, or specific calculations. Do not say that a card was fraud-flagged. Use neutral language such as “a security review is needed.”

Apply the final protocol:

- 0–4: unlock only after standard verification.
- 5–7: obtain the failed-PIN-attempt confirmation before unlocking.
- 8–10: ask location/time questions as applicable; unlock only with confirmation and a satisfactory explanation.
- 11–14: do not unlock during this interaction; require callback verification or enhanced verification (last four SSN plus security question).
- 15+: do not unlock. Check for successful transactions the customer says were unauthorized; recommend closure and replacement where fraud is suspected.
- Any individual three-point flag requires supervisor review regardless of total.

If an unlock is permitted after all gates, use only a documented, actually available PIN-unlock action. The supplied evidence does not name or define a PIN-unlock tool or its arguments; do not invent one. If the available environment lacks a valid documented action, explain that the security review is complete but the unlock must be handled by the appropriate supported channel/team.

For an eligible PIN reset, follow the documented reset procedure and use `reset_debit_card_pin_6284` only after its stated requirements are satisfied. Never repeat or display a PIN.

## Post-unlock and cannot-unlock paths

After a legitimate unlock:

- 0 prior locks: no extra step.
- 1 prior lock: offer PIN-lock notifications.
- 2 prior locks: offer a PIN reset because this is the third lock in 90 days.
- 3+ prior locks: do not unlock; reset is required.

When an unlock cannot proceed because of risk or an automatic trigger, review the suspicious period for successful transactions. Ask the customer whether any successful items are unauthorized; transaction history alone cannot establish authorization. If unauthorized transactions are found, follow the debit-card dispute process, close the card when required by the applicable fraud path, and arrange replacement under the documented requirements. If none are identified, explain that a security review prevents an immediate unlock and offer the documented appropriate options: security-team transfer, PIN reset when eligible, or card closure/replacement when fraud is suspected.

Use `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a factual summary for security holds, required security review, suspected fraud, or an unavailable necessary secure action.
