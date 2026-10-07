---
name: debit-card-pin-lock-investigation
description: Safely investigate one or more debit cards reporting incorrect-PIN or PIN-lock declines. Use for PIN-locked debit cards before any unlock decision, including multi-account customers, fraud-risk scoring, security escalation, PIN reset, and possible card closure/replacement.
---

# Debit-Card PIN Lock Investigation

Use this workflow whenever a debit card has `pin_locked = TRUE`, a PIN-related decline indicates the PIN is locked, or a customer reports repeated incorrect-PIN/locked-card messages. Never simply unlock a PIN-locked card. Do not reveal fraud-score calculations, flag values, internal decline codes, or security rationale to the customer.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and tool use

The executor receives the customer conversation and may receive prior read-only observations. Treat prior observations as evidence, but confirm that identity verification has been logged before any banking action.

1. Verify the caller using at least two of date of birth, email, phone number, and address against the user record. Confirm the person is the card owner. Obtain the current timestamp with `get_current_time` and call `log_verification` with all fields returned by the user lookup.
2. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`.
3. For **every checking account**, unlock and call `get_debit_cards_by_account_id_7823`. Match each card's `user_id` to the verified customer. Collect card ID, status, issue reason, issuance date, ATM limit, PIN-lock fields, fraud-alert/velocity fields, and any lock-history fields returned.
4. Unlock and call `get_bank_account_transactions_9173` for each relevant checking account. Preserve raw results and normalize only the facts needed by the assessor: timestamps, merchant/ATM location, type, amount, status, successful PIN uses, declined PIN attempts, overdraft fees, and potentially unauthorized successful transactions.
5. The card/transaction tools named above are discoverable agent tools. Use `unlock_discoverable_agent_tool` before `call_discoverable_agent_tool`. Do not guess tool names or call a banking action tool merely because a script recommends an action.

If an expected field is absent or dates/locations cannot be reliably derived, mark that item unknown. Do not silently award zero points. Ask for clarification, seek security review, or defer the unlock decision as appropriate.

## Multi-card and automatic-trigger handling

Investigate and score every PIN-locked card separately. If another card on the account is also PIN-locked, complete investigation of all such cards before unlocking any of them.

Before scoring each target card, check:

- `pin_lock_reason == "security_hold"`: chat agents cannot unlock it. Offer transfer to the security team.
- Any other PIN-locked card on the account: no card may be unlocked until all are investigated.
- Any account card issued/replaced for `issue_reason == "stolen"` in the preceding 90 days: require enhanced verification. Enhanced verification should include last four SSN digits and an approved security question; do not treat standard verification alone as sufficient.

A bank-initiated fraud alert must be transferred to security and must not be cleared. A customer-initiated alert or velocity block may be cleared only after identity verification and only through `clear_debit_card_fraud_alert_4892` with its documented reason. Clearing an alert/block is not a substitute for the PIN-lock assessment.

## Score and decision process

Normalize the gathered facts and run:

```text
python3 scripts/pin_lock_assess.py < assessment-input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. It is advisory and intentionally fails closed: its `missing_inputs` or `decision = "investigate_before_decision"` means do not unlock. Its output contains internal findings; do not copy flag scores or calculations into a customer-facing message.

### Assessment input schema

```json
{
  "now": "ISO-8601 timestamp",
  "target_card": {"card_id":"...", "date_issued":"YYYY-MM-DD", "daily_atm_limit":500, "pin_lock_reason":"..."},
  "all_cards": [{"card_id":"...", "pin_locked":true, "issue_reason":"stolen", "date_issued":"YYYY-MM-DD", "velocity_blocked":false, "fraud_alert_active":false}],
  "account": {"opened":"YYYY-MM-DD", "balance":600, "home_city":"Boston"},
  "declines": [{"timestamp":"ISO-8601", "city":"...", "state":"...", "country":"US", "amount":100}],
  "successful_transactions_7d": [{"timestamp":"ISO-8601", "city":"...", "state":"...", "country":"US", "amount":20}],
  "successful_atm_amounts": [40, 60],
  "last_legitimate_pin_use": "ISO-8601",
  "prior_pin_locks_90d": 0,
  "overdraft_count": 0,
  "all_locked_investigated": false,
  "remove_flags": []
}
```

Use chronological order for declined attempts. `remove_flags` is only set after the customer gives the specific confirmation required below; allowed values are `A1`, `A2`, `A3`, `B1`, and `C1`. Do not use it to erase a flag without the documented confirmation.

The assessment applies the documented A1–A3, B1–B3, C1–C4, D1–D3, and E1–E3 rules. It uses the highest applicable time/location result where the policy describes individual attempts and the closest consecutive-attempt interval for velocity. A flag worth 3 points requires supervisor review regardless of total. D1 of 3 or more prior locks requires PIN reset rather than unlock.

### Required customer questions and recalculation

For total score 5 or more, ask only applicable questions:

- Location mismatch: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, remove the location flags supported by that confirmation and recalculate. If no, retain them.
- Decreasing amount pattern: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Remove C1 only if confirmed.
- Time-of-day score 2 or 3: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, remove B1 and recalculate. If the customer says they were asleep or gives an equivalent denial, treat it as likely fraud: do not unlock and escalate.

After each answer, rerun the script with the justified `remove_flags`. Keep a record of the factual explanation, not the numerical score, in interaction notes.

### Threshold actions

- **0–4:** unlock only after standard identity verification and all prerequisites are met.
- **5–7:** ask “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the customer answers satisfactorily and applicable follow-up is complete.
- **8–10:** ask the applicable location/time questions. Unlock only if the customer confirms and gives a satisfactory explanation.
- **11–14:** do not unlock on this contact. Require callback verification or enhanced verification (last 4 SSN plus security question).
- **15+:** do not unlock. Check for successful unauthorized transactions; recommend closure/replacement and security handling.

For any case where the protocol permits an unlock, use only a declared, authorized PIN-unlock tool after verifying card ID, ownership, active/eligible status, and confirmation requirements. No such tool name is inferred by this Skill. If no declared unlock capability is available, explain the next safe option and transfer/escalate rather than improvising a reset or status change.

## Post-unlock and fraud branches

After a permitted unlock:

- 0 prior locks: standard unlock.
- 1 prior lock: offer PIN-lock notifications using the documented wording.
- 2 prior locks: offer a PIN reset, explaining it is the third lock in 90 days.
- 3+ prior locks: do not unlock; require PIN reset.

A PIN reset is distinct from an unlock. Reset only for a verified owner and ACTIVE card, after confirming card last four digits and a valid new four-digit PIN; never repeat or display the PIN. It must not be used to bypass a security hold, fraud escalation, or an unresolved risk decision.

When an unlock cannot proceed, review the suspicious period for successful unauthorized transactions. If the customer identifies unauthorized transactions, begin the applicable dispute process and consider closure/replacement. For closure, re-check ownership, eligible card status, pending activity/refunds, and the closure reason; suspected fraud/lost/stolen cases receive the documented security handling. For replacement, check checking-account tier, replacement count in the prior 12 months, waiting period, delivery/design options, exact fees, available balance, delivery address, and customer confirmation before ordering. State that applicable replacement fees are deducted automatically from checking before placing the order.

If no unauthorized transaction is found, give safe options: PIN reset where appropriate, security-team investigation, or closure/replacement when fraud is suspected. Use `transfer_to_human_agents` with `fraud_or_security_concern` for security holds, bank-initiated alerts, likely fraud, or required supervisor/security review.

## Output validation

Before an action or final response, confirm: identity verification was logged; all customer checking accounts/cards were reviewed; every locked card has an outcome; the target card belongs to the caller; automatic triggers were handled; missing evidence did not become a zero-point score; required questions and recalculation were completed; and no internal code, score, or calculation is disclosed. The customer-facing response should state only the current safe next step, any required verification, and available options.
