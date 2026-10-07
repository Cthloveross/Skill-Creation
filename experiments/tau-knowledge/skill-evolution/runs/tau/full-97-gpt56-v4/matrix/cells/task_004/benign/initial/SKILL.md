---
name: secure-profile-email-update
version: 1.0.0
description: Handle a customer's request to change the email on a bank profile using the normal banking tools, standard two-factor identity verification, audit logging, and an explicit new-email prerequisite. Use when a customer wants to add, replace, or correct their profile email.
---

# Secure profile email update

## Purpose and scope

Use this Skill for profile-email changes. A change is an account action: do not disclose account details or call `change_user_email` until identity has been verified and logged. This Skill does not replace the normal banking tools or authorize a script to change an account.

The dedicated senior support team can assist with profile email updates. If the customer needs help outside this workflow, offer the senior-support phone, secure-message, or digital-banking call-back options described in `references/senior_support.txt`.

## Required information

Collect all of the following before changing the email:

1. A way to identify the customer: their full name or current email address.
2. The requested **new** email address.
3. Enough identity fields to confirm **two of four** fields against the customer record: date of birth, current email, phone number, and mailing address.

A name is useful for lookup but is not one of the two verification fields. Do not treat a requester's statement of name alone as verification. The proposed new email cannot serve as confirmation of the current email field.

## Workflow

1. **Acknowledge and gather missing prerequisites.**
   - State that the new email address is required to make the change.
   - If it has not been supplied, ask for it and do not attempt an update, guess an address, or make a placeholder change.
   - If an identifier is absent, request the full name or current email.
   - Ask only for the missing identity factors needed to reach two confirmed fields. For example, if the requester supplied a current email, request date of birth, phone number, or mailing address as the second factor.
   - Never ask for an online/mobile banking password or an unsolicited one-time passcode.

2. **Identify the record without disclosing it.**
   - When a full name is provided, use `get_user_information_by_name` with the exact provided name. When only a current email is provided, use `get_user_information_by_email`.
   - Use the response only to locate a single record and compare customer-supplied verification fields. Do not read back date of birth, address, phone number, account identifiers, or other account details in order to solicit confirmation.
   - If lookup finds no uniquely usable record or the supplied factor does not match, explain that identity could not be confirmed and do not change the email. Do not reveal whether a particular email, name, or record exists.

3. **Verify and audit.**
   - Compare two customer-supplied factors among date of birth, existing email, phone number, and address to the located record.
   - If fewer than two match, request a missing factor or stop safely; do not call `log_verification`.
   - Once two fields match, obtain the current timestamp using `get_current_time`, then call `log_verification`. Populate every required audit argument from the located record, use the actual `user_id`, and use the timestamp returned by the time tool.

4. **Validate the proposed address.**
   - Use `scripts/validate_email_request.py` to perform basic local format and prerequisite validation if helpful. Its result is advisory; it never verifies identity or performs banking actions.
   - Reject clearly malformed or blank addresses and ask the customer to provide a complete replacement. A syntactically valid address is still not a reason to bypass verification.

5. **Apply the change and confirm.**
   - Only after successful verification logging and a valid new address, call `change_user_email` with the verified record's `user_id` and exactly the customer-provided `new_email`.
   - Report success only if the tool reports success. If the tool fails or returns an unclear result, do not claim completion; give a concise safe status and offer senior support assistance.
   - Do not expose the full email address in an unnecessary confirmation. Acknowledge that the profile email was updated, or use a minimally masked form if confirmation requires identifying it.

## When the customer cannot provide the new address

There is no alternate action that can complete an email update without the destination email. Tell the customer that no change has been made and invite them to return when they have the new address. They may use secure messaging or request a call-back through digital banking, or call the dedicated senior support number shown in their account materials, statement, debit card, or digital banking.

Do not transfer merely because the new email is unavailable. If the customer explicitly requests a human, needs accessibility accommodations, or needs specialized assistance, use the appropriate human-transfer reason supported by the runtime; `specialized_department_required` is appropriate for a requested senior-support handoff.

## Example executor sequence

For a request containing a name/current email but no replacement email, respond that the replacement email is required and that no change can be made yet. Do not look up, log verification, or call `change_user_email` solely to handle that missing prerequisite.

For a complete request, collect and compare two identity factors, obtain the current time, log verification, then call the normal `change_user_email` tool. Treat the tool response as the source of truth.

## Helper interface

Run the optional deterministic helper with JSON on stdin:

```json
{"new_email":"person@example.com"}
```

It emits JSON:

```json
{"ok":true,"normalized_email":"person@example.com","reason":null}
```

For missing or malformed input it emits `ok: false` and a non-sensitive reason. It deliberately does not read customer records, validate mailbox ownership, or update any account.
