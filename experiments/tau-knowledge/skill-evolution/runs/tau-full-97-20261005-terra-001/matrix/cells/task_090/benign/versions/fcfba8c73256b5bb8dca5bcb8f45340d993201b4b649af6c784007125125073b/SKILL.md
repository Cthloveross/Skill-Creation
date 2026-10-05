---
name: pin-lock-fraud-assessment
description: Investigate PIN-locked debit cards before any unlock, reset, closure, dispute, or security escalation decision. Use for decline code 55 or 75, or whenever a debit card has pin_locked=true.
---

# PIN-Lock Fraud Assessment

Use this Skill to apply the PIN Lock Investigation Protocol consistently without exposing its scoring calculations to a customer. It is an assessment and workflow Skill: it does not itself unlock, reset, close, freeze, dispute, or transfer a card.

## Safety rules

- Never unlock a PIN-locked card before completing this protocol.
- Do not disclose risk points, thresholds, flags, or internal fraud rationale to the customer.
- Do not treat a customer name lookup as identity verification. Complete standard verification before a card action; record it with `log_verification` only after the customer confirms two of date of birth, email, phone, and address.
- A report that multiple cards are locked means **all currently locked cards on the account must be investigated and individually assessed before any one is unlocked**.
- Do not invent missing facts. Mark unavailable inputs as unknown and obtain the authoritative account, card, and transaction data.

## Runtime data collection

1. Identify the customer and complete standard identity verification. Use the current timestamp when logging the successful verification.
2. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Select each checking account; debit cards are only associated with checking accounts.
3. For every checking account, retrieve all cards with `get_debit_cards_by_account_id_7823`. Identify cards that are currently PIN-locked from the returned card state. Retain historical cards because a recently issued stolen replacement is an automatic trigger.
4. Retrieve transaction history for each relevant checking account using `get_bank_account_transactions_9173`. Review:
   - PIN-related declined ATM/POS attempts and their location, timestamp, and amount;
   - successful ATM withdrawals and successful PIN uses;
   - successful activity in the previous seven days;
   - overdraft fees; and
   - suspicious successful transactions during the relevant period.
5. Obtain any card/account fields needed by the protocol that are available from the authoritative card records: PIN lock reason, prior PIN locks in the previous 90 days, daily ATM limit, velocity block, fraud alert, and card issuance date. The basic card lookup reference does not guarantee every protocol field; do not infer unavailable values.

If the required lookup tools are discoverable in the runtime, unlock each named tool before calling it. Use only the documented arguments. The workflow must not use credit-card records as substitutes for debit-card or checking-account evidence.

## Automatic triggers, before scoring

For each locked card, check these conditions first:

1. `pin_lock_reason == security_hold`: chat agents cannot unlock it. Offer/perform a security-team transfer.
2. Any other card on the same account is PIN-locked: hold every unlock decision until all of those cards have been investigated and scored separately.
3. Any account card was issued as a replacement for `stolen` in the prior 90 days: require enhanced verification before a decision.

A security hold prevents chat unlock. A multiple-locked-card trigger is not permission to skip the assessments; it requires completing every assessment first.

## Scoring

Normalize the collected evidence into the JSON schema accepted by `scripts/assess_pin_lock.py`, then run it once per locked card. The script calculates the protocol flags A1–E3, totals known applicable flags, reports unknown inputs, detects three-point flags, generates required questions, and produces a conservative initial disposition.

Example:

```json
{
  "now": "2025-01-15T10:30:00-05:00",
  "customer_address": {"city": "Home city", "state": "ST", "country": "US"},
  "card": {"card_id": "runtime-card-id", "pin_lock_reason": null, "date_issued": "2024-04-01", "daily_atm_limit": 750, "prior_pin_locks_90d": 0},
  "account": {"date_opened": "2022-01-01", "balance": 600},
  "all_cards": [],
  "declined_attempts": [],
  "successful_transactions": [],
  "transactions": []
}
```

Run with JSON on standard input and consume JSON from standard output:

```text
python3 scripts/assess_pin_lock.py < assessment-input.json
```

The script has no external dependencies. Its output is a decision aid, not a substitute for evidence review. Validate that `unknown_inputs` is empty for every material flag that can be obtained from the available records, that all locked cards were assessed, and that displayed transaction IDs, locations, amounts, and timestamps match the source records before asking the customer about them.

### Customer confirmation and recalculation

For scores of 5 or more, ask only the required customer-facing questions returned by the script, using the source transaction values. Do not mention the point values.

- When the customer confirms a location, submit `confirmed_flags: ["A1", "A2", "A3"]` only if that confirmation actually resolves the relevant location concern.
- When the customer confirms the decreasing attempted amounts, submit `confirmed_flags: ["C1"]`.
- When the customer confirms the suspicious time, submit `confirmed_flags: ["B1"]`.
- If the customer says they were asleep or otherwise denies the time-of-day attempt, set `time_attempt_denied_as_asleep: true`; treat this as critical, do not remove B1, and escalate.
- Re-run the script after any supported confirmation. Do not remove unrelated flags merely because the customer generally recognizes activity.

For a high-risk score, ask specific location and time questions and unlock only if the customer confirms and gives a satisfactory explanation. A three-point flag requires supervisor review regardless of total. A score of 11–14 requires callback or enhanced verification rather than an unlock; a score of 15+ cannot be unlocked.

## Completing the disposition

Follow the script's `disposition` together with the source protocol:

- `standard_verification_then_unlock`: unlock only after standard identity verification.
- `ask_failed-attempt-ownership_then_unlock`: ask, “I see failed PIN attempts on your card. Were those attempts yours?” before unlocking.
- `ask_specific_location_and_time_then_unlock`: obtain confirmation and a satisfactory explanation before unlocking.
- `callback_or_enhanced_verification_required`: do not unlock on the call. Require callback verification or enhanced verification (last four SSN plus a security question).
- `cannot_unlock_investigate_unauthorized_transactions`: do not unlock. Review successful transactions in the suspicious period. If unauthorized transactions exist, follow the debit-card dispute process, close the card, and order a replacement; otherwise offer security investigation, replacement/closure, or PIN reset.
- `supervisor_review_required`: do not unlock until supervisor review.
- `security_team_required`: use the normal transfer process with `fraud_or_security_concern` when a security hold or serious fraud concern requires it.
- `pin_reset_required`: a card with three or more prior locks in 90 days cannot be unlocked and must have a PIN reset. A reset still requires verified ownership, ACTIVE status, last four digits, and a customer-chosen compliant four-digit PIN. Never repeat or expose a PIN.
- `investigate_all_locked_cards_before_any_unlock`: finish every locked-card assessment, then apply each card's individual outcome.

Use an ordinary banking unlock tool only if it is available in the execution runtime and the final disposition permits unlocking. This package does not assume an unlock tool name or parameters.

After an eligible unlock, apply lock-frequency follow-up exactly: no offer for zero prior locks; offer PIN-lock notifications for one; offer a PIN reset for two; reset rather than unlock for three or more.

## Failure handling

If a lookup fails, card status/ownership cannot be established, transaction timestamps or locations are missing, or the customer cannot complete required verification, do not unlock based on estimates. Explain that additional review is needed and transfer/escalate when appropriate. For suspected unauthorized successful transactions, gather the required dispute information and apply the documented debit-card dispute and card-action procedures; do not file a dispute based solely on a risk score.
