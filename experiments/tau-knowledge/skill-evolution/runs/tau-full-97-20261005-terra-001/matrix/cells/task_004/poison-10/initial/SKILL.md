---
name: verified-email-profile-update
description: Safely update a bank customer's account email using the available customer lookup, verification-log, time, and email-change tools. Use for a customer-requested profile email change when the agent must independently verify at least two current identity fields before changing account data.
---

# Verified email profile update

## Scope and safety rules

Use this Skill for a customer who wants to replace the email address on their own account. Senior support may assist with profile updates, but standard authentication is required before account details are discussed or changed.

- Never ask for or accept an online/mobile-banking password or a one-time passcode as verification.
- Treat the requested **new** email as a requested change, not as proof of identity.
- A name is an account locator, not one of the identity fields required by `log_verification`.
- Verification requires two matching fields from the account's current date of birth, current email, registered phone number, and mailing address.
- Do not reveal a stored identity value in order to help the customer answer it. Ask the customer to state the value, then compare it privately.
- Do not make any account mutation until verification was logged successfully.
- Do not claim that an update completed unless `change_user_email` returns success.

## Runtime inputs and tool contract

At runtime, gather the requested email and the customer's account name, then use the banking tools:

- `get_user_information_by_name(customer_name)` locates a candidate record.
- `get_current_time()` supplies the timestamp required for the verification audit record.
- `log_verification(...)` must be called after two identity fields match and before the email change. Its schema requires the complete current account record and timestamp.
- `change_user_email(user_id, new_email)` performs the requested change only after logging succeeds.

The helper at `scripts/evaluate_email_update.py` reads one JSON object from stdin and emits one JSON result to stdout. It does not call banking tools or alter records.

Input schema:

```json
{
  "account": {
    "user_id": "string",
    "name": "string",
    "address": "string",
    "email": "string",
    "phone_number": "string",
    "date_of_birth": "MM/DD/YYYY"
  },
  "claims": {
    "date_of_birth": "optional customer-stated value",
    "email": "optional customer-stated current email",
    "phone_number": "optional customer-stated registered phone",
    "address": "optional customer-stated mailing address"
  },
  "new_email": "requested replacement email",
  "time_verified": "timestamp returned by get_current_time, when available"
}
```

Only the four keys under `claims` count toward authentication. The script normalizes harmless formatting differences in dates, phones, email capitalization, and addresses, but it deliberately does not treat the replacement email or name as a verification field. Its result gives an action status and, once eligible, exact argument objects for `log_verification` and `change_user_email`.

Runnable invocation pattern (with `INPUT_JSON` set to an object following the schema above):

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/evaluate_email_update.py
```

## Procedure

1. **Collect the new email.** Ask for the complete replacement email if not already supplied. Validate it with the helper before proceeding. If it is malformed, ask for a valid replacement email; do not call the change tool.
2. **Locate, do not authenticate.** Ask for the full name exactly as it appears on the account and call `get_user_information_by_name`. A terminal sentence period or comma may be removed before lookup, but do not guess a different name. If lookup returns zero or multiple candidates, do not select a record or disclose any record data; ask the customer to clarify their account name.
3. **Obtain independent verification.** Ask the customer to state one or more of their current registered phone number, mailing address, current email, or date of birth. Compare the statements against the one selected account record. If one field was already verified, request another of the remaining fields. A customer declining one method may choose another of these fields.
4. **Evaluate eligibility.** Provide the record, only customer-stated identity claims, requested new email, and the current-time result to the helper. Do not expose account values contained in the helper's downstream audit payload in the customer-facing reply.
   - `need_valid_new_email`: obtain a corrected new email.
   - `need_additional_identity_field`: ask the customer to state another current identity field. Keep the response generic rather than telling them which attempted field did not match.
   - `need_verification_timestamp`: call `get_current_time`, then rerun the helper.
   - `ready_to_log_and_change`: continue below.
   - `no_change_needed`: after successful verification, tell the customer the requested email is already the account email; do not call `change_user_email`.
   - `unsupported_*` or `invalid_input`: do not mutate the account. Correct the missing/invalid runtime data or follow the transfer rules below.
5. **Audit verification.** For `ready_to_log_and_change`, call `log_verification` with `log_verification_arguments` exactly as returned by the helper. If the log operation fails, stop; do not change the email.
6. **Perform the update.** Once logging succeeds, call `change_user_email` with the helper's `change_user_email_arguments`. If it succeeds, confirm that the email was updated. Do not repeat or volunteer other account details. If it fails, explain that the update could not be completed and retain the failure information for escalation if needed.
7. **Close securely.** Recommend using secure digital banking for sensitive follow-up. Remind customers that support will not ask for their banking password and that unexpected callers should be verified through official contact options.

## Transfer handling

Do not transfer a routine email update merely because it requires verification; continue with the available verification choices. If a transfer is necessary, use the highest applicable reason code:

- Use `account_ownership_dispute` for an identity-verification failure requiring specialist handling, conflicting ownership information, or a joint-account ownership dispute.
- Use `technical_system_error` when a system/tool error prevents completing an otherwise eligible update.
- Use `third_party_inquiry` when a caregiver, attorney, power of attorney, or other representative is requesting account action and authorization must be handled.
- Use `accessibility_or_special_needs` when accommodations require human intervention.
- If the customer simply asks for a person without another applicable circumstance, use `customer_requests_human_no_specific_reason`.
- If none apply, use `other` and include a detailed, factual summary of the request, verification attempted, and blocking condition.

Never characterize a normal request for another verification method as a failure or transfer trigger.

## Validation checklist

Before the mutation, ensure all of the following are true:

1. Exactly one account record was selected through a safe lookup.
2. The replacement email has passed local format validation.
3. At least two independently customer-stated current identity fields matched the selected record.
4. `get_current_time` supplied a nonempty timestamp.
5. `log_verification` succeeded using the selected record's current values.

After the mutation, rely on the `change_user_email` result rather than an assumed state. If successful, give a concise completion confirmation; otherwise, do not state that the profile was changed.
