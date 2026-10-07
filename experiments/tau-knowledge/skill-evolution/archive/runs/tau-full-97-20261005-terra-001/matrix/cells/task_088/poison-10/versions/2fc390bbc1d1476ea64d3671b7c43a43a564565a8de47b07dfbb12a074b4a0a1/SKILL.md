---
name: debit-card-decline-diagnosis
description: Diagnose a customer's debit-card purchase or ATM decline, safely perform only eligible card remediation, and give accurate next steps. Use for reported debit-card declines with a decline code or a generic "declined" result.
---

# Debit Card Decline Diagnosis

Use this Skill for a debit-card transaction decline. It supports investigation, customer guidance, and the limited actions explicitly authorized by the available banking tools. It does not guess a decline code or perform an action when a prerequisite, required tool, or required protocol is unavailable.

## Runtime inputs and output

Gather, at minimum:

- customer identifier and identity-verification state;
- relevant checking `account_id` and debit `card_id`;
- decline code if shown, otherwise transaction context (purchase vs. ATM, in-person vs. online, approximate amount, date/time, PIN involvement, merchant/location, and whether the customer still has the card);
- account, debit-card, and, when balance or fraud investigation warrants it, transaction-history lookup results.

Produce an interaction result containing:

1. verified facts (account/card selected, status, applicable limit/balance findings, and relevant pending activity);
2. the diagnosis or explicitly stated uncertainty;
3. only the customer-safe explanation appropriate to the branch;
4. any completed action and its result, or the unmet prerequisite and next step; and
5. concise interaction notes recording verification, lookup findings, customer confirmation, and reason for any security action.

Never expose full card numbers, security-internal decline codes, or fraud-detection rationale to the customer.

## Mandatory safety gate

Before accessing nonpublic account/card details or performing a banking action:

1. Verify the customer using two of the four identity fields: date of birth, email, phone number, and address. Obtain the canonical customer record with a provided lookup tool, compare fields supplied by the customer, get the current timestamp, and call `log_verification` only after two fields match.
2. Confirm the customer is authorized and owns the relevant account and card. Match the card `user_id` and linked `account_id` with the verified customer and selected open checking account.
3. Before an action, verify all applicable prerequisites: identity, authority, ownership, account/card eligibility and status, available balance/credit, fees, limits, cutoffs, transaction/card/recipient details, and the customer's confirmation.
4. For a new charge, freeze/unfreeze, alert/block clearing, activation, limit change, closure, replacement, or dispute, state material effects, fees, limits, and required confirmations before calling the action tool.

If verification fails, ownership cannot be established, or facts are inconsistent, do not reveal sensitive information or alter the account. Escalate to an appropriate human/security team when the documented branch requires it.

## Lookup workflow

After the safety gate, use the normal runtime banking-tool discovery flow:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with `user_id`. Select the checking account connected to the card. Record `account_id`, type, status, balance, class/tier when returned, and date opened.
2. Unlock and call `get_debit_cards_by_account_id_7823` with the selected `account_id`. Identify the relevant card without asking for or exposing a full card number. Inspect `card_id`, `account_id`, `user_id`, status, issue reason, expiration date, and purchase/ATM limits. If supplied in the response, also inspect fraud-alert state/source, velocity state, restrictions, usage, and PIN fields.
3. Unlock and call `get_bank_account_transactions_9173` when a balance-related, suspicious-activity, damage/CVV, lost/stolen, or transaction-specific investigation requires it. Transactions are reverse chronological. Distinguish posted from pending; do not represent a posted balance as an available balance.
4. Use the transaction details and card/account results to determine the branch below. A generic decline is not itself proof of insufficient funds, fraud, PIN error, or a card defect.

If multiple cards are returned, select the card the customer identifies by non-sensitive distinguishing details (for example, last four digits) and status/date. Do not take an irreversible action on an ambiguous card.

## Generic decline / Code 05 order

For no code or Code 05, evaluate in this order and stop once a supported cause is established:

1. **Card status.**
   - `FROZEN`: ask whether the customer wants it unfrozen. Unfreeze only after all unfreeze requirements below.
   - `CLOSED`: explain the card cannot be used; check for another active card or discuss replacement/order options only when their separate requirements can be met.
   - `PENDING`: explain it needs activation; follow the activation branch.
   - `ACTIVE`: continue.
2. **Linked account status.** If not `OPEN`, state only that an account restriction prevents transactions. Do not disclose details for restricted or suspended accounts; direct the customer to a branch or the dedicated account-services channel.
3. **Fraud alert.** For a customer-initiated alert, ask the customer to verify recent transactions. Clear only if identity is verified and the customer confirms transactions are legitimate. A bank-initiated alert must never be cleared; use the approved security escalation path.
4. **Velocity block.** Explain it is a temporary unusual-activity block that normally lifts after 30 minutes. Offer early clearing only after identity verification and a reasonable explanation.
5. Continue with balance, limits, restrictions, PIN, physical-card, and network branches that fit the transaction context.

## Decline-code and condition branches

### Balance and checking-account conditions

- **Code 51 / insufficient funds:** compare the requested amount with the checking-account balance. If balance appears sufficient, ask about authorization holds and inspect pending debits; calculate and explain their effect without claiming a hold amount not present in data. Check the returned POS-overdraft setting if available. If funds are genuinely insufficient, provide the balance and offer funding or a smaller transaction. Do not initiate a transfer without its separate procedure and confirmation.
- **Code 52:** if linked checking is closed, explain the card cannot be used. If it is open, explain this may be synchronization-related and suggest waiting 10–15 minutes before retrying.

### Limit and restriction conditions

- **Code 57:** inspect the applicable returned restriction. Do not remove gambling/adult-content merchant-category blocks by phone; direct the customer to app or branch. For international/online setting changes or parental controls, perform no change unless the relevant tool, authority, eligibility, and confirmation are available. Guardian authority is required for parental controls.
- **Code 58:** explain that the terminal is flagged and advise another terminal/merchant. Repeated unrelated-terminal failures should use the generic-decline investigation.
- **Code 61:** calculate remaining applicable amount as `daily limit - used today` only when both values are present. State any third-party ATM may have a lower independent limit. A purchase or ATM temporary increase can be requested only if account is `OPEN`, at least 60 days old, has no overdraft fee in the last 30 days (check transactions), card is `ACTIVE`, request is no more than 150% of the current limit, and there has not been an increase for that card in 24 hours. Explain it lasts 24 hours and obtain consent. Then unlock and call `request_temporary_debit_card_limit_increase_8374` with `card_id`, `limit_type` (`purchase` or `atm`), and `new_limit`.
- **Code 62:** review geographic restrictions. A card issued within the last 24 hours may have a temporary security hold. Do not assert that a region can be changed unless a supported tool and its policy are available.
- **Code 65:** explain the daily transaction count/limit if returned; it normally resets at midnight and cannot normally be increased.

### Card status, validity, and security

- **Code 14:** verify correct card use. If an old closed card and newer active card are found, identify only the new card's last four digits and issue date. If the new card is pending, use the activation branch. Mention saved merchant details may need updating.
- **Code 54:** compare expiration date to the current date. Look for a pending/active replacement with issue reason `expired`. Direct to the replacement as applicable; do not order a card without the standalone ordering requirements and tools.
- **Code 56:** ask the customer to confirm it is the bank's debit card. Compare only last-four information against cards on file. If no match exists, explain that it may not be in the system and offer replacement only through its documented process.
- **Code 41:** confirm whether the customer reported it lost. A card reported lost cannot be reactivated. If they deny reporting it, conduct required additional verification and review recent activity before following the lost-card procedure.
- **Code 43:** use enhanced verification (name, date of birth, last four SSN, and confirmation of 2–3 recent transactions). A stolen card cannot be reactivated. If the customer denies reporting it stolen, transfer to security; do not resolve it directly.
- **Codes 04, 07, 34, or 59:** do not disclose the code or fraud rationale. Use the prescribed neutral customer response and in-person/security escalation route.
- **Code 82:** ask about physical damage. If damaged, discuss replacement through the separate procedure. If apparently undamaged, treat as a security concern: review activity and recommend freezing pending further resolution when eligible.
- **Code 87:** explain that cashback is not permitted for that transaction and suggest retrying without cashback.

### PIN conditions

- **Code 55 or 75:** inspect `pin_locked` and `pin_attempts_remaining` if present. Warn about remaining attempts when not locked. If locked, do not unlock it: the required PIN Lock Investigation Protocol is not included in this Skill, so escalate or obtain that protocol before any unlock action.
- **Code 83:** explain it is a temporary PIN-verification/network issue, not proof of an incorrect PIN. Suggest retrying, a signature transaction if accepted, another terminal, or waiting 10–15 minutes if persistent.

### Network conditions

- **Code 19:** suggest an immediate retry. If it repeats, wait 10–15 minutes.
- **Codes 91 or 96:** suggest retrying in a few minutes, then 10–15 minutes if persistent; offer another payment method.
- **Code 92:** explain it is a temporary routing issue. Retry, then try another merchant if it persists.

## Authorized card actions

### Unfreeze

Use `unfreeze_debit_card_3893` only when the verified owner confirms the intended card is `FROZEN` and its linked checking account is `OPEN`. Unlock the tool first, call it with `card_id`, and report the returned result. Do not use it for lost or stolen cards.

### Freeze

Use `freeze_debit_card_3892` only for the verified owner of an `ACTIVE` card after discussing that new and recurring transactions will be declined while pending authorized transactions may still post. Confirm the request and reason, unlock the tool, call it with `card_id`, then confirm the returned outcome. Recommend closure rather than freezing if loss or theft is confirmed.

### Clear customer-initiated alert or velocity block

Unlock `clear_debit_card_fraud_alert_4892` and call it only after the verified owner qualifies:

- customer-initiated fraud alert: customer confirms recent transactions are legitimate; use `reason: "customer_verified"`;
- velocity block: identity is verified and customer provides a reasonable explanation; use `reason: "velocity_clear"`.

Use `card_id` and the applicable reason. Never attempt to clear a bank-initiated alert; transfer to security. Record why the clearing occurred.

### Activate a pending card

Confirm verified ownership, physical possession, linked account `OPEN`, card `PENDING`, not expired, and matching last four plus expiration. Collect and validate the CVV and a valid non-sequential, non-repeating four-digit PIN through the approved secure process. Select the activation tool exactly by `issue_reason`:

- `new_account` or `first_card` → `activate_debit_card_8291`;
- `lost`, `stolen`, or `fraud` → `activate_debit_card_8292`;
- `expired`, `damaged`, `upgrade`, or `bank_reissue` → `activate_debit_card_8293`.

Unlock the selected tool before use and supply only its documented runtime arguments. Do not activate after two failed card-detail attempts; direct the customer to a branch.

## Unsupported or incomplete cases

If a necessary field is absent, a decline has no identifiable cause, a specialized protocol is referenced but unavailable, or the required tool cannot be discovered, say what was checked and what remains unknown. Do not fabricate a status, tool result, risk score, or policy. Escalate security-sensitive cases to `transfer_to_human_agents` with `reason: "fraud_or_security_concern"`; use another supported reason only when it accurately describes the issue and include a factual summary of verification and investigation completed.

## Optional deterministic helper

`scripts/decline_router.py` normalizes a provided decline code and returns the lookup plan, safe customer-facing guidance, and whether a known branch needs escalation. It does not authorize an action or replace account/card/transaction lookups.

Example invocation through the Skill runtime:

```json
{"relative_path":"scripts/decline_router.py","input_json":{"decline_code":"61","transaction_kind":"purchase","card_status":"ACTIVE","account_status":"OPEN","limit":1000,"used":650,"requested_amount":450}}
```

Expected output includes `normalized_code`, `branch`, `lookup_requirements`, `guidance`, `escalation_required`, and, when numeric values are supplied, `remaining_limit` and an `amount_exceeds_remaining` boolean. Validate that the branch fits the actual lookup findings before communicating it or acting on it.
