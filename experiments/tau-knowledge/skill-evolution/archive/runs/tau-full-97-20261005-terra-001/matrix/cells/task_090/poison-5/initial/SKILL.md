---
name: pin-locked-debit-card-investigation
description: Assess one or more PIN-locked debit cards before any unlock decision. Use for debit-card decline code 55 or 75, a locked PIN report, or a request to unlock a card after failed PIN attempts.
---

# PIN-Locked Debit Card Investigation

Use this Skill whenever a customer reports that a debit-card PIN is locked. Never unlock a PIN-locked card based only on the customer's statement, and never disclose internal fraud scores, flag values, calculations, or security-trigger details to the customer.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and action boundary

This Skill performs the required investigation and identifies the protocol outcome. The available documentation identifies `reset_debit_card_pin_6284` for a voluntary PIN reset on an eligible active card, but does **not** document a PIN-unlock action for a PIN-locked card. Do not use PIN reset, fraud-alert clearing, velocity-block clearing, unfreezing, or any other card operation as a substitute for an authorized PIN unlock.

If the investigation would otherwise permit an unlock but no documented and available PIN-unlock action exists, explain that the lock requires specialist handling and transfer using `technical_system_error` with a summary that the mandatory PIN-lock assessment was completed but no supported unlock action is available. If fraud, a security hold, a critical outcome, suspicious denial, or supervisor review is involved, transfer using `fraud_or_security_concern` instead.

## Required workflow

1. **Verify identity before any banking action.** Obtain confirmation of at least two of date of birth, email, phone number, and address. Look up the user only using information supplied by the customer. Retrieve the current time and call `log_verification` only after two fields have been confirmed. Confirm the customer is the cardholder/account owner before considering any card action.
2. **Discover the complete relevant card set.** Unlock and call `get_all_user_accounts_by_user_id_3847`. For every checking account, unlock and call `get_debit_cards_by_account_id_7823`. Do not limit review to a card the customer names or to a supplied last four digits. The customer may identify the preferred checking account, but all PIN-locked cards on that account must be investigated before any unlock decision for that account.
3. **Retrieve evidence.** For every checking account containing a relevant or PIN-locked debit card, unlock and call `get_bank_account_transactions_9173`. Inspect all returned records and any available card lock/security fields. Obtain missing material facts from the customer or treat them as unresolved; never infer absent facts as safe.
4. **Check automatic triggers before scoring.** For each PIN-locked card, check: `pin_lock_reason == security_hold`; other PIN-locked cards on the same account; and any card on the account issued as a stolen replacement in the last 90 days. A security hold cannot be unlocked by chat and requires security-team transfer. More than one locked card requires every locked card to be assessed individually before any unlock. A recent stolen replacement requires enhanced verification.
5. **Score every locked card separately.** Normalize the collected facts into the script schema below and run `scripts/assess_pin_lock.py`. The script returns a conservative assessment. Unknown evidence remains unknown rather than contributing zero points. Resolve all score-relevant unknowns before treating its score as complete.
6. **Ask required customer questions for a complete score of 5 or more.** Ask only the questions corresponding to scored flags:
   - Location: ask whether the customer was at the declined-attempt location. On a credible yes, remove location flags and recalculate; on no, retain them.
   - Decreasing amounts: ask whether the customer remembers the specific attempted amounts in chronological order. Remove only the amount-pattern flag on credible confirmation.
   - Overnight time flag worth 2 or 3: ask whether the customer was attempting to use the card at that time. Remove the time flag on credible confirmation. If the customer says they were asleep or gives an equivalent denial, treat this as a critical security concern; do not unlock.
   Never tell the customer the numerical score or internal reasons beyond the question needed for verification.
7. **Apply the protocol outcome.** A flag worth 3 points requires supervisor review regardless of total. Three or more prior locks in 90 days requires PIN reset and prohibits unlock. Otherwise: 0–4 may proceed only after standard identity verification; 5–7 needs the failed-attempt ownership question; 8–10 needs satisfactory location/time confirmation; 11–14 needs callback or enhanced verification; and 15+ cannot be unlocked. Do not override automatic triggers or incomplete evidence.
8. **If an unlock is prohibited or fraud is suspected,** examine the suspicious period for successful unauthorized transactions. If found, follow the debit-card dispute process, close and replace the card as applicable, and use the mandated action tools only after their prerequisites are met. If none are found, offer security-team investigation, PIN reset, or card closure/replacement as appropriate. A closure, dispute, replacement, reset, or transfer is a separate banking workflow and has its own prerequisites.
9. **Post-unlock requirement, only if a separately supported unlock succeeds:** with 1 prior lock, offer PIN-lock notifications; with 2 prior locks, offer a PIN reset. With 3+ prior locks, do not unlock and require reset.

## Assessment helper

Run `scripts/assess_pin_lock.py` through the skill runtime. It reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "now": "ISO-8601 timestamp with timezone",
  "customer_address": {"city": "...", "state": "...", "country": "US"},
  "account": {"account_id": "...", "balance": 0, "date_opened": "YYYY-MM-DD"},
  "cards": [{
    "card_id": "...", "account_id": "...", "pin_locked": true,
    "pin_lock_reason": "...", "issue_reason": "...", "date_issued": "YYYY-MM-DD",
    "daily_atm_limit": 0, "prior_pin_locks_90d": 0,
    "velocity_blocked": false, "fraud_alert_active": false
  }],
  "target_card_id": "...",
  "declined_attempts": [{
    "card_id": "...", "timestamp": "ISO-8601 timestamp with timezone",
    "amount": 0, "location": {"city": "...", "state": "...", "country": "US"}
  }],
  "successful_transactions_7d": [{"timestamp": "...", "location": {"city": "...", "state": "...", "country": "US"}}],
  "successful_pin_uses": [{"timestamp": "..."}],
  "successful_atm_withdrawals": [{"amount": 0}],
  "overdraft_fee_count": 0,
  "confirmations": {"location_confirmed": false, "amounts_confirmed": false, "time_confirmed": false, "customer_was_asleep": false}
}
```

Dates may be supplied as `MM/DD/YYYY`, `YYYY-MM-DD`, or ISO timestamps. `declined_attempts` must contain only the affected card's declined ATM/POS PIN attempts in the relevant investigation period. The documented transaction feed may not expose all needed PIN-specific fields, timestamps, lock history, or structured locations; collect those facts through supported records or customer questioning. Do not manufacture them.

### Output schema and validation

The output contains `complete`, `unknown_inputs`, `automatic_triggers`, `flags`, `score`, `risk_level`, `required_questions`, `supervisor_review`, `unlock_permitted_by_protocol`, and `recommended_path`. A valid output has one nonnegative integer score per known flag, a total equal to the sum of known non-removed flags, and `complete: false` when a required scoring input is absent. Review `unknown_inputs` before proceeding. `unlock_permitted_by_protocol: true` means only that the scoring protocol does not prohibit unlock; it never authorizes an undocumented tool action.

Example runtime call (use live case facts, not this placeholder structure):

```json
{"now":"2025-01-01T12:00:00-05:00","customer_address":{"city":"Example","state":"MA","country":"US"},"account":{"account_id":"account-id","balance":600,"date_opened":"2020-01-01"},"cards":[{"card_id":"card-id","account_id":"account-id","pin_locked":true,"daily_atm_limit":500,"prior_pin_locks_90d":0}],"target_card_id":"card-id","declined_attempts":[],"successful_transactions_7d":[],"successful_pin_uses":[],"successful_atm_withdrawals":[],"overdraft_fee_count":0}
```

## Customer communication

Acknowledge urgency without promising access. State that you must review the PIN lock securely before taking action. Ask concise fact-gathering questions when records are incomplete. Do not claim an unlock, reset, closure, dispute, or replacement has occurred unless the applicable documented tool has completed successfully.
