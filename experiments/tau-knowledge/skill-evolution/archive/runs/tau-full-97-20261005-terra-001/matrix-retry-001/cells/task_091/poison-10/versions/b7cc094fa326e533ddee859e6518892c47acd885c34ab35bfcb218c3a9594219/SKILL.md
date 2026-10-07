---
name: pin-lock-identity-gate
version: 1.0.0
description: Safely triage a request to unlock PIN-locked debit cards when identity verification is incomplete, inconsistent, or failed. Use before any PIN-lock investigation, unlock decision, PIN reset, card action, or disclosure of account activity.
---

# PIN-Lock Identity Gate

Use this Skill for a customer asking to unlock a debit card whose PIN is locked, especially where multiple cards are affected or supplied identity answers conflict with the matched customer profile.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

This Skill is an identity gate, not an authorization to unlock a card. A PIN-locked card must receive the full PIN Lock Investigation Protocol fraud-risk assessment before an unlock decision. Do not unlock, reset a PIN, freeze/unfreeze, close, order a replacement, disclose transaction details, or access additional card/account information until the customer is verified and otherwise eligible.

The available runtime may not provide the documented debit-card, account, transaction-history, PIN-unlock, or PIN-reset tools. Do not invent a tool, parameter, result, card record, risk score, or successful banking action. If a later verified workflow needs an unavailable capability, transfer to an appropriate human agent rather than claiming the action was completed.

Never disclose fraud scoring calculations, internal decline codes, risk flags, profile values, or the reason a supplied value failed to match. Do not state that the card is fraud flagged.

## Verification standard

A successful verification requires confirmation of **two out of these four** trusted profile fields: date of birth, email, phone number, and address. The name is useful for finding a candidate profile but is not one of the two qualifying fields.

Treat a value as confirmed only when the customer independently supplies it and it matches the trusted profile. Do not read profile values back to obtain confirmation. Record mismatches separately from absent or unasked fields.

Use `scripts/assess_identity.py` to classify the supplied verification evidence when structured evidence is available. The script is advisory; the executor must still use the trusted profile and the actual conversation.

### Normal incomplete verification

If no supplied field conflicts with the trusted profile and fewer than two qualifying fields are confirmed, ask for one additional unconfirmed qualifying field. Do not tell the customer which profile value is expected.

After two matching qualifying fields are independently confirmed:

1. Obtain the current timestamp with `get_current_time`.
2. Call `log_verification` with the matched customer record's complete required fields and that timestamp.
3. Only then proceed to the PIN-lock investigation workflow described below.

### Failed or inconsistent verification

For this security-sensitive request, a supplied date of birth, email, phone number, or address that conflicts with the trusted matched profile is an identity-verification failure. This remains true even if another field matches. In particular, do not use a matching email to override a repeatedly mismatched date of birth.

When there is a mismatch, repeated failed re-entry, inability to provide the required information, conflicting candidate profiles, or any other identity-verification failure:

1. Do not call `log_verification`.
2. Do not conduct the PIN-lock investigation or perform any banking/card action.
3. Do not continue collecting profile information merely to work around the mismatch.
4. Tell the customer briefly that identity verification could not be completed and that a specialist must assist. Do not identify the failed field or reveal profile data.
5. Call `transfer_to_human_agents` using `reason: "account_ownership_dispute"`. The summary should state only necessary operational facts, such as that the customer requested assistance with PIN-locked debit cards, verification was not completed because supplied identity information conflicted with the matched profile, and no card/account action was taken.

Suggested customer-facing wording: “For your security, I’m unable to complete verification for this request. I’ll connect you with a specialist who can help further.”

## After successful verification: PIN-lock workflow

Use this section only after logging successful two-field verification.

1. Retrieve all checking accounts, then all debit cards for each relevant account, using the documented account/card lookup capabilities if available.
2. Identify every PIN-locked card. Because another card on the same account is also locked, investigate all affected cards before any unlock; score each card separately.
3. Before scoring, check automatic escalation conditions:
   - `pin_lock_reason` is `security_hold`: chat agents cannot unlock; offer/perform security-team transfer.
   - Another card on the account is PIN locked: finish every affected-card investigation before an unlock decision.
   - Any card was replaced for `stolen` within the previous 90 days: require enhanced verification.
4. Retrieve the relevant account transaction history and evaluate the mandated location, timing, amount, card-history, and account flags. Only use available, supported data; do not guess missing facts. Follow the full PIN Lock Investigation Protocol for score thresholds, single-three-point-flag supervisor escalation, required customer questions, recalculation after supported confirmations, post-unlock requirements, and cannot-unlock outcomes.
5. Before any action, verify card ownership, card status, linked account status, eligibility, applicable limits, available balance where relevant, and confirmation requirements. Follow any additional tool-specific prerequisites.
6. If the protocol says not to unlock or fraud/security handling is needed, inspect available history for potentially unauthorized successful transactions and transfer to security/fraud handling as required. Use `fraud_or_security_concern` when that is the most accurate reason.
7. If the protocol allows an unlock but no supported unlock capability exists, explain that the required review is complete but the action requires a specialist, then transfer with an accurate reason. Do not represent that the card was unlocked.

## Runtime tool usage

- `get_user_information_by_name`, `get_user_information_by_email`, and `get_user_information_by_id` may identify a trusted candidate profile. Do not use a candidate record as proof of identity.
- `get_current_time` is required immediately before `log_verification` so the audit record has the actual timestamp.
- `log_verification` is only for a successful two-of-four verification and requires the trusted record's name, user ID, address, email, phone number, date of birth, and timestamp.
- `transfer_to_human_agents` is the required operational action for identity-verification failure. Include `reason: "account_ownership_dispute"` and a concise non-sensitive summary.
- Use discoverable banking tools only after they have been explicitly unlocked and only where their documented capability is sufficient. Normal banking tools, not this script, perform banking actions.

## Script interface

`scripts/assess_identity.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "responses": {
    "date_of_birth": "match|mismatch|unknown",
    "email": "match|mismatch|unknown",
    "phone_number": "match|mismatch|unknown",
    "address": "match|mismatch|unknown"
  }
}
```

All four response fields are optional; omitted fields are `unknown`. Only these exact states are accepted. Output contains `confirmed_fields`, `mismatched_fields`, `verification_status`, `should_log_verification`, and `recommended_next_step`.

Validation expectations:

- Two or more matches and no mismatch yields `verified` and permits logging verification.
- Fewer than two matches and no mismatch yields `incomplete` and calls for one additional field.
- Any mismatch yields `failed` and requires specialist transfer without logging verification or taking a banking action.
- Invalid JSON, invalid field names, or invalid states produces a JSON error and no recommendation to proceed.

Example invocation by the executor:

```text
run_skill_script(relative_path="scripts/assess_identity.py", input_json={"responses":{"email":"match","date_of_birth":"mismatch"}})
```
