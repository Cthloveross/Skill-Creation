---
name: pin-lock-fraud-investigation
description: Investigate PIN-locked debit cards before any unlock. Use for PIN-related declines or a customer reporting a locked debit card; assess each card separately, apply fraud-risk escalation rules, collect required verification answers, and complete only eligible card actions.
---

# PIN Lock Fraud Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and scope

Use this workflow whenever `pin_locked` is true or a PIN decline indicates that tries were exceeded. Do not simply unlock the card. Do not reveal risk-score calculations, point values, internal flags, or scoring thresholds to the customer.

Treat each debit card as a separate investigation. If more than one card on the account is locked, investigate all of them before unlocking any card. A customer may choose which card to discuss first, but that does not remove the requirement to finish the other investigations before an unlock.

Before a banking action, confirm identity using two supported profile fields, record the successful verification with `log_verification`, and verify that the customer owns the account and card. Retrieve the customer's accounts, then retrieve every debit card for each relevant checking account. Do not assume a card is active, belongs to the customer, or is eligible based only on the customer's description.

## Required information gathering

1. Obtain the current time for date-window calculations.
2. Retrieve the customer's checking accounts with `get_all_user_accounts_by_user_id_3847` and identify the relevant checking account(s), account class/tier, balance, and opening date.
3. Retrieve all cards for each relevant account with `get_debit_cards_by_account_id_7823`. Identify the target card, its status, issue date, daily ATM limit, PIN-lock state/reason and attempts remaining if supplied by the card lookup, and all other cards on the account.
4. Retrieve account transactions with `get_bank_account_transactions_9173`. Review posted and pending activity for successful ATM withdrawals, successful PIN use if identifiable, overdraft fees, suspicious successful debits, and pending transactions where a later closure might be considered.
5. Obtain the declined PIN-attempt records required by the PIN-lock protocol from the available card/decline history source. The standard bank-account transaction lookup documents posted/pending transaction types and may not contain the required declined types. Do not infer declined location, time, amount, velocity, or a PIN lock reason from absent data. If the required decline history is unavailable, do not unlock; escalate to the security team for completion of the investigation.
6. Check all card issuance history for a card replaced for `stolen` within the prior 90 days. Count prior locks on the target card in the prior 90 days from a reliable lock-history source; do not substitute replacement history for lock history.

## Automatic triggers

Evaluate these before assigning a score:

- `pin_lock_reason = security_hold`: chat cannot unlock the card. Offer transfer to the security team.
- Another card on the same account is PIN locked: complete every card investigation before any unlock.
- Any account card was replaced for `stolen` in the last 90 days: require enhanced verification before proceeding.

## Scoring procedure

Normalize retrieved information and run `scripts/assess_pin_lock.py` to make the repeatable calculation. The script supports a structured, evidence-based input and reports missing inputs rather than inventing values. Review the output alongside the underlying records.

Score the documented A1–A3 location, B1–B3 time, C1–C4 amount, D1–D3 card-history, and E1–E3 account flags. For multiple declined events, use the most risk-indicating supported value for event-specific flags, the shortest supported interval for velocity, and the aggregate of all relevant failed attempts for the daily-limit test. Use only comparable records within the applicable investigation period. A single three-point flag requires supervisor review regardless of total.

Apply the resulting protocol without disclosing the calculation:

- **0–4:** Standard verified unlock may be eligible.
- **5–7:** Ask whether the failed PIN attempts were the customer's before an unlock.
- **8–10:** Ask specific location and time questions. Unlock only if the customer confirms and gives a satisfactory explanation.
- **11–14:** Do not unlock on the call. Require callback verification or enhanced verification consisting of last four SSN plus a security question.
- **15 or more:** Do not unlock. Review for successful unauthorized transactions and recommend closure and replacement.

For a score of at least five, ask only applicable questions:

- Location mismatch: ask whether the customer was at the transaction location. If they confirm, remove the location flags and recalculate; if they deny it, keep the flags.
- Decreasing amount pattern: ask whether they remember trying the specific amounts. Remove that flag only if confirmed.
- Time-of-day score of two or more: ask whether they were using the card at that time. A statement that they were asleep or otherwise could not have used it is a critical fraud indicator; do not unlock.

Record the customer's answers factually and rerun the assessment after supported flag removals. A denial of attempts is evidence of a potential unauthorized event, not authorization to relax controls.

## Completing an eligible result

Only use an available, normal banking unlock action after all of the following are true: verification was logged; ownership, target card, status, and eligibility were checked; all locked cards on the account were investigated; required customer questions were satisfactorily answered; and no escalation rule blocks the action. If the runtime does not provide a documented unlock action, do not invent a tool call; transfer to the appropriate security/specialized team.

After a successful eligible unlock:

- Zero prior locks in 90 days: no extra step.
- One prior lock: offer PIN-lock notifications.
- Two prior locks: offer a PIN reset and explain that frequent locks can indicate the current PIN is difficult to remember.
- Three or more prior locks: do not unlock; a PIN reset is required.

A PIN reset requires verified ownership, an ACTIVE card, confirmed last four digits, and a customer-selected compliant four-digit PIN. Never read a PIN back. Use only `reset_debit_card_pin_6284` with the documented required arguments when that tool is available.

## Fraud, closure, replacement, and transfer

When an unlock is blocked, check the suspicious period for successful unauthorized transactions. If any are identified, obtain the information needed for a dispute, follow the debit-card dispute procedure, and recommend closure/replacement. Closure is a separate destructive action: reconfirm customer ownership, card status, pending transactions/refunds, eligibility, reason, and customer confirmation before using the documented closure tool. Do not close or order a replacement merely because it is recommended.

If a replacement is requested after an eligible closure, determine the checking-account tier, replacement count in the preceding 12 months, required wait period, delivery option, design, exact fees, available balance, and customer confirmation. Explain that applicable fees are automatically charged to the linked checking balance before ordering.

Transfer to the security team or a human specialist for a security hold, unavailable required decline/lock data, a single three-point flag, a high-risk or critical assessment, suspected fraud needing investigation, or any unavailable required action. Provide a concise internal summary of verification status, card/account identifiers, observed decline evidence, customer statements, risk disposition, and actions not taken. Do not include full card numbers or PINs.

## Assessment script

Run:

```sh
python3 scripts/assess_pin_lock.py <<'JSON'
{"now":"2025-01-01T12:00:00-05:00","home_location":{"city":"Example","state":"EX","country":"US"},"card":{"date_issued":"2024-01-01","daily_atm_limit":500,"prior_locks_90d":0},"account":{"date_opened":"2020-01-01","balance":600},"declines":[]}
JSON
```

The example is schema-only; replace every value with current retrieved evidence. Input is one JSON object. Required fields are `now`, `home_location`, `card`, `account`, and `declines`. Declines are objects with ISO timestamp, numeric amount, and a structured `location` object. Optional fields include `successful_transactions`, `last_successful_pin_use`, `other_cards`, `stolen_replacements`, and `overdraft_count`.

The script writes one JSON object containing `automatic_triggers`, `flags`, `total_score`, `risk_level`, `single_flag_escalation`, `recommended_disposition`, and `missing_data`. Validate that `missing_data` is empty for fields necessary to the proposed disposition, compare flags to the retrieved records, and never treat script output as permission to bypass verification, customer questions, or banking-action prerequisites.
