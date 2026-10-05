---
name: secure-pin-lock-intake
version: 1.0.0
description: Safely handles debit-card PIN-lock requests by enforcing identity verification before disclosure or card action, routing verification failures, and guiding the required per-card fraud-risk investigation when sufficient data and authorized banking tools are available.
---

# Secure PIN-Lock Intake

Use this Skill for PIN-related declines (including codes 55 and 75) or a request to unlock a debit card PIN lock.

## Safety boundary

Do not disclose account, card, transaction, profile, fraud-score, or risk-flag information and do not unlock, reset, freeze, close, or otherwise act on a card until identity verification is complete. A customer must match at least two of the four profile fields: date of birth, email, phone number, and address. Log a successful verification with `log_verification` and the current timestamp.

If a claimed field conflicts with the profile and the customer cannot provide two matching fields, treat verification as failed. Do not keep soliciting the same failed fact, reveal the profile value, or use a requested card action as proof of ownership. Transfer using `transfer_to_human_agents` with `reason: "account_ownership_dispute"`; this Tier-1 code specifically covers identity-verification failures requiring a specialist. Give a minimal summary that states that verification could not be completed, without repeating sensitive values.

This rule takes precedence over PIN-lock research. The provided current-case facts are an example of an unverified intake, not authorization to investigate or act.

## Runtime helper

Use `scripts/assess_pin_lock_intake.py` to make the intake decision deterministic.

Input JSON schema:

```json
{
  "identity_fields": {
    "date_of_birth": {"provided": "...", "profile": "..."},
    "address": {"provided": "...", "profile": "..."},
    "email": {"provided": "...", "profile": "..."},
    "phone_number": {"provided": "...", "profile": "..."}
  },
  "requested_cards": 1,
  "pin_locked_cards_observed": 0
}
```

Only include fields actually supplied and actually obtained from the authoritative user profile. Values are normalized for harmless formatting differences in addresses and phone numbers. The script emits JSON containing `verification_status`, matching and conflicting field names (never values), the permitted next stage, and—when needed—the required transfer reason and a safe summary. `requested_cards` and `pin_locked_cards_observed` must be nonnegative integers.

Example runnable call:

```bash
python3 scripts/assess_pin_lock_intake.py <<'JSON'
{"identity_fields":{"address":{"provided":"...","profile":"..."},"date_of_birth":{"provided":"...","profile":"..."}},"requested_cards":1,"pin_locked_cards_observed":0}
JSON
```

Validate that `verification_status` is `verified` before calling `log_verification` or retrieving account/card activity. If it is `failed` or `insufficient`, do not attempt banking actions. An `invalid_input` result means request only the missing or corrected non-sensitive intake data; do not infer a result.

## Verified investigation workflow

After successful verification and logging:

1. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Limit debit-card work to linked checking accounts and identify the customer-owned cards.
2. Retrieve every card for each relevant account using `get_debit_cards_by_account_id_7823`. Confirm the target card, ownership, and status. Identify *all* cards with `pin_locked = TRUE`. A report or observation that multiple cards are locked is an automatic escalation condition: investigate every locked card before considering any unlock; never unlock one first.
3. For each locked card, first check automatic escalation triggers:
   - `pin_lock_reason == "security_hold"`: chat agents cannot unlock; offer security-team transfer for that card.
   - another account card is PIN-locked: complete all per-card investigations before any unlock decision.
   - any card replaced within 90 days for `issue_reason == "stolen"`: require enhanced verification.
4. Retrieve transaction history for each affected linked account with `get_bank_account_transactions_9173`. Use only available, attributable data. The documented transaction response does not guarantee the PIN-decline transaction types or timestamps needed for the full score. If required decline, successful-PIN-use, prior-lock, fraud-alert, or timing/location data are absent, do not invent values or calculate a partial score as if complete; route the security investigation to a human.
5. When all required data exist, score **each locked card separately** under the PIN Lock Investigation Protocol: location (A1–A3), time (B1–B3), amount (C1–C4), card history (D1–D3), and account factors (E1–E3). Do not reveal point values, calculations, thresholds, or internal flags to the customer.
6. Apply the required protocol outcome:
   - 0–4: unlock only after standard verification.
   - 5–7: ask whether the failed attempts were theirs before an unlock.
   - 8–10: ask location/time questions; unlock only after confirmation and a satisfactory explanation.
   - 11–14: no unlock on the call; callback or enhanced verification is required.
   - 15+: no unlock; review for unauthorized successful activity and recommend closure/replacement as appropriate.
   - Any individual 3-point flag requires supervisor review regardless of total.
   - A customer denial/confusion, or saying they were asleep for a high-risk-time attempt, must be handled as the protocol directs and should not be overridden by a lower recalculated score.
7. For outcomes where an unlock is permitted, use only an explicitly documented and available authorized unlock capability. No unlock tool is established by this Skill's evidence. Never substitute a PIN-reset, alert-clear, unfreeze, or other tool for an unlock. If the authorized unlock capability is unavailable, transfer for security handling rather than improvising a card-state change.
8. For any actual authorized unlock, comply with post-unlock requirements based on prior locks in 90 days: no extra step for 0; offer notifications for 1; offer PIN reset for 2; for 3+ do not unlock—reset PIN is required. A PIN reset separately requires verified identity, ownership, ACTIVE card status, card last four digits, and a compliant new PIN, then uses `reset_debit_card_pin_6284` if available.
9. When the protocol prohibits unlock or fraud is suspected, review for successful unauthorized transactions. For unauthorized activity, follow the dispute process and appropriate closure/replacement procedures; otherwise offer the protocol’s security-team, replacement, or PIN-reset options. Use `fraud_or_security_concern` for a security transfer unless the more-specific identity-verification failure reason above applies.

## Customer communication

Be empathetic but neutral. Say that identity verification could not be completed and that a specialist will help continue securely. Do not say that the account is fraudulent, reveal a security hold or fraud score, confirm the number or status of cards before verification, or quote internal calculations.
