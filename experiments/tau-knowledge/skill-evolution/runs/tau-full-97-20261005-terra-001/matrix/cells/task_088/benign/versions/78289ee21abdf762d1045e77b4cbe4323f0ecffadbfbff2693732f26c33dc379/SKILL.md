---
name: debit-card-purchase-decline-diagnosis
description: Diagnose a declined debit-card purchase by retrieving linked checking accounts, debit cards, and transaction activity; apply the required card/account/security/balance/limit checks in order; and safely perform or recommend only eligible follow-up actions. Use when a customer reports a debit-card purchase decline, with or without a decline code.
---

# Debit-card purchase decline diagnosis

## Scope and safety

Use this Skill for a debit-card **purchase** decline. It supports investigation and customer guidance; it does not presume a specific decline cause merely because a purchase was declined.

- Use the customer profile resolved during the interaction. Never use a name alone as proof that the requester owns an account.
- Do not ask for a full card number, PIN, or CVV for diagnosis.
- Investigation may establish facts, but any state-changing card action requires the applicable identity, ownership, and status checks below. When identity verification is required, confirm two of date of birth, email, phone number, and address, then call `log_verification` with the full retrieved profile and current timestamp.
- Do not clear a bank-initiated fraud alert, reveal internal fraud/security codes, remove gambling/adult MCC blocks by phone, or promise that an authorization hold can be released by the bank.
- Do not make a card change when several cards could be the card used. Ask the customer to identify the card by last four digits; if they cannot, provide only non-sensitive diagnostic guidance.

## Runtime tool sequence

The specialized banking tools named below must first be unlocked with `unlock_discoverable_agent_tool`, then invoked through `call_discoverable_agent_tool` using a JSON-string `arguments` value.

1. Resolve a unique customer record using the supplied account identifier (name or email) and retain its `user_id`.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with `{"user_id":"<resolved user id>"}`.
   - Keep checking accounts and inspect `account_id`, `account_type`, `account_class`, `status`, `balance`, and `date_opened`.
   - If there is no checking account, explain that a debit card must be linked to a checking account; do not diagnose a savings account as a debit-card account.
3. For every relevant checking account, unlock and call `get_debit_cards_by_account_id_7823` with `{"account_id":"<checking account id>"}`.
   - Retain card ID, account ID, user ID, last four digits, status, issue reason, issued/expiration dates, daily limits, and any returned alert, restriction, PIN, or usage fields.
   - Confirm that a selected card's `user_id` matches the customer and its `account_id` matches the selected checking account before any action.
4. Unlock and call `get_bank_account_transactions_9173` for every plausible linked checking account.
   - Transactions are reverse chronological. Review both `posted` and `pending` entries, especially pending negative amounts, overdraft fees, recent purchases, and any record related to the reported merchant/amount.
   - A declined authorization may not appear in returned transaction history. Absence of a matching transaction is not proof that no decline occurred.
5. If the card or account remains ambiguous, ask only for useful non-secret corroboration: the card last four digits, approximate amount, merchant/store or city, approximate time, and any decline notification/code. Continue with read-only diagnosis where possible; do not perform a mutation until the target card is certain.

For deterministic calculations, normalize one candidate account, card, and its transactions and call the packaged helper:

```sh
python scripts/assess_decline.py < collected_decline_context.json
```

The helper is advisory only. Validate that its `missing_facts` list is resolved before treating a cause or an eligibility result as final.

## Required diagnostic order for an unknown or generic decline

Follow this order for each identified candidate card. State only the relevant customer-facing explanation, not internal security rationale.

1. **Card status**
   - `FROZEN`: offer unfreezing only after identity/ownership verification, confirmation that the linked checking account is `OPEN`, and customer consent. Use `unfreeze_debit_card_3893` with `card_id`; confirm that it is active.
   - `CLOSED`: explain the card is no longer active; check whether another active card exists or discuss a replacement through the applicable process.
   - `PENDING`: explain it has not yet been activated. Activation requires a pending, unexpired card, an open checking account, verified identity, physical-card possession, and matching last four/expiry/CVV. Select the activation tool strictly by `issue_reason`: `activate_debit_card_8291` for `new_account`/`first_card`, `activate_debit_card_8292` for `lost`/`stolen`/`fraud`, and `activate_debit_card_8293` for `expired`/`damaged`/`upgrade`/`bank_reissue`.
   - `ACTIVE`: continue.
2. **Linked checking-account status**
   - If not `OPEN`, do not transact on the card. For `SUSPENDED` or `RESTRICTED`, do not disclose the specific restriction. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert**
   - If `fraud_alert_active` is true and `alert_source` is `bank_initiated`, do not clear it. Tell the customer a security flag requires additional review and transfer to the security team using `transfer_to_human_agents` with reason `fraud_or_security_concern`.
   - If it is customer-initiated, first verify identity and have the customer confirm recent transactions are legitimate. Then unlock and call `clear_debit_card_fraud_alert_4892` with `{"card_id":"<card id>","reason":"customer_verified"}`. Document why it was cleared.
4. **Velocity block**
   - If `velocity_blocked` is true, explain the temporary security block normally lifts after 30 minutes. Clear early only after identity verification and a reasonable explanation for unusual activity: call `clear_debit_card_fraud_alert_4892` with `reason` `velocity_clear`, then document the reason.
5. **Balance and available-funds factors**
   - Compare the purchase amount with the current checking-account balance. If the posted balance is insufficient, offer adding/transferring funds or a smaller purchase.
   - If the posted balance appears sufficient, do not claim available funds are sufficient. Explain that pending debits and authorization holds can reduce the available amount. Identify pending debit totals from transaction history and ask about recent gas, hotel, rental-car, restaurant, or similar holds; holds may not appear in transactions.
   - If returned, use `overdraft_pos_enabled` only to explain whether POS overdraft coverage is enabled. Do not represent it as a guarantee that the purchase will be approved.
6. **Daily purchase limit and restrictions**
   - Compute remaining purchase capacity as `daily_purchase_limit - daily_purchase_used`; a purchase may be declined if its amount exceeds the remaining capacity. Use the helper calculation rather than rounding currency values.
   - Check returned restriction fields only when relevant: `restricted_mccs`, `international_enabled`, `online_enabled`, geographic regions, and daily transaction count/limit. Do not infer a restriction that was not returned.
   - A known Code 58 means the terminal is flagged: suggest a different register or merchant. A known Code 57 requires the applicable returned restriction. A known Code 61 is a daily amount limit; Code 65 requires waiting for the daily count reset. For a Light Green Account, do not alter parental controls without guardian authorization.
7. **Other known-code routes**
   - Code 19: immediate retry; after a second failure, wait 10–15 minutes. Codes 91/96: retry in a few minutes or 10–15 minutes if persistent; code 92: retry or use a different merchant.
   - Code 82: ask about physical damage. If damaged, discuss replacement; if not, review activity for suspicious transactions and recommend a freeze while replacement is considered.
   - Code 87: retry without cash back.
   - Codes 04, 07, 34, and 59: never disclose the code or fraud reason. Use the prescribed branch/in-person wording and escalate if needed.
   - Codes 41/43, or a card reported lost/stolen, are security-sensitive. A reported lost/stolen card cannot be reactivated. For a customer who says they did not report a stolen card, transfer to security rather than resolving it in chat.
   - Codes 55/75 with `pin_locked=true` require the separate PIN-lock fraud-risk assessment before any unlock. Check automatic escalation triggers, assess all relevant cards, do not reveal the scoring calculations, and follow the resulting verification/escalation outcome. A `security_hold` cannot be unlocked by chat.

## Temporary purchase-limit increase

Offer this only if the customer asks for it or agrees after a limit diagnosis. It is a 24-hour change, not a guarantee against a merchant or third-party ATM limit.

Before requesting it, verify all of the following: the linked checking account is `OPEN`; it is at least 60 days old; there are no `overdraft_fee` transactions in the preceding 30 days; the chosen debit card is `ACTIVE`; the requested new daily purchase limit is no more than 150% of its current limit; and no temporary increase was already granted for that card in the past 24 hours. The helper identifies the first five items when the supplied data supports them; use available card/history information to establish the frequency rule.

After identity/ownership verification and customer consent, unlock and call `request_temporary_debit_card_limit_increase_8374` with:

```json
{"card_id":"<identified card id>","limit_type":"purchase","new_limit":<requested total daily limit>}
```

The requested total daily limit must accommodate both amount already used and the intended purchase, and must remain within the 150% maximum. Explain the 24-hour expiration before submitting. If any requirement is unknown or fails, do not submit; explain the specific known blocker or collect the missing fact.

## Completion and response

Report the facts found (selected card ending, linked account state, relevant pending activity, current/remaining daily limit, and any action taken), avoiding full account/card numbers and internal fraud details. Give a concrete next step: retry, wait, add funds, use another permitted payment method, activate/unfreeze after verification, request an eligible limit increase, replacement path, or security transfer. Never say a purchase will succeed until a new authorization is actually approved.

## Helper input/output contract

`scripts/assess_decline.py` reads one JSON object from stdin and emits one JSON object to stdout.

Required input fields: `current_time` (ISO-like timestamp), `account` object, `card` object, and `transactions` array. Optional `attempted_amount` is the reported purchase amount. Optional `limit_request` has `limit_type` (`purchase` or `atm`), `new_limit`, and `temporary_increase_in_last_24h` (`true`, `false`, or `null`). Dates accepted from account/card/transactions are `MM/DD/YYYY`; timestamps may include a time and timezone.

The output contains normalized calculations, pending debit total, recent overdraft-fee count, an ordered `findings` list, `temporary_limit_assessment`, `missing_facts`, and `validation_errors`. A nonempty `validation_errors` list means the executor must correct or omit malformed data and must not rely on associated calculations.
