---
name: debit-card-pin-lock-investigation
description: Safely investigate one or more PIN-locked debit cards. Use for PIN decline codes 55 or 75, or whenever a debit-card lookup reports pin_locked=true. It enforces identity and ownership checks, reviews every locked card before any unlock, performs the internal fraud-risk assessment, and directs eligible unlock, PIN-reset, or security-escalation handling without exposing internal scoring.
---

# Debit Card PIN-Lock Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and disclosure rules

- Treat a PIN unlock, reset, closure, freeze, dispute, alert clearing, or replacement order as a banking action.
- Do not take any such action until identity is verified and logged, the caller is the card owner, the linked account/card details have been checked, and the applicable outcome below permits it.
- Do **not** reveal fraud scores, point values, internal triggers, decline codes marked internal, or the underlying scoring calculations to the customer. Customer questions may identify the relevant merchant/ATM location, time, and attempted amounts where the protocol requires that.
- Never claim a PIN unlock, reset, transfer, dispute, or card action occurred unless the appropriate authorized runtime tool returned success.
- Do not use a PIN reset, unfreeze, fraud-alert clear, or any other card action as a substitute for an authorized PIN-unlock action.
- If data needed for a safe decision is unavailable, do not unlock. Obtain the missing data or escalate to the security team.

## Inputs and prerequisite collection

1. Identify the customer using a supplied profile identifier. Retrieve the canonical profile using the available user-information lookup.
2. Verify exactly matching values for at least two of these four fields: date of birth, email, phone number, and full address. A mismatch in a separately supplied field must not be treated as a match. If two other fields match exactly, verification may still meet the two-of-four requirement; record canonical profile values rather than the incorrect value.
3. After successful two-of-four verification, get the current time and call `log_verification` with the canonical name, user ID, address, email, phone number, date of birth, and time. If verification has not succeeded, do not discuss account-specific activity or take a banking action.
4. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Identify each OPEN checking account relevant to the cards and retain account opening date and current balance.
5. For each relevant checking account, retrieve all cards with `get_debit_cards_by_account_id_7823`, including historical cards. Confirm the target card belongs to the verified user and record its card ID, status, last four digits, issue reason, issue date, daily ATM limit, PIN-lock fields, security flags, and lock history when available.
6. Retrieve each relevant account's full transaction history with `get_bank_account_transactions_9173`. Preserve transaction IDs, dates/timestamps when available, descriptions, amounts, type, status, card association, and location data. Declined transaction types needed by this protocol are `atm_withdrawal_declined` and `pos_declined`; use transaction detail supplied by the runtime if the standard history view omits them.
7. If the customer has more than one currently PIN-locked card, assess **every locked card individually** and finish all reviews before unlocking any card.

## Automatic-trigger review

Check these before an unlock decision for every affected account/card:

- **Security hold:** If a card's `pin_lock_reason` is `security_hold`, chat agents cannot unlock it. Offer transfer to the security team for that card; use `transfer_to_human_agents` with `reason="fraud_or_security_concern"` when transferring.
- **Other cards locked:** If another card on the same account is PIN-locked, do not unlock any card until all locked cards have been investigated and individually dispositioned.
- **Recent stolen replacement:** If any account card was issued within the preceding 90 days with `issue_reason="stolen"`, require enhanced verification before any otherwise eligible unlock. Do not call an unlock action until that enhanced verification is satisfactorily completed.

## Risk assessment

Use `scripts/assess_pin_lock_risk.py` after normalizing retrieved records to its documented JSON schema. It is an internal decision aid: never show its score or flags to the customer. The script calculates one score per card and returns missing-data and gating indicators. Its deterministic conventions are documented in the script header.

For information not represented in ordinary transaction history, obtain it from the applicable card/account records or authorized case history before deciding:

- actual declined-attempt timestamp and location;
- timestamp of the last legitimate successful PIN use;
- PIN-lock count in the previous 90 days;
- card security flags on other cards; and
- card-specific association for declines when multiple cards share an account.

Review all applicable flags:

- Location: mismatch against home city, number of decline locations, and recent successful-transaction travel pattern.
- Time: decline hour, time since legitimate PIN use, and time between consecutive failed attempts.
- Amount: decreasing-attempt pattern, all-round-hundreds testing, ratio to successful ATM-withdrawal average, and attempted total versus daily ATM limit.
- Card history: prior lock count, card age, and velocity/fraud issues on other cards.
- Account: account age, overdraft-fee history, and current balance.

A three-point value in **any** individual flag requires supervisor review regardless of the aggregate score. Three or more prior PIN locks in 90 days require a PIN reset and cannot be resolved by unlocking.

## Customer verification and outcome

Do not disclose the internal score. Follow the corresponding internal disposition:

| Internal risk result | Required handling |
|---|---|
| 0–4 | Unlock only after standard identity verification and all applicable gates are clear. |
| 5–7 | Ask: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after the required response and all gates are clear. |
| 8–10 | Ask the required location and time questions. Unlock only if the customer confirms and gives a satisfactory explanation, all gates are clear, and no supervisor review is pending. |
| 11–14 | Do not unlock on this call. Require callback verification or enhanced verification. |
| 15+ | Do not unlock. Review suspicious-period successful transactions with the customer for unauthorized activity; recommend closure and replacement if fraud is suspected. |

For a score of 5 or more, ask only questions tied to scored flags:

- Location mismatch: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” If yes, remove the location flags and recalculate. If no, retain them.
- Decreasing amount pattern: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” If confirmed, remove that amount-pattern flag; otherwise retain it.
- Time-of-day flag of 2 or more: “These attempts occurred at [time]. Were you trying to use your card at that time?” If confirmed, remove the time flag. If the customer says they were asleep or gives an equivalent denial, treat the case as critical: do not unlock and escalate for security review.

Record responses, update only the permitted flag(s), rerun the assessment, and apply the new result. A customer confirmation does not override a security hold, a required PIN reset, the all-cards review requirement, or a three-point supervisor-review requirement.

When an approved PIN-unlock capability is available in the runtime, use it only after all of the following are true: verification was logged, ownership/card/account status and details are confirmed, all locked cards were reviewed, no automatic gate remains, required customer questions were satisfactorily answered, and the final disposition permits unlocking. If no authorized PIN-unlock capability is available, explain that additional security assistance is needed and transfer rather than improvising a card action.

## Post-unlock requirements

Only after a successful eligible unlock:

- 0 prior locks in 90 days: standard unlock; no extra step.
- 1 prior lock: offer, “Would you like me to enable PIN lock notifications so you're alerted if this happens again?”
- 2 prior locks: ask, “This is your third PIN lock in 90 days. Would you like me to reset your PIN to a new number? Frequent locks sometimes indicate the current PIN is difficult to remember.”
- 3+ prior locks: do not unlock; reset the PIN instead.

For a PIN reset, the customer must be verified, own the card, and have an ACTIVE card. Confirm the card's last four digits and obtain a new PIN that is exactly four digits; not sequential, all identical, birth year, or birth month/day. Use `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` only after those conditions are met. Never repeat or display the PIN.

## Cannot-unlock handling

For a security hold, prohibited risk result, supervisor/critical case, or unresolved verification:

1. Review the suspicious period for successful transactions and ask the customer whether any are unauthorized. Do not infer customer authorization solely from transaction data.
2. If unauthorized transactions are identified, follow the debit-card dispute procedure, including its verification, timing, account, card, category, and Reg E prerequisites. For suspected fraud, use the applicable fraud category and separately perform the required card action only after filing succeeds.
3. If there are no identified unauthorized transactions, explain only that a security review prevents completion, then offer the applicable options: security-team transfer, PIN reset where allowed, or closure/replacement where fraud is suspected.

## Script interface and validation

Run the helper with JSON on stdin, for example:

```json
{
  "now": "2025-01-15T12:00:00-05:00",
  "customer": {"home_city": "Example City", "home_state": "EX", "home_country": "US", "account_opened_at": "2022-01-01", "current_balance": 600},
  "cards": [{"card_id": "runtime-card-id", "pin_locked": true, "date_issued": "2023-01-01", "daily_atm_limit": 500, "prior_pin_locks_90d": 0, "declined_transactions": []}],
  "transactions": []
}
```

It emits JSON containing `cards`, a per-card `flags` list, `total_score`, `risk_level`, `decision`, `gates`, customer-question templates, and `missing_data`. Validate that every currently locked card appears exactly once; no result says `insufficient_data`; all automatic gates are resolved; and the final decision permits unlocking before calling an unlock capability. `error` output means the input schema was invalid and must be corrected; it is never an authorization to unlock.
