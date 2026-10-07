---
name: debit-card-purchase-decline-diagnosis
description: Diagnose a declined debit-card purchase when the customer has a known or unknown decline code. Use for a checking-account-linked debit card decline, especially an in-store chip, tap, or signature purchase. It guides safe read-only investigation of account, card, and transaction data; generic decline sequencing; balance and limit analysis; and gated security or card actions.
---

# Debit-card purchase decline diagnosis

Use this Skill to investigate a debit-card purchase decline without guessing the cause or exposing sensitive account information before verification. It is designed for a declined purchase, not for filing a dispute or ordering/replacing a card unless the investigation establishes that follow-up is needed.

## Required inputs to collect

1. Identify the customer using an unambiguous name or email and obtain their `user_id` with the applicable user lookup tool.
2. Ask for the approximate declined amount, whether the physical card is in the customer's possession, whether the purchase was chip/PIN, chip/signature, tap, or online, and any decline code shown by the merchant or app.
3. Ask for the last four digits of the card when more than one current card may exist. Never request a full card number, PIN, CVV, or online-banking password.
4. For an inserted-chip purchase, separately ask whether the chip, stripe, or card has been damaged or failed at other terminals. Do not infer an answer from a response that only says the card was inserted.
5. Before revealing account/card details or taking a card action, complete standard identity verification by confirming two of date of birth, email, phone number, and address, then call `log_verification` with all required fields and the current timestamp. A name, possession of a card, or knowledge of a purchase is not identity verification.

A decline code is useful but is not required to begin a read-only investigation. If no code is known, ask the customer to check their app or ask the merchant for the exact code/message while the investigation proceeds.

## Read-only investigation workflow

Use only the customer's resolved `user_id` and real runtime lookup results. Do not choose an account or card by invented identifiers.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the customer `user_id`.
   - Identify all checking accounts and retain account ID, account type/class, status, balance, and date opened.
   - Savings accounts cannot be the debit-card-linked account.
   - If no checking account is found, explain that a debit card requires a checking account; do not diagnose a card against a savings account.
2. For **each relevant checking account**, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
   - Match the card by `card_id` or customer-provided last four digits. If no match is possible, ask for the last four digits rather than identifying a card to the customer from a list.
   - Retain all cards, not just active cards: a newer replacement or reissued card can explain an old-card decline.
   - Inspect the selected card's `status`, `issue_reason`, `expiration_date`, `date_issued`, `daily_purchase_limit`, and returned security/usage fields when present.
3. Unlock and call `get_bank_account_transactions_9173` for the linked checking account. Review posted and pending activity, especially recent negative debit-card purchases, fees, and same-day activity. Transaction results are reverse chronological; do not assume they include authorization holds.
4. Optionally pass normalized lookup data to `scripts/assess_purchase_decline.py` to calculate pending-debit totals, a conservative limit screen, and missing evidence. The script is decision support only; lookup results and customer statements remain authoritative.

### Runnable script interface

Run from the package runtime by sending one JSON object on stdin:

```json
{
  "purchase_amount": "amount in USD",
  "today": "YYYY-MM-DD or timestamp",
  "reported_decline_code": "optional code without CODE prefix",
  "card_last4": "optional four digits",
  "card_id": "optional card identifier",
  "identity_verified": false,
  "accounts": [{"account_id": "...", "account_type": "checking", "status": "OPEN", "balance": "0", "date_opened": "MM/DD/YYYY"}],
  "cards_by_account": {"account-id": [{"card_id": "...", "status": "ACTIVE", "card_number_last_4": "0000", "daily_purchase_limit": "0"}]},
  "transactions_by_account": {"account-id": [{"date": "MM/DD/YYYY", "amount": "-0", "type": "debit_card_purchase", "status": "pending"}]}
}
```

It emits JSON:

- `validation_errors`: malformed or missing required analysis inputs; fix these before relying on findings.
- `candidate_cards`: cards matching supplied card selectors.
- `findings`: nonfinal observations about status, pending debits, balance screening, purchase-limit screening, security indicators, and code-specific retry guidance.
- `missing_data`: questions/lookup fields that prevent a conclusion.
- `recommended_next_steps`: ordered diagnostic or eligibility checks.
- `action_gates`: conditions that must be satisfied before a sensitive action.

The script accepts omitted optional card fields. Missing information is reported as unknown, never treated as false or zero. Validate that the selected card belongs to the selected checking account, amounts are positive USD values, and dates are parseable before acting on calculations.

## Diagnosis and response logic

### No code or generic Code 05

For a no-code decline, do not state a definite cause. Once the intended card is identified, follow this order:

1. **Card status.**
   - `FROZEN`: ask whether the customer wants it unfrozen; only unfreeze after verified ownership, confirmation it is the customer's card, and confirmation that its linked checking account is OPEN.
   - `CLOSED`: explain the card is no longer active. Check for an active or pending replacement card.
   - `PENDING`: the card is not active; follow the activation procedure rather than treating it as a purchase decline.
   - `ACTIVE`: continue.
2. **Linked checking-account status.** If the account is not OPEN, do not attempt a card transaction action. For `SUSPENDED` or `RESTRICTED`, do not disclose specific restriction details. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert.** Inspect `fraud_alert_active` and `alert_source` only if returned.
   - A customer-initiated alert can be cleared only after identity verification and the customer confirms recent activity is legitimate. Unlock `clear_debit_card_fraud_alert_4892` and use reason `customer_verified`.
   - A bank-initiated alert must not be cleared. Transfer to the security team using `transfer_to_human_agents` with `fraud_or_security_concern` and a concise, non-sensitive summary.
4. **Velocity block.** If `velocity_blocked` is true, explain that the temporary block normally lifts after 30 minutes. It may be cleared early only after identity verification and a reasonable explanation for the activity. Use `clear_debit_card_fraud_alert_4892` with reason `velocity_clear` after unlocking it.

Do not clear an alert or block merely because the customer says the purchase was legitimate. Document the verified identity and reason for a permitted clearance.

### Funds and pending activity

For Code 51 or whenever the balance may explain a no-code decline:

1. Compare the purchase amount with the linked checking account's displayed balance.
2. Review pending negative transactions. They reduce available funds, but authorization holds may not appear in transaction history.
3. If the displayed balance appears sufficient, ask about recent gas-station, hotel, rental-car, restaurant, or other authorization holds. Explain that posted balance is not necessarily available balance.
4. When returned by account lookup, inspect `overdraft_pos_enabled`. If it is false, explain that the account is not opted into POS overdraft coverage and offer to explain options; do not imply an opt-in was changed.
5. If funds appear genuinely insufficient, state the available balance only after verification and offer a transfer from another eligible customer account or a smaller transaction. A transfer requires customer authorization, positive amount, distinct account IDs, both accounts OPEN/ACTIVE, and sufficient source funds. Use the normal transfer tool only after those checks.

### Purchase-limit screen and temporary increase

For Code 61 or when the declined purchase may exceed the daily purchase limit:

1. Use card-provided `daily_purchase_limit` and `daily_purchase_used` if present. If usage is absent, same-day debit-card transactions can be a conservative clue but are not a definitive replacement for card-provided usage.
2. Calculate remaining purchase capacity as `limit - used`; do not report a negative remaining amount as spendable.
3. A temporary purchase-limit increase can be considered only if all of the following are known: linked checking account is OPEN, account age is at least 60 days, no overdraft fee appears in the last 30 days, and the selected card is ACTIVE.
4. The requested temporary limit cannot exceed 150% of the current limit, lasts 24 hours, and only one increase is allowed per card per 24 hours. Check the frequency restriction before calling the tool; if it cannot be checked, do not represent the customer as eligible.
5. After verified customer authorization, unlock and call `request_temporary_debit_card_limit_increase_8374` with the real `card_id`, `limit_type: "purchase"`, and an eligible `new_limit`. Explain the 24-hour expiry. A limit increase cannot override merchant/terminal restrictions or insufficient available funds.

### Code-specific paths relevant to a purchase

- **Code 19:** ask the merchant to retry immediately. If the retry also returns Code 19, treat it as a temporary system issue and suggest waiting 10–15 minutes.
- **Code 91 or 96:** advise retrying in a few minutes; if it persists, wait 10–15 minutes and use another payment method if available.
- **Code 92:** explain it is a temporary routing issue, retry, and if persistent try another merchant/terminal.
- **Code 57:** inspect returned merchant-category, online, international, and account-class restrictions. Do not remove gambling/adult MCC blocks by phone; those changes must be made by the customer in the app or in person. Do not modify parental controls without guardian authorization.
- **Code 58:** the terminal itself is flagged. Suggest another register or merchant. If it happens at multiple unrelated terminals, return to the generic Code 05 sequence.
- **Code 82 or reported chip/stripe damage:** ask about physical damage. If damaged, follow the replacement process. If undamaged, treat possible cloning as a security concern: review transactions and recommend a freeze while an appropriate replacement/security workflow is pursued.
- **Code 54:** check expiration and whether an `expired` replacement is pending or active; direct the customer to the replacement/activation path as appropriate.
- **Code 14:** compare the customer’s last four digits with cards on file; a closed old card with a newer active card indicates the saved/entered old number may be in use.

Do not apply PIN-lock procedures solely because a chip card was inserted. Code 55 or 75 with `pin_locked = TRUE` requires the separate PIN Lock Investigation Protocol, including its fraud-risk assessment, before any unlock.

## Card actions and escalation safeguards

- **Freeze:** only for a verified card owner and only when the card is ACTIVE. Explain that new and recurring transactions decline while pending authorized transactions may still process. Unlock/call `freeze_debit_card_3892` only after those checks.
- **Unfreeze:** only for a verified owner, a FROZEN card, and OPEN linked checking account. Unlock/call `unfreeze_debit_card_3893`; confirm that it is active immediately.
- Do not close, replace, activate, transfer money, change restrictions, or request a limit increase unless the customer asks for that result and all applicable prerequisites are met.
- For bank-initiated fraud alerts, suspicious cloned-card evidence, or a customer who denies suspicious activity, use `transfer_to_human_agents` with `fraud_or_security_concern`. Do not disclose internal fraud codes or detailed security rationale.

## Completion standard

Give a concise, factual outcome: what was checked, the confirmed cause or remaining uncertainty, safe next action, and retry timing if applicable. Do not claim a card was fixed, a limit was changed, or a transfer was completed until the normal banking tool reports success. If data is incomplete, say exactly what is needed (for example, card last four digits, a decline code, card status, or pending activity) and continue only with supported conclusions.
