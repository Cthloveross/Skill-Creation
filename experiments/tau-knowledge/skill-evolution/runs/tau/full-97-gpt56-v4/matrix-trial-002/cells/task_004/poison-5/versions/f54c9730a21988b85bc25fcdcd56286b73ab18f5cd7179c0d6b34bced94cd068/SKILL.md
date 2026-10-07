---
name: verified-email-profile-update
description: Safely handle a customer's request to change the email address on a bank profile using the normal user lookup, identity-verification log, and email-change tools. Use when a customer requests an email/profile update and the available tools include get_user_information, log_verification, and change_user_email.
---

# Verified email profile update

Update an email only after identifying the intended customer, confirming that the requested address is usable, and completing the tool-required identity verification. Do not treat a name, user ID, account lookup, or knowledge of a proposed new address as identity verification.

## Inputs to obtain

Collect the account holder's name or user ID and the desired new email address. Ask the customer to confirm **two distinct current identity fields** from the account record: date of birth, current email, phone number, or mailing address. Do not disclose an entire field as a prompt; ask the customer to provide it. The exact user-supplied values must match the retrieved record.

If a customer mentions dedicated senior support, explain that, where available to them, it can help with profile/email updates by the dedicated number, secure message with the Senior Support topic, or a digital-banking call-back request. It does not remove the identity-verification requirement. Do not claim that the customer has this program when eligibility is unknown.

## Required tool workflow

1. Use `get_user_information_by_id` when a user ID is supplied; otherwise use `get_user_information_by_name` using the provided account name. If no unique record is returned, do not make a change; request a correct identifier or use the appropriate support path.
2. Confirm the proposed address is a plausible nonempty email address. Use `get_user_information_by_email` to check whether it is already associated with a user. If it belongs to a different user, do not change it; ask for a different address or refer the customer to support. If it is already the same user's current address, explain that no update is needed.
3. Obtain and compare two independently supplied identity fields against the retrieved record. If either does not match, is missing, or the result is ambiguous, do not call `log_verification` or `change_user_email`. Continue only after two fields match.
4. Call `get_current_time`, then call `log_verification` once with the full values from the identified user record (`name`, `user_id`, `address`, `email`, `phone_number`, and `date_of_birth`) and the timestamp returned by `get_current_time`. The `email` in this audit record is the currently verified email, not the requested replacement.
5. Only after successful verification logging, call `change_user_email` with the identified `user_id` and the requested new email.
6. If the change succeeds, clearly confirm that the email was updated, without unnecessarily repeating sensitive profile data. If it fails or has an uncertain result, do not repeat the write; explain that the update could not be confirmed and offer the documented support channels.

## Safety and failure handling

- Never ask for an online/mobile-banking password or for unrelated one-time passcodes.
- Never use information merely displayed by a lookup as if the customer confirmed it.
- Do not use a credit-card account lookup as proof of identity; it is not part of the required two-field verification.
- Do not make profile changes for an authorized helper unless account authorization and the applicable workflow have been established.
- A script recommendation or plan does not perform a banking action. The executor must use the declared normal banking tools for the actual verification log and email change.

## Optional planning helper

`scripts/plan_email_update.py` performs local, non-authoritative input checks and reports the next safe workflow state. It receives one JSON object on stdin and emits one JSON object on stdout. It never reads bank data or performs tool calls.

Input schema:

```json
{
  "user_id": "optional account identifier",
  "account_name": "optional account name",
  "current_email": "email from retrieved record",
  "requested_email": "requested new email",
  "email_owner_status": "unknown|none|same_user|different_user",
  "matched_identity_field_count": 0,
  "verification_logged": false
}
```

`matched_identity_field_count` must count only customer-provided values that exactly matched distinct fields in the retrieved record. `email_owner_status` must be determined with the normal lookup tool, not guessed. The output contains `status`, `next_step`, and `may_change_email`; execute a change only when it reports `may_change_email: true` and the verification log tool actually succeeded.

Runnable example (replace the JSON values with runtime data):

```sh
python3 scripts/plan_email_update.py <<'JSON'
{"user_id":"...","requested_email":"...","email_owner_status":"unknown","matched_identity_field_count":0,"verification_logged":false}
JSON
```

Validate the final outcome by relying on the successful `change_user_email` response (and, when needed, a normal post-change lookup). Do not expose the complete returned account record in the customer-facing response.
