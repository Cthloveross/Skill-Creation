---
name: verified-profile-email-update
description: Safely update a customer's account email using the available banking tools after confirming two of the four permitted identity fields (date of birth, current email, current phone number, or mailing address), logging the successful verification, and handling unavailable verification through the proper human-transfer reason.
---

# Verified Profile Email Update

Use this Skill for a customer-requested change to the email address on an existing account when the runtime provides user lookup, verification logging, and email-change tools.

## Safety and authorization rules

- Treat the requested **new** email address as a requested change, never as proof of identity.
- Before discussing account details or changing the email, confirm **at least two of these four fields** against the located account: date of birth, current email, currently registered phone number, and mailing address.
- A name is useful for locating a record but is not one of the four verification factors.
- Do not reveal a stored date of birth, address, current email, phone number, user ID, password, or one-time passcode in order to help the customer pass verification. Ask the customer to provide a factor and compare it privately.
- Never request an online/mobile-banking password or an unsolicited one-time passcode.
- Only call `log_verification` after two factors match. Use values from the located record to populate all required log fields and use a current timestamp from `get_current_time`.
- Only call `change_user_email` after the verification log succeeds.

## Runtime workflow

1. Obtain the requested replacement email. If it is missing, ask for it. Confirm it is plausibly formatted as an email address before attempting a write.
2. Obtain the customer's full name as it appears on the account and look up the account using `get_user_information_by_name`.
   - The name lookup is case-sensitive. If a lookup fails because of harmless surrounding punctuation or whitespace in the customer-provided name, retry using the same stated name with that formatting removed; do not invent alternate names.
   - If no unique account can be located, do not disclose any information. Ask for clarification or transfer once identity/account ownership cannot be resolved.
3. Privately compare customer-supplied verification factors to the located record. Count only matching values among `date_of_birth`, `email` (the existing email), `phone_number`, and `address`.
   - If the customer cannot provide one factor, offer another permitted factor. For example, a customer unable to provide date of birth may provide their currently registered phone number or mailing address.
   - If one supplied factor matches, request one additional permitted factor; a mailing address is an appropriate alternative when date of birth is unavailable.
   - Do not state whether an individual attempted factor matched until the required verification has succeeded. Never give the expected value.
4. At the time two factors have matched, call `get_current_time`, then call `log_verification` with the complete record and that timestamp.
5. If logging succeeds, call `change_user_email` with the located `user_id` and the requested new email.
6. Confirm the outcome concisely. If the target email is already the account email, state that no update was needed after verification rather than issuing an unnecessary change.

## Deterministic verification helper

Use `scripts/verification_gate.py` to consistently evaluate supplied factors and construct the post-verification action sequence. It performs no banking action itself.

### Input JSON schema

```json
{
  "record": {
    "user_id": "string",
    "name": "string",
    "address": "string",
    "email": "string",
    "phone_number": "string",
    "date_of_birth": "MM/DD/YYYY"
  },
  "claims": {
    "date_of_birth": "optional customer-provided value",
    "current_email": "optional customer-provided current email",
    "phone_number": "optional customer-provided phone",
    "address": "optional customer-provided address"
  },
  "new_email": "requested replacement email",
  "time_verified": "current timestamp returned by get_current_time"
}
```

`claims` may omit any factor that the customer has not supplied. `current_email` deliberately distinguishes an existing-email claim from `new_email`.

### Output JSON schema

The helper emits a JSON object with:

- `status`: `verified`, `already_current`, `need_more_verified_factors`, `identity_not_verified`, or `invalid_input`.
- `matched_fields`: factor names that matched; do not expose this list to an unverified customer.
- `remaining_factor_options`: factors that have not yet been supplied, when more proof is needed.
- `actions`: ordered recommended tool calls only when identity is verified. The executor must execute them in order and must stop if a tool call fails.
- `errors`: input/format errors, if applicable.

Runnable invocation (with live runtime data substituted by the executor):

```sh
python3 scripts/verification_gate.py <<'JSON'
{"record":{"user_id":"<id>","name":"<name>","address":"<address>","email":"<current-email>","phone_number":"<phone>","date_of_birth":"<dob>"},"claims":{"phone_number":"<customer-phone>","address":"<customer-address>"},"new_email":"<new-email>","time_verified":"<timestamp>"}
JSON
```

## When verification cannot be completed

If the customer cannot provide enough matching factors, account lookup cannot be resolved, or identity verification fails and specialist handling is required, transfer to a human agent using the highest applicable reason code:

- Use `account_ownership_dispute` for identity-verification failures requiring specialist handling.
- Use another higher-priority code if the conversation independently raises fraud/security, legal, deceased-holder, or other Tier 1 circumstances.

The transfer summary should state only necessary operational facts: the request is an email update, which verification alternatives were offered, that verification was not completed, and that no email change was made. Do not include passwords, passcodes, or unnecessary full identity values.

The dedicated senior support team can assist with profile updates and standard authentication. If normal execution cannot complete the request, direct or transfer the customer to that team through the available approved contact path.

## Completion checks

Before responding that the change is complete, verify all of the following:

1. A unique account record was located.
2. Two permitted identity factors matched.
3. `log_verification` was called successfully with a current timestamp and the complete located record.
4. `change_user_email` was called successfully with that record's `user_id` and the requested email, unless the requested email was already current.
5. The response accurately states whether the update occurred, was unnecessary, or must be handled by a specialist.
