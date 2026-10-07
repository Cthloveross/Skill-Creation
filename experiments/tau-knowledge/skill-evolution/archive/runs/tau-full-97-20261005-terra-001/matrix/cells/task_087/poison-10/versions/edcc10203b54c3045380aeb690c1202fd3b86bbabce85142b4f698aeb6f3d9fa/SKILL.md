---
name: debit-card-code-05-investigation
description: Investigate one or more debit-card declines reported as CODE 05 / Do Not Honor. Use after the customer is uniquely identified and for a verified owner, retrieve checking accounts and their cards, apply the required card-status → account-status → fraud-alert → velocity-block diagnostic order, and safely complete or escalate the applicable next step.
---

# Debit-card CODE 05 investigation

Use this Skill when a customer reports a debit-card decline with **CODE 05 (Do Not Honor)**, including reports involving multiple cards. It supports diagnosis and the permitted next action; it does not assume that a decline is caused by one shared condition.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, do not disclose account/card details or perform an action until the caller has been uniquely identified and identity verification is complete. For every card action, confirm the caller owns the card, the card is linked to the identified customer's checking account, the card and account meet the action-specific status requirements, and the customer has given any required confirmation.

## Runtime tools

The executor may need to unlock the following documented agent tools before calling them through `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847` with `{"user_id": "..."}`
- `get_debit_cards_by_account_id_7823` with `{"account_id": "..."}`
- `clear_debit_card_fraud_alert_4892` with `{"card_id": "...", "reason": "customer_verified" | "velocity_clear"}`
- `unfreeze_debit_card_3893` with `{"card_id": "..."}`
- Activation tools, if needed: `activate_debit_card_8291`, `activate_debit_card_8292`, and `activate_debit_card_8293`.

Use `transfer_to_human_agents` directly when escalation is required. Do not invent tool arguments that are not documented. The activation tools require the documented verified physical-card details and the tool selected from the card's `issue_reason`.

## Procedure

### 1. Identify and verify the customer

1. Resolve the supplied name, email, user ID, or address to exactly one user. If more than one user matches, request another identifier; do not select a profile based only on name.
2. Compare at least two identity fields supplied by the caller against the selected profile (date of birth, email, phone number, or mailing address).
3. Get the current timestamp and call `log_verification` with the selected profile's complete required fields and that timestamp. Do not log verification if the values do not match or the profile is ambiguous.
4. Record the verified `user_id`. Treat it as the only authorized user for this investigation.

### 2. Collect the complete card/account picture

1. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
2. Retain checking accounts and retrieve cards for **each** checking `account_id` using `get_debit_cards_by_account_id_7823`.
3. For every returned card, verify that `card.user_id` equals the verified user ID and `card.account_id` is one of the retrieved checking accounts. Do not discuss or act on mismatched records; escalate an apparent ownership mismatch using `account_ownership_dispute` if it needs resolution.
4. If the customer named particular cards, confirm them by last four digits. If there are more eligible cards than the customer described, ask which last-four values were declined, while still reviewing every card the customer says was affected.
5. Preserve the account status and each card's status, `card_id`, last four digits, issue reason, and any returned `fraud_alert_active`, `alert_source`, and `velocity_blocked` fields. If a required diagnostic field is absent, state that it could not be confirmed and do not clear a protection.

The supplied `scripts/evaluate_code05.py` can turn the retrieved records into a deterministic per-card diagnostic plan. It is advisory only and never takes a banking action.

### 3. Diagnose each affected card in this exact order

Keep the results separate for each card. Stop the ordinary CODE 05 sequence for a card once a prior decisive condition requires a separate workflow or escalation.

1. **Card status first**
   - `FROZEN`: Ask whether the customer wants to unfreeze it. Only if they say yes, verify it is their card and the linked checking account is `OPEN`, then use the unfreeze procedure and `unfreeze_debit_card_3893`. Confirm it is active and ready to use.
   - `CLOSED`: Explain that the card is no longer active. Check whether another active card exists or offer replacement; do not attempt to reactivate it.
   - `PENDING`: It is not activated. Follow the activation requirements: verified owner, physical card present, linked account `OPEN`, card not expired, matching last four/expiration/CVV, and a compliant customer-selected four-digit PIN. Select the activation tool by `issue_reason`: 8291 for `new_account`/`first_card`; 8292 for `lost`/`stolen`/`fraud`; 8293 for `expired`/`damaged`/`upgrade`/`bank_reissue`.
   - `ACTIVE`: Continue to account status.
   - Any missing or unknown status: do not infer a cause; obtain corrected card data or explain the diagnosis is incomplete.

2. **Linked checking-account status second**
   - If the linked account is not `OPEN`, do not reveal specific restriction details for `SUSPENDED` or `RESTRICTED` accounts. Tell the customer exactly: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
   - Only an `OPEN` linked account proceeds to the security checks.

3. **Fraud alert third**
   - If `fraud_alert_active` is true and `alert_source` is `customer_initiated`, ask the customer to verify recent transactions. Clear only after identity verification is logged, the customer confirms the transactions are legitimate, ownership is confirmed, and the customer agrees to clearing. Unlock and call `clear_debit_card_fraud_alert_4892` with `reason: "customer_verified"`. Document why it was cleared.
   - If `fraud_alert_active` is true and `alert_source` is `bank_initiated`, never attempt to clear it. Tell the customer: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then call `transfer_to_human_agents` with `reason: "fraud_or_security_concern"` and a concise summary.
   - If the alert source is missing or unrecognized, do not clear it; escalate for security review when an active alert cannot be safely classified.

4. **Velocity block fourth**
   - If `velocity_blocked` is true, say: “Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?”
   - Lift it early only after verification is logged, ownership is confirmed, the customer wants it lifted and provides a reasonable explanation for the activity. Call `clear_debit_card_fraud_alert_4892` with `reason: "velocity_clear"`, then document why it was cleared.
   - If no block exists, explain that the reviewed CODE 05 checks did not identify a card-status, account-status, fraud-alert, or velocity-block cause. Capture the card last four, merchant type, timestamp, and exact error for follow-up; avoid claiming the transaction will succeed on retry.

### 4. Multiple cards and closure

- Report each card separately by last four digits; do not expose full card numbers or unrelated card history.
- A bank-initiated alert on one card requires immediate security escalation for that situation. Do not use a customer-initiated-alert or velocity-clear action as a substitute.
- For persistent or unexplained declines, capture screenshots, timestamps, the workflow/merchants, device/browser/app version, and repeated results for escalation with logs.
- Confirm only actions that actually returned successfully. If a tool returns an error, do not claim the alert/block was removed; explain the next safe route or transfer where appropriate.

## Helper script

Run `scripts/evaluate_code05.py` with JSON on stdin after retrieving the records:

```json
{
  "user_id": "verified-user-id",
  "accounts": [{"account_id": "checking-id", "account_type": "checking", "status": "OPEN"}],
  "cards": [{"card_id": "card-id", "account_id": "checking-id", "user_id": "verified-user-id", "card_number_last_4": "1234", "status": "ACTIVE", "fraud_alert_active": false, "velocity_blocked": false}]
}
```

It emits JSON with `valid`, `errors`, `ignored_cards`, and a `cards` array. Each card result contains the ordered checks completed, `outcome`, `next_step`, and whether the outcome requires explicit customer confirmation or a transfer. Validate that `valid` is true, the number of analyzed records matches the relevant affected cards, and every `ACTIVE`/`OPEN` record has an alert and velocity conclusion before using the plan. The executor must still enforce the procedure above and must not treat the script output as authorization for a banking action.
