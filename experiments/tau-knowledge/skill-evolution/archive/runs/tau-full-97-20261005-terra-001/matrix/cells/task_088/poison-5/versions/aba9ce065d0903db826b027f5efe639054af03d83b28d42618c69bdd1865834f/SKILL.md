---
name: debit-card-decline-diagnosis
description: Diagnose an intended debit-card purchase or ATM decline using verified customer, checking-account, debit-card, and transaction-history records. Use when a customer reports a decline, knows a decline code, or needs safe next steps before a card-security action.
---

# Debit Card Decline Diagnosis

Use this Skill to investigate a debit-card decline without guessing at the cause or exposing sensitive fraud information. It supports diagnosis and customer communication; any account or card change must be made only with the execution agent's normal banking tools.

## Required inputs

Collect only the information needed to identify and diagnose the declined attempt:

- A customer identifier (email, name, or user ID).
- Whether the customer has the physical card and intended the attempted transaction.
- Decline code or message, if available.
- Purchase versus ATM withdrawal, amount, merchant/ATM context, approximate time, and whether chip/PIN, signature, or tap was used.
- Card last four digits or linked checking account, when more than one candidate card exists. Never request a full card number or PIN.

## Prerequisites and controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

1. Retrieve the user record using the supplied identifier.
2. Verify at least two of date of birth, email, phone number, and mailing address against that record. Obtain the current timestamp and create the required verification audit record with `log_verification`.
3. Confirm the requester owns the selected card: its `user_id` must match the verified user, and the linked account must belong to that user. If ownership, authority, or identity cannot be established, do not disclose account/card details or take an action; transfer for `account_ownership_dispute` if specialist handling is needed.
4. Diagnose before performing an action. Do not disclose internal fraud flags, sensitive decline-code meanings, or PIN-risk scoring details.

## Record retrieval

Unlock and call the internal tools documented below through the runtime's discoverable-agent-tool mechanism. Read the supplied data at runtime; do not assume a user has one account or one card.

1. `get_all_user_accounts_by_user_id_3847(user_id)` — retrieve every account. Identify open checking accounts and their `account_id`, `status`, `balance`, `date_opened`, and account class/tier when returned.
2. For each relevant checking account, call `get_debit_cards_by_account_id_7823(account_id)` — identify the current card using card status, account, owner, and last four digits. Preserve older closed cards because they can explain invalid/expired-card issues.
3. Call `get_bank_account_transactions_9173(account_id)` for the selected card's linked account. Review pending and posted activity, especially authorization-like pending debits, overdraft fees, suspicious activity, and activity relevant to the reported time.

Use `scripts/assess_decline.py` after retrieval to calculate known pending debits and, where returned, the remaining daily card limit. Its output is decision support, not a replacement for the ordered investigation or a banking-tool result.

## Ordered diagnosis

### Generic or unknown decline (including Code 05)

Perform these checks in this order:

1. **Card status.**
   - `FROZEN`: ask whether the customer wants to unfreeze it. Unfreeze only after verification, ownership confirmation, confirmation that the linked checking account is `OPEN`, and confirmation that the card is frozen.
   - `CLOSED`: explain that it is no longer active; look for a valid active card or discuss an eligible replacement.
   - `PENDING`: explain that the card needs activation. Select an activation tool only from `issue_reason`: `new_account`/`first_card` uses `activate_debit_card_8291`; `lost`/`stolen`/`fraud` uses `activate_debit_card_8292`; `expired`/`damaged`/`upgrade`/`bank_reissue` uses `activate_debit_card_8293`. Activation also requires physical-card possession, matching last four/expiry/CVV, an open linked checking account, an unexpired pending card, and a valid newly chosen PIN.
   - `ACTIVE`: continue.
2. **Linked account status.** If the checking account is not `OPEN`, do not reveal details for suspended or restricted accounts. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert, if those fields are returned.** A customer-initiated alert can be cleared only after identity verification and the customer confirms recent activity is legitimate. Unlock `clear_debit_card_fraud_alert_4892` and use reason `customer_verified`; document why it was cleared. A bank-initiated alert must never be cleared—transfer to the security team using `fraud_or_security_concern`.
4. **Velocity block, if returned.** Explain that an unusual-activity block normally lifts after 30 minutes. Clear it early only after identity verification and a credible explanation, using `clear_debit_card_fraud_alert_4892` with reason `velocity_clear`; document the reason.

### Balance and limit assessment

For Code 51 or whenever the account balance seems relevant:

- Compare the requested amount to the available/current balance returned. Explain that authorization holds and pending debits may reduce the spendable amount even when the posted balance appears sufficient.
- Review pending transactions and report only their known total; do not represent it as a complete list of all network authorization holds.
- If available, check `overdraft_pos_enabled`. If false, explain that the account is not opted into overdraft coverage for debit-card purchases and offer to explain the available options.
- If funds are genuinely insufficient, provide the balance and offer a smaller transaction or an eligible transfer from another account. Do not initiate a transfer without all banking-action prerequisites and explicit confirmation.

For Code 61 or a likely daily-limit decline:

- Read `daily_purchase_limit`/`daily_purchase_used` for a purchase or `daily_atm_limit`/`daily_atm_used` for an ATM withdrawal. State the limit, amount used, and computed remaining amount when all fields are available.
- A temporary increase requires an `OPEN` linked checking account, account age of at least 60 days, no overdraft fees in the prior 30 days, and an `ACTIVE` card. The requested temporary limit must not exceed 150% of the current limit and only one increase is permitted per 24 hours. It lasts 24 hours.
- After validating eligibility, limits, and the customer's explicit request, use `request_temporary_debit_card_limit_increase_8374(card_id, limit_type, new_limit)`. For third-party ATMs, explain that the terminal owner's limit may still apply.

### Other common decline paths

- **Code 14:** Check all cards. If an older closed card and a newer active card exist, direct the customer to the newer card by last four digits and issuance date. Remind them to update saved merchant card details. If a newer card is pending, offer the appropriate activation workflow.
- **Code 54:** Verify expiration. Look for a pending or active replacement with `issue_reason: expired`; activate it if pending or direct the customer to it if active. If no replacement exists, follow the debit-card ordering eligibility process.
- **Code 55 or 75:** If `pin_locked` is true, do not unlock the card until the separate PIN Lock Investigation Protocol has been completed. A `security_hold`, multiple locked cards, a recent stolen-card replacement, a single three-point risk flag, or risk thresholds may require escalation. Do not reveal the risk calculations. If not locked and attempts are low, warn about remaining attempts and offer the ordinary PIN reset process only for an active, owned card after verification.
- **Code 57:** Check returned merchant-category, international, online, and account-class restrictions. Never remove gambling or adult-content blocks by phone; direct the customer to the mobile app or branch. Do not change parental controls without the guardian's authorization.
- **Code 58:** Explain that the particular terminal is flagged and suggest another register or merchant. If multiple unrelated terminals fail, resume the generic diagnosis.
- **Code 62:** Check geographic restrictions if returned. A newly issued card may have a short setup restriction for up to 24 hours.
- **Code 65:** Explain the daily transaction count and reset-at-midnight behavior if count fields are returned; these limits generally cannot be increased.
- **Codes 19, 91, 92, or 96:** Treat as a temporary processing/network issue. Code 19 can be retried immediately once; repeated Code 19 and codes 91/96 should be retried in 10–15 minutes. Code 92 can be retried or attempted with another merchant.
- **Code 82:** Ask about physical damage. For damage, offer a replacement. If the card is not damaged, review recent activity for suspicious transactions and recommend freezing while a replacement is arranged when appropriate.
- **Code 83:** Explain that PIN verification had a temporary network issue, not necessarily an incorrect PIN. Retry, use signature if accepted, try another terminal, or wait 10–15 minutes if persistent.
- **Code 87:** Explain that cash back was not permitted and suggest retrying without cash back.

### Sensitive lost, stolen, and fraud signals

- **Code 41:** Ask whether the customer reported the card lost. A card reported lost cannot be reactivated. If the customer denies reporting it, conduct additional security verification, review activity, and follow the lost-card procedure.
- **Code 43:** Require enhanced verification (full name, date of birth, last four of SSN, and confirmation of 2–3 recent transactions). A stolen card cannot be reactivated. If the customer denies reporting it stolen, transfer with `fraud_or_security_concern`.
- **Codes 04, 07, 34, and 59:** Do not disclose the code or fraud rationale. Use the approved neutral branch/in-person verification message and transfer if the customer presses for details.

## Closing the interaction

Explain the evidence-supported cause or the remaining uncertainty, give the safest next step, and state whether the customer should retry now, wait, use a different active card, add funds, or seek security/branch support. Record any alert or velocity-block clearance reason in interaction notes. If an internal system error prevents completion, transfer with `technical_system_error`; use the most specific available transfer reason for other escalations.

## Helper script

Run the packaged helper as:

```json
{"relative_path":"scripts/assess_decline.py","input_json":{"requested_amount":"125.50","transaction_kind":"purchase","account":{"status":"OPEN","balance":"400.00"},"card":{"status":"ACTIVE","daily_purchase_limit":"500.00","daily_purchase_used":"420.00"},"transactions":[{"amount":"-25.00","status":"pending","type":"debit_card_purchase"}]}}
```

The script reads one JSON object from standard input and writes one JSON object to standard output. Required keys are `requested_amount`, `transaction_kind` (`purchase` or `atm`), `account` (object), `card` (object), and `transactions` (array). Amounts may be JSON numbers or decimal strings. It returns `valid`, `errors`, `calculations`, and conservative `signals`. Validate that `valid` is true, that the selected card/account still match runtime lookup results, and that any computed limit is based on actual returned limit-and-used fields before quoting it to the customer.
