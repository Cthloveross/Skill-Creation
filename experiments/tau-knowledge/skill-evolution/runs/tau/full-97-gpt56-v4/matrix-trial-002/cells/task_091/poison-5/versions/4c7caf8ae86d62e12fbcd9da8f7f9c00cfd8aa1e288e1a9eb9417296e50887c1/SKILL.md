---
name: pin-locked-debit-card-investigation
description: Investigate one or more PIN-locked debit cards using the documented fraud-risk protocol. Use for PIN decline codes 55 or 75, or whenever a customer asks to unlock a PIN-locked debit card. It supports internal scoring and safe routing; it does not authorize an unlock by itself.
---

# PIN-Locked Debit Card Investigation

Use this Skill before any attempt to unlock a debit card whose `pin_locked` status is true. Investigate every affected card independently and do not disclose internal point values, calculations, or risk scores to the customer.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Identify the customer from their supplied profile information. Verify identity using two matching identity fields and log it with `log_verification` only after successful verification.
   - Treat a supplied identity value that contradicts the profile as an unresolved verification failure. Ask the customer to correct it or use the approved verification route; do not log verification or take card action while the contradiction remains.
   - Confirm the customer is the cardholder and owner of the linked checking account.
2. Obtain the current time for audit logging and recency calculations.
3. Obtain all customer accounts using `get_all_user_accounts_by_user_id_3847`. This is a documented discoverable agent tool: unlock it first, then call it with `{"user_id":"..."}`.
4. For every OPEN checking account, retrieve all cards using `get_debit_cards_by_account_id_7823` (unlock it first if it is discoverable). Identify all PIN-locked cards, including cards other than the one initially named by the customer.
5. Retrieve transactions for every account linked to a PIN-locked card with `get_bank_account_transactions_9173` (unlock first if needed). Retain declined PIN attempts, successful ATM/PIN history, successful transactions from the prior seven days, and overdraft fees. The documented transaction lookup may not expose PIN-decline records or location/time details; obtain only fields available in the authorized runtime and mark unavailable flags as not applicable rather than guessing.
6. Check card history and account/card security fields returned by the authorized runtime. Never manufacture lock history, a lock reason, fraud alerts, velocity blocks, PIN-use times, transaction locations, or an unlock capability.

The documented card lookup lists card identity, status, issue reason, issue date, and ATM limit. The PIN-lock protocol may require additional card fields (for example `pin_locked`, `pin_lock_reason`, lock history, or security flags). Use such fields only if the normal authorized lookup actually returns them. If they are unavailable, explain internally that the assessment is incomplete and route to the appropriate security/supervisor review rather than assuming a favorable result.

## Automatic escalation and multi-card handling

Before scoring each card, check these conditions:

- `pin_lock_reason == "security_hold"`: do not unlock that card; offer a security-team transfer.
- More than one card on the account is PIN-locked: investigate and score **all** locked cards before any unlock decision. Never unlock the first card merely because it was the one the customer mentioned.
- A card replaced for `issue_reason == "stolen"` in the preceding 90 days: require enhanced verification before an otherwise eligible unlock decision.

A security hold routes directly to security. The presence of several locked cards requires a complete per-card investigation. A recent stolen replacement requires enhanced verification in addition to the ordinary fraud evaluation.

## Internal scoring

Normalize authorized observations into the JSON schema accepted by `scripts/score_pin_lock.py`, then run the script once per locked card. The script returns an internal flag breakdown, total, threshold routing, automatic conditions, and customer questions. It is an aid to applying the protocol, not evidence that an action was completed.

```json
{
  "now": "2025-01-31T15:00:00-05:00",
  "card": {
    "card_id": "authorized runtime value",
    "date_issued": "2024-03-01",
    "daily_atm_limit": 500,
    "pin_lock_reason": null,
    "prior_pin_locks_90d": 0
  },
  "account": {
    "date_opened": "2020-01-01",
    "balance": 600,
    "address": {"city": "Home city", "state": "ST", "country": "US"}
  },
  "declined_attempts": [],
  "successful_transactions": [],
  "last_successful_pin_use": null,
  "other_cards": [],
  "overdraft_fee_count": 0,
  "stolen_replacement_within_90d": false
}
```

Dates may be ISO-8601 or `MM/DD/YYYY`; amounts may be signed or unsigned. Declined and successful transaction entries may include `timestamp` (or `date`), `amount`, and a `location` object with `city`, `state`, and `country`. A successful transaction may include `is_pin_use: true`; ATM withdrawals use `type: "atm_withdrawal"`. Other card entries may include `pin_locked`, `velocity_blocked`, `fraud_alert_active`, `issue_reason`, and `date_issued`.

Example invocation through the Skill runtime:

```text
run_skill_script(
  relative_path="scripts/score_pin_lock.py",
  input_json=<normalized internal assessment JSON>
)
```

The script deliberately returns `not_applicable` flags for missing evidence. Review these manually: absence of data is not a zero-risk finding. If material evidence required for a safe decision is unavailable, do not unlock; obtain the data through an authorized source or transfer for review.

Apply the returned routing as follows:

- 0–4: standard identity verification is required before an unlock.
- 5–7: ask, “I see failed PIN attempts on your card. Were those attempts yours?” before any unlock.
- 8–10: ask the location/time questions indicated by the flags. Unlock only when the customer confirms and gives a satisfactory explanation.
- 11–14: do not unlock in this interaction; require callback verification or enhanced verification (last four SSN plus security question).
- 15+: do not unlock. Review for successful unauthorized activity and recommend closure/replacement.
- Any three-point flag requires supervisor review regardless of total. Three or more prior locks require PIN reset, not unlock.

When the customer confirms a flagged location, remove the location flags and recalculate. When they confirm the declining amount sequence, remove the amount-pattern flag and recalculate. When they confirm a flagged time, remove the time-of-day flag and recalculate. If they say they were asleep or otherwise deny a 2+ point time-of-day attempt, treat it as a critical fraud concern; do not unlock and transfer to security. Record only authorized, relevant answers.

Use neutral customer language such as “I need to review recent card activity for security” and ask only the exact relevant questions returned by the script. Do not tell the customer the score, flag points, internal thresholds, or calculation method.

## Completing an eligible decision

An eligible result is not permission to invent an unlock operation. Use an authorized normal banking unlock tool only if it is actually supplied and its prerequisites are met. If no such tool is documented or available, explain that the card needs authorized servicing and transfer to the appropriate security/specialized team rather than attempting a PIN reset as a substitute.

For every actual banking action, verify identity, ownership, account/card status, applicable limits, card details, and confirmation requirements immediately before the action. Preserve the mandatory control above with the action record.

After an authorized unlock:

- With zero prior locks, complete the standard unlock.
- With one prior lock, offer PIN-lock notifications.
- With two prior locks, offer a PIN reset because this is the third lock in 90 days.
- With three or more prior locks, do not unlock; reset the PIN only through the separate PIN-reset procedure.

A PIN reset requires verified ownership, an ACTIVE card, confirmation of the card last four digits, and a new compliant four-digit PIN. Do not request a new PIN unless performing that authorized reset flow; never read a PIN back.

## Cases that cannot be unlocked

For security holds, critical/very-high outcomes, denied suspicious activity, unresolved identity verification, or incomplete material evidence, do not perform an unlock. Review authorized transaction history for successful unauthorized transactions during the suspicious period. If unauthorized transactions are identified, follow the authorized dispute, closure, and replacement process. Otherwise offer the applicable security investigation, replacement/closure, or PIN-reset option. Use `transfer_to_human_agents` with `fraud_or_security_concern` when a security-team/supervisor review is required and no more specific authorized servicing path is available.

## Validation checklist

Before ending the case, confirm internally that:

- every PIN-locked card was identified and, when multiple are locked, assessed before any unlock;
- automatic triggers, card/account status, ownership, and verification were checked;
- each score uses only authorized observations and missing material evidence was not treated as safe;
- all required customer questions were asked and any confirmed flags were recalculated;
- no score/calculation was disclosed; and
- any banking action was authorized, logged, and followed by the correct post-unlock requirement.
