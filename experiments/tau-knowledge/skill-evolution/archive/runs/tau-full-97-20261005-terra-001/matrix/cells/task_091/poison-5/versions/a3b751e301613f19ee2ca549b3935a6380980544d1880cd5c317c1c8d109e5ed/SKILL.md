---
name: debit-card-pin-lock-investigation
description: Safely investigate one or more PIN-locked debit cards. Use for PIN decline codes 55 or 75, or when a debit-card lookup reports pin_locked=true. The skill prevents servicing while identity is unresolved, requires review of every locked card, applies PIN-lock fraud-risk rules, and directs unlock, reset, or security escalation without exposing internal scoring.
---

# Debit Card PIN-Lock Investigation

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety rules

- Treat an unlock, PIN reset, freeze/unfreeze, alert clearing, closure, replacement order, or dispute as a banking action.
- Do not perform or represent any banking action as completed unless its authorized runtime tool succeeds.
- Do not reveal internal risk scores, point values, automatic triggers, internal-only decline codes, or scoring calculations. Required customer questions may name the relevant location, time, and amounts.
- Do not use another card action as a workaround for an unauthorized PIN unlock.
- If a required fact is unavailable, obtain it from authorized records or escalate; do not assume a favorable result.

## Identity verification is a hard gate

1. Locate the canonical profile using a supplied name, email, or user ID, then compare the customer's supplied identity values to the profile.
2. Standard verification requires exact matches for at least two of: date of birth, email, phone number, and full address.
3. **A supplied identity field that conflicts with the canonical profile invalidates verification.** In particular, if DOB is requested or supplied and does not exactly match, do not treat matching email, phone, or address as curing that DOB discrepancy.
4. Ask the customer to correct the conflicting value. If they repeat, deny, or cannot resolve it, clearly state that identity verification cannot be completed. Keep the customer unverified; do not call `log_verification`.
5. Call `log_verification` only after all supplied verification values match, the two-field minimum is met, and the profile identity is resolved. Use the canonical profile data and current timestamp.
6. Until verification succeeds, do not unlock or reset a PIN, clear a protection, freeze/unfreeze/close a card, file a dispute, order a replacement, or make any other servicing change.

A limited read-only review may be used to assess an already reported security concern and prepare a security handoff. Do not disclose account-specific details beyond what is necessary for the customer to identify the reported concern, and do not convert that review into servicing while the identity gate remains unresolved.

## Evidence collection

After identity is verified—or, for an unresolved identity case, only as limited read-only evidence needed for a security escalation—perform the following:

1. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`; retain account ID, type, status, balance, and opening date.
2. For every relevant checking account, call `get_debit_cards_by_account_id_7823`. Retrieve all current and historical cards. Confirm target-card ownership, status, last four, issue reason/date, ATM limit, PIN-lock state/reason, security flags, and lock history where provided.
3. Call `get_bank_account_transactions_9173` for every relevant checking account. Retain transaction ID, timestamp/date, description/location, amount, type, status, and card association.
4. If more than one card is PIN-locked, assess **every currently locked card individually** before any unlock decision. A card on the same account cannot be unlocked until all locked cards on that account have been reviewed and dispositioned.

## Automatic gates

For each locked card, check these before an unlock decision:

- If `pin_lock_reason` is `security_hold`, chat agents cannot unlock it; transfer to security.
- If another card on the same account is locked, complete all card reviews first.
- If any card on that account was issued for `stolen` within the preceding 90 days, enhanced verification is required before an otherwise eligible unlock.
- Three or more prior PIN locks in 90 days require a PIN reset and prohibit an unlock.

Use `scripts/assess_pin_lock_risk.py` with normalized record data as an internal aid. Its JSON schema is documented in the script. Correct an `error` response or collect its `missing_data`; neither permits an unlock.

## Risk review and outcomes

Review location mismatch/scatter/travel conflict; decline time, prior legitimate PIN use, and attempt velocity; amount patterns, historical ATM amount, and daily limit; lock frequency, card age, other-card security flags; and account age, overdrafts, and balance.

A single three-point flag requires supervisor review regardless of total score. Apply the final result as follows:

| Internal score | Handling |
|---|---|
| 0–4 | Unlock only after verified identity and all gates are cleared. |
| 5–7 | Ask: “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after a satisfactory answer and cleared gates. |
| 8–10 | Ask applicable location and time questions; unlock only after confirmation, a satisfactory explanation, and cleared gates. |
| 11–14 | Do not unlock on this call; require callback or enhanced verification. |
| 15+ | Do not unlock; review suspicious successful activity and recommend closure/replacement if fraud is suspected. |

For scored flags, use only these required questions:

- Location mismatch: “I see your card was locked after failed PIN attempts at [location]. Were you at that location?” A yes removes location flags and requires recalculation; a no retains them.
- Decreasing amounts: “The attempts were for [amount 1], then [amount 2], then [amount 3]. Do you remember trying those specific amounts?” Confirmation removes only the amount-pattern flag.
- Time-of-day score of two or more: “These attempts occurred at [time]. Were you trying to use your card at that time?” If the customer says they were asleep or otherwise denies it, treat the matter as critical: do not unlock and escalate.

Rerun the assessment after a permitted flag change. Customer confirmation never overrides a security hold, mandatory reset, unresolved identity, all-cards review requirement, or supervisor-review gate.

## Servicing and escalation

Use an authorized PIN-unlock capability only when identity was successfully logged, ownership and account/card status were confirmed, every locked card was reviewed, all gates are resolved, required questions were answered, and the final disposition permits it. If no authorized unlock capability exists, transfer rather than improvising another card action.

After a successful eligible unlock:

- 0 prior locks: no extra step.
- 1 prior lock: offer PIN-lock notifications.
- 2 prior locks: offer a PIN reset because this is the third lock in 90 days.
- 3+ prior locks: do not unlock; reset only if all reset prerequisites are satisfied.

A PIN reset requires a verified card owner, an ACTIVE card, confirmed card last four, and a customer-selected four-digit PIN that is neither sequential, all identical, birth year, nor birth month/day. Use `reset_debit_card_pin_6284(card_id, last_4_digits, new_pin)` only after those conditions. Never repeat or display the PIN.

For security holds, critical/high-risk results, a denied suspicious transaction, or unresolved identity, preserve the no-unlock decision and transfer with `transfer_to_human_agents(reason="fraud_or_security_concern", summary=...)`. The summary must include the reported decline location/time, suspicious successful transactions and amounts, failed attempts, the customer’s response, all affected card last-four values when available, and that identity verification was incomplete if applicable.

If verified and the customer identifies unauthorized successful transactions, follow the debit-card dispute procedure and its Reg E, transaction, account, card, and category prerequisites before filing. Do not file or close/freeze a card while identity remains unresolved.

## Script interface and validation

Run the packaged helper by sending JSON on stdin:

```json
{
  "now": "2025-01-15T12:00:00-05:00",
  "customer": {"home_city": "Example City", "home_state": "EX", "home_country": "US", "account_opened_at": "2022-01-01", "current_balance": 600},
  "cards": [{"card_id": "runtime-card-id", "pin_locked": true, "date_issued": "2023-01-01", "daily_atm_limit": 500, "prior_pin_locks_90d": 0, "declined_transactions": []}],
  "transactions": []
}
```

It emits `{"cards":[...]}` with per-card flags, score, disposition, gates, questions, and missing data, or `{"error":"..."}` for invalid input. Before an unlock, validate that every locked card appears exactly once, no safety-critical evidence is missing, all automatic gates are resolved, identity was logged successfully, and the final decision permits unlocking.
