---
name: debit-card-purchase-decline-diagnosis
description: Safely investigate a declined debit-card purchase by retrieving checking accounts, cards, and transaction activity; distinguish available funds from posted balance; handle chip/security concerns; and escalate suspected fraud. Use when a customer reports a debit-card purchase decline, with or without a decline code.
---

# Debit-card purchase decline diagnosis

## Scope and safeguards

Use this Skill for a debit-card **purchase** decline. A decline alone does not establish its cause.

- Resolve a unique customer record, but do not treat a name or email alone as identity verification.
- Never request a full card number, PIN, or CVV for diagnosis.
- Do not change, freeze, unfreeze, close, replace, activate, clear an alert, or request a limit increase unless the applicable verification, ownership, status, and consent requirements are met.
- If the customer has not identified the used card, perform read-only investigation across plausible checking accounts, but do not attribute the decline to one card or mutate any card.
- Do not clear bank-initiated fraud alerts, disclose internal fraud codes or rationale, or remove gambling/adult MCC restrictions in chat.
- Do not promise that a retry, released hold, or new authorization will succeed.

## Investigation sequence

Specialized banking tools must be unlocked with `unlock_discoverable_agent_tool` before use through `call_discoverable_agent_tool`; the nested `arguments` parameter is a JSON string.

1. Resolve the supplied customer name or email to one customer and retain `user_id`.
2. Call `get_all_user_accounts_by_user_id_3847` with `{"user_id":"<user_id>"}`. Retain every checking account's ID, type, class, status, balance, and opening date.
3. For **every** discovered checking account when the card is unknown, call `get_debit_cards_by_account_id_7823` with `{"account_id":"<account_id>"}`. Retain card ID, linked account/user ID, last four, status, issue reason, dates, limits, usage, and returned security/restriction fields.
4. For every plausible checking account, call `get_bank_account_transactions_9173` with `{"account_id":"<account_id>"}`. Review posted and pending activity, including pending debits, deposits with holds, overdraft fees, and transactions matching the reported merchant or amount. A declined authorization can be absent from history.
5. If needed, ask for the card last four, merchant/city, approximate time, amount, and any decline notification/code. These are corroborating details, not a substitute for card identification.

For repeatable arithmetic, run:

```sh
python scripts/assess_decline.py < collected_decline_context.json
```

The helper is advisory. Do not treat incomplete data or an output with `validation_errors` as a final diagnosis.

## Unknown-card and held-funds communication

When the customer cannot identify the card, say explicitly that the card remains unknown. Use wording such as:

> “I still have not identified which card was used for the Portland purchase, so I cannot confirm this is the definitive cause of that decline.”

If a pending deposit has a hold, distinguish posted balance from usable funds precisely. State the held amount, currently available portion, and stated release date when returned by activity. For example, explain that funds subject to a hold are **not currently spendable**, even if they appear in a displayed balance. Do not claim the hold definitely caused a decline on an unidentified card.

## Diagnostic order for an identified or candidate card

1. **Card status.** `FROZEN`: offer unfreeze only after verified identity/ownership, open linked account, and consent. `CLOSED`: explain it cannot be used; consider another active card or replacement path. `PENDING`: follow activation requirements. `ACTIVE`: continue.
2. **Account status.** If not `OPEN`, do not transact. For `SUSPENDED` or `RESTRICTED`, say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert.** For a bank-initiated alert, do not clear it; tell the customer additional security review is required and transfer to security. A customer-initiated alert may be cleared only after identity verification and confirmation that reviewed activity is legitimate.
4. **Velocity block.** It normally expires after 30 minutes. Clear early only after identity verification and a reasonable explanation for unusual activity.
5. **Funds.** Compare purchase amount with balance, but never infer available funds from posted balance alone. Pending debits and authorization holds reduce availability. If balance is truly insufficient, offer funding, transfer, or a smaller purchase. Explain POS overdraft only if its returned setting supports the statement.
6. **Limits and restrictions.** Calculate remaining purchase capacity exactly as `daily_purchase_limit - daily_purchase_used`. Check only returned restriction fields: MCC, international/online settings, geographic rules, and transaction count. Do not modify parental controls without guardian authorization.
7. **Known codes.** Code 19: retry immediately, then wait 10–15 minutes after a second failure. Codes 91/96: retry shortly or wait 10–15 minutes if persistent. Code 92: retry or try a different merchant. Code 58: suggest another terminal/merchant. Code 87: retry without cash back. Never disclose sensitive codes 04, 07, 34, or 59.

## Chip/CVV mismatch and suspicious activity

For Code 82 or a reported chip issue, ask whether the physical card is damaged.

- If damaged, explain that replacement may be appropriate; do not order one before required checks and consent.
- If the card appears undamaged, say that recent activity must be reviewed because an undamaged chip problem can indicate counterfeit use. Review the linked account's recent activity before recommending replacement.
- If a transaction is suspicious, ask the customer whether they recognize its merchant, date, amount, and location.
- If the customer denies a suspicious in-person transaction, do **not** clear alerts, unfreeze a card, close/reissue, order a replacement, or file a card action in chat unless separately authorized by the governing workflow. Immediately recommend protective freezing and transfer to security. The customer-facing response must explicitly include a freeze/block recommendation, for example:

> “Because you confirmed this transaction was not yours, I recommend that you freeze the affected debit card now (temporarily block it) while our security team reviews it and determines the replacement steps. I’ll transfer you to our security team immediately.”

Then call `transfer_to_human_agents` with reason `fraud_or_security_concern`. Its summary must record the suspicious transaction's amount and location and the confirmed customer denial. This recommendation is not itself permission to execute a freeze.

Lost/stolen cards and Codes 41/43 are security-sensitive; do not reactivate a reported lost/stolen card. A customer who denies reporting a stolen card must be transferred to security. PIN-locked Codes 55/75 require the separate fraud-risk assessment before any unlock; a `security_hold` cannot be unlocked in chat.

## State-changing actions

Before any state-changing action, verify identity by confirming two of date of birth, email, phone number, and address against the retrieved profile. Obtain current time and call `log_verification` with the complete retrieved profile and timestamp. Confirm card ownership (`user_id`) and linked account ID/status.

- Unfreeze only an eligible `FROZEN` card using `unfreeze_debit_card_3893` after consent.
- Clear customer-initiated alert or velocity block only under the respective verified conditions using `clear_debit_card_fraud_alert_4892` and document why.
- Activation requires a verified customer, physical pending unexpired card, open account, matching card details, and the issue-reason-specific activation tool.
- A temporary purchase-limit increase requires: OPEN account, account age at least 60 days, no overdraft fee in prior 30 days, ACTIVE card, no increase in prior 24 hours, customer consent, and a requested total limit no greater than 150% of current limit. It lasts 24 hours. Call `request_temporary_debit_card_limit_increase_8374` only after all checks pass.

## Completion

Report only relevant facts: selected card ending, account state, available-funds factors, pending activity, daily capacity, and action/transfer. Give a concrete next step without guaranteeing approval.

## Helper I/O

`scripts/assess_decline.py` reads one JSON object from stdin and writes one JSON object to stdout. Input requires `current_time`, `account` object, `card` object, and `transactions` array; `attempted_amount` and `limit_request` are optional. Dates may be `MM/DD/YYYY`, `YYYY-MM-DD`, or ISO-like timestamps. `limit_request`, if supplied, contains `limit_type`, `new_limit`, and `temporary_increase_in_last_24h` (`true`, `false`, or `null`). Output provides pending-debit totals, purchase capacity, 30-day overdraft count, ordered findings, temporary-limit eligibility, missing facts, and validation errors.
