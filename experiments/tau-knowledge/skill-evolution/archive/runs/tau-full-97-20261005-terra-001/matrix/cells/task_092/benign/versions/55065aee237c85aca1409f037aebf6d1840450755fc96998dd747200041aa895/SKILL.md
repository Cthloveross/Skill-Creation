---
name: pin-lock-fraud-assessment
description: Investigate one or more PIN-locked debit cards before any unlock. Use for PIN decline codes 55/75 or a card with pin_locked=true. It orchestrates required account/card/activity retrieval, automatic escalations, internal fraud-risk scoring, verification questions, and eligible post-unlock or fraud-response steps without exposing the scoring method to the customer.
---

# PIN-Lock Fraud Assessment

## Scope and safety rules

Use this Skill only for debit-card PIN locks. A PIN-locked card must **never** be unlocked until this assessment is complete for that card. Do not tell the customer the points, score, flag labels, scoring thresholds, or calculation details.

The executor performs all banking actions using its normal banking tools. This package only calculates and structures an internal assessment; it does not unlock, reset, close, replace, dispute, or transfer a card by itself.

The customer must be identity-verified before card actions. If verification has already been completed during the interaction, log it using the available verification-record process before proceeding with a card action.

## Required runtime investigation

1. Identify the customer and retrieve every account for the customer.
2. For each checking account, retrieve **all** debit cards, including historical cards. Retrieve account transactions for each relevant checking account.
3. Identify every card currently marked `pin_locked=true`; do not rely solely on a customer-provided last four. The card lookup may expose PIN-lock/security fields in addition to its documented identity, status, issue-date, and limit fields.
4. For each locked card, collect and normalize the data required by `scripts/pin_lock_assess.py`:
   - target-card PIN-lock reason, PIN-lock history, issue date, daily ATM limit, status, and owner;
   - all cards and their PIN-lock, fraud-alert, and velocity-block status;
   - account opening date and current balance;
   - declined PIN-related attempts and their timestamp, amount, and location;
   - recent successful transactions, including successful PIN uses and successful ATM withdrawals where available;
   - account transactions, including overdraft fees;
   - the customer's home city/state/country.
5. Run the script once per locked card. When multiple cards are locked, pass all cards on the account each time so the script can identify the multi-card escalation. Finish all individual assessments before any unlock.
6. Treat `assessment_complete=false`, `unknown_inputs`, or `needs_manual_review` as a stop condition for unlocking. Obtain the missing authoritative data or transfer/escalate; do not guess a zero-point result.

### Script invocation

The script reads one JSON object from standard input and emits one JSON object to standard output:

```text
python3 scripts/pin_lock_assess.py < assessment_input.json
```

The full schema is documented in `references/assessment_input_schema.md`. The input must be normalized from live tool results; never embed a customer ID, a case result, or a presumed answer in a saved input file.

## Automatic escalation and assessment handling

Read the `automatic`, `required_next_step`, and `cannot_unlock` output before considering score-based treatment.

- `security_hold`: chat agents cannot unlock. Offer transfer to the security team and transfer with `fraud_or_security_concern` when the customer accepts or specialist handling is required.
- `other_locked_cards`: this is not permission to unlock the selected card. Complete the investigation for every locked card first. Each has an independent result.
- `recent_stolen_replacement`: enhanced verification is required. Obtain the required enhanced verification before any otherwise eligible action.
- `D1` at 3 points: the PIN cannot be unlocked; a PIN reset is required.
- Any single 3-point flag: supervisor/security review is required regardless of the total. Do not unlock pending that review.
- A customer saying they were asleep at the time of a high-risk nighttime attempt is a critical fraud indicator. Do not unlock; review for unauthorized successful transactions and escalate as a security concern.

## Customer conversation and recalculation

For a completed score of 5 or more, ask the customer-facing questions returned in `verification_questions` when their corresponding flag is present. Ask the supplied wording or equivalent wording that preserves the location/time/amount facts, but never disclose the score or internal flag calculation.

Record the response and rerun the script with `customer_confirmations`:

- `location: "confirmed"` removes the location flags as required by the PIN-lock protocol.
- `amount_pattern: "confirmed"` removes only the amount-pattern flag.
- `time_of_day: "confirmed"` removes only the time-of-day flag.
- `"denied"` or `"unknown"` does not remove a flag.
- `time_of_day: "asleep"` makes the result non-unlockable.

For HIGH risk, confirmation alone is not enough: the customer must also provide a satisfactory explanation. The executor records that judgment as `satisfactory_explanation=true` only when genuinely satisfied; otherwise do not unlock. Re-run after any response that changes the flags.

## Result-to-action protocol

Subject to all automatic escalations and required verification:

- **LOW (0–4):** standard identity verification, then unlock only through an available, authorized banking action.
- **MEDIUM (5–7):** ask the required failed-attempt ownership question(s); unlock only after the required response and identity verification.
- **HIGH (8–10):** ask the specific location/time/amount questions. Unlock only if the customer confirms and provides a satisfactory explanation, and no single-flag escalation applies.
- **VERY HIGH (11–14):** do not unlock in this interaction. Require callback verification or enhanced verification.
- **CRITICAL (15+), critical customer response, or a non-unlockable automatic trigger:** do not unlock. Review the suspicious period for successful unauthorized transactions and recommend closure/replacement when fraud is suspected.

If an eligible result requires a PIN reset, follow the PIN-reset procedure: confirm ownership, ensure the card is ACTIVE, obtain card last four and a compliant new four-digit PIN, and use only the normal reset tool documented in the runtime. Never repeat or display a PIN. Do not invent an unlock/reset tool name or parameters if it is not available in the runtime.

For a case where unlocking is prohibited, inspect successful transactions in the suspicious period. If unauthorized transactions are found, follow the debit-card dispute workflow (including its verification, timing, and fraud-category requirements), close/reissue as required by that workflow, and handle replacement under the applicable tier rules. If none are found, explain only that a security review prevents the unlock and offer the permitted options: PIN reset, transfer to security, or closure/replacement where fraud is suspected. Use `fraud_or_security_concern` for security transfers.

## Eligible post-unlock requirements

After a successful eligible unlock, use `post_unlock_requirement`:

- zero prior locks: no additional step;
- one prior lock: offer PIN-lock notifications;
- two prior locks: offer a PIN reset and explain that frequent locks can indicate the PIN is difficult to remember;
- three or more: do not unlock; reset is required.

## Validation

Before any action, confirm all of the following in the script result and live records:

1. The assessed `target_card_id` is the intended, customer-owned PIN-locked card.
2. All locked cards on the account have been assessed.
3. `assessment_complete` is true and no automatic/critical/single-3 escalation blocks the proposed action.
4. The risk-level protocol, required customer questions, and any enhanced/callback verification were completed.
5. The card is eligible for the intended action under the normal banking procedure.
6. The customer-facing reply omits internal calculations, scores, and fraud-detection details.

If authoritative fields are unavailable or contradictory, preserve the script output as internal notes and escalate rather than estimating values.
