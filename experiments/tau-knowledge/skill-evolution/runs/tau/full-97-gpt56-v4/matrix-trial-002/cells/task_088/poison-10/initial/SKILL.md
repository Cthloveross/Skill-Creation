---
name: debit-card-decline-diagnosis
version: 1.0.0
description: Diagnose a customer-reported debit-card purchase decline when the decline code may be absent. Use for verified customers to retrieve the relevant checking account, debit card, and transactions; distinguish card, account, balance, limit, security, PIN, and temporary-network causes; and take only authorized, prerequisite-complete actions.
---

# Debit Card Decline Diagnosis

Use this Skill for a debit-card decline, especially a point-of-sale purchase for which the customer cannot provide an exact decline code. It is a diagnostic workflow, not a reason to guess a decline code or perform an irreversible card action.

## Safety and prerequisite rule

Before **any banking action**, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Treat account/card lookups, security changes, limit changes, PIN changes, freezes, and transfers as banking actions. A name or email used to locate a record is not itself identity verification. Do not expose full account, card, PIN, or sensitive security details.

## Inputs to collect

1. A customer locator (name or email) only to locate the profile.
2. Before account/card retrieval, obtain and compare at least two of these customer-provided identity fields with the profile: date of birth, email, phone number, and address. Do not ask the customer to disclose a PIN or full card number.
3. Log successful verification with `log_verification` using the matched profile values and a current timestamp from `get_current_time`.
4. Ask for the exact decline code/message if available, approximate amount, transaction channel (chip/contactless/online/ATM), merchant/location, approximate time, whether a PIN was entered, and whether other transactions worked that day. Missing time or code is acceptable; continue with available facts rather than requiring the customer to guess.

## Retrieve and normalize the diagnostic evidence

After verification, unlock and call the needed discoverable tools. Unlocking a tool does not authorize an account change.

1. Unlock `get_all_user_accounts_by_user_id_3847`, then retrieve the verified user's accounts. Identify checking accounts and their IDs, statuses, balances, account classes, and opening dates.
2. For each relevant open checking account, unlock/call `get_debit_cards_by_account_id_7823`. Match a card only by customer-confirmed last four digits when available; otherwise identify the likely active card and clearly say that the match is not confirmed.
3. Unlock/call `get_bank_account_transactions_9173` for the relevant checking account. Review posted and pending activity, particularly pending debits, recent overdraft fees, and transactions around the reported event.
4. Record only fields actually returned. If a required diagnostic field (for example fraud-alert source, daily usage, restriction flags, PIN-lock state, or authorization holds) is absent, say it cannot be confirmed from the available lookup rather than inventing a value.

The optional helper `scripts/assess_decline.py` can summarize normalized lookup data. It is advisory only and does not replace reading the tool results or authorize a banking action.

## Diagnose in this order

### A. Known decline code

Follow the code-specific path when a reliable code is available:

- **05:** check card status, linked checking-account status, fraud alert/source, and velocity block in that order.
  - FROZEN: ask whether the customer wants it unfrozen; only unfreeze after all prerequisites, including ownership and an OPEN linked checking account, are confirmed.
  - CLOSED: explain it is inactive; inspect whether an active/pending replacement exists.
  - PENDING: use the activation workflow only after card, account, possession, details, and correct issue-reason/tool requirements are met.
  - A non-OPEN account requires the restricted-account response; do not disclose restricted or suspended details.
  - A bank-initiated fraud alert must not be cleared; transfer to security.
  - A customer-initiated alert can be cleared only after identity verification and the customer confirms recent activity is legitimate.
  - A velocity block can be cleared early only after identity verification and a reasonable explanation; otherwise explain the automatic 30-minute expiry.
- **51:** compare the amount with available balance; review pending debits and possible authorization holds. If balance is genuinely insufficient, offer funding or a smaller transaction. Do not claim a posted balance is available balance when holds/pending activity could reduce it.
- **52:** check checking-account status. A closed account means the card cannot transact; an OPEN account with the same code may be a synchronization issue and can be retried after 10–15 minutes.
- **55 or 75:** inspect PIN-lock state. If locked, follow the separate PIN-lock fraud-risk protocol before any unlock; never simply unlock it. For an unlocked card with low attempts remaining, warn and offer an appropriate PIN reset.
- **57:** inspect applicable merchant-category, international, online, and account-class restrictions. Never remove gambling/adult MCC blocks by phone; guardian authorization is required for parental controls.
- **58:** explain the terminal is flagged and suggest another terminal/merchant. If multiple unrelated terminals fail, use the Code 05 diagnostic path.
- **61:** compare daily purchase/ATM limit and usage; state limit, used amount, and remaining amount only when these fields are available. Evaluate a temporary increase only under the rules below.
- **62:** check geographic restrictions and very-new-card timing.
- **65:** explain the daily transaction-count limit and reset timing when confirmed.
- **14, 54, 56, 41, 43, 82, 87:** use the corresponding card-number, expiry, unknown-card, lost/stolen, damage/CVV, or cashback procedure. For stolen-card or suspected-fraud cases, apply enhanced verification and transfer/escalate as required.
- **04, 07, 34, or 59:** do not disclose the code or fraud rationale. Give only the permitted neutral response and escalate/transfer as required.
- **19:** immediate retry is appropriate; after a repeat Code 19, wait 10–15 minutes.
- **91, 92, or 96:** describe a temporary network/system issue, advise retrying in a few minutes (or 10–15 if persistent), and offer a different payment method where appropriate.

### B. No reliable code

Do not infer a code from the merchant or transaction amount. Use the following evidence-led screen:

1. Confirm card status and the linked account's OPEN status.
2. Compare confirmed amount to daily purchase limit and available amount, considering pending debits and possible holds.
3. Check whether the card response provides restriction fields, fraud alert/source, velocity block, PIN-lock state, and daily usage/count fields.
4. Consider whether the behavior could instead be an isolated terminal/network failure. If card/account/balance/limits/security evidence does not identify a cause, recommend one careful retry or a different terminal/payment method, and collect a receipt/decline message if it recurs.
5. Do not clear a security control, change a PIN, increase a limit, or freeze/close a card merely because the cause remains unknown.

## Temporary purchase or ATM limit increase

Only offer/request this after the diagnosis establishes that the limit is the issue and the customer explicitly asks for it. Before calling `request_temporary_debit_card_limit_increase_8374`, verify all of the following:

- the linked checking account is OPEN and in good standing;
- the account is at least 60 days old;
- no overdraft fee occurred in the previous 30 days (review transactions);
- the card is ACTIVE;
- there was no temporary increase for that card in the preceding 24 hours;
- requested `new_limit` is no more than 150% of current applicable limit; and
- the customer confirms the requested limit type (`purchase` or `atm`) and new limit.

State that the increase lasts 24 hours and that third-party ATM limits cannot be overridden. Unlock the tool only when this workflow is needed; call it with `card_id`, `limit_type`, and `new_limit`. A script recommendation never executes it.

## Closure and customer response

Give a concise, factual outcome: what was confirmed, what remains unavailable, safe next step, and any action actually completed. For unresolved repeats, collect the merchant/terminal, timestamp if known, amount, exact message, device/app/browser details where relevant, and screenshots/receipt for escalation. Transfer to `fraud_or_security_concern` for bank-initiated alerts, suspected compromise, or other security-sensitive cases; use the most specific available transfer reason for other required escalations.

## Helper script

Run with normalized JSON on stdin:

```json
{
  "amount": 0,
  "current_date": "YYYY-MM-DD",
  "accounts": [{"account_id":"...","account_type":"checking","status":"OPEN","balance":0,"date_opened":"YYYY-MM-DD"}],
  "cards": [{"card_id":"...","account_id":"...","status":"ACTIVE","daily_purchase_limit":0,"daily_purchase_used":0,"daily_atm_limit":0,"daily_atm_used":0}],
  "transactions": [{"account_id":"...","date":"MM/DD/YYYY","amount":0,"type":"debit_card_purchase","status":"pending"}]
}
```

Run `scripts/assess_decline.py`. It emits JSON with pending-debit totals, matching-card limit facts, and explicit missing-data flags. Validate that the output has `findings` and `missing_data`; reconcile it with source tool results before communicating or acting. It deliberately does not determine available balance, fraud status, authorization holds, or eligibility on its own.
