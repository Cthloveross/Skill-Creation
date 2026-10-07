---
name: banking-email-profile-update-or-human-transfer
description: Handle a banking customer's request to change the email on an account, including identity-verification prerequisites, collection and validation of a replacement email, safe use of the normal email-change tool, and transfer when the customer asks for a human or cannot provide required information.
---

# Email profile update or human transfer

Use this Skill for a request to update an account email address. Account changes require standard identity verification before discussing or modifying account details. A new email address is required to complete the change.

## Required inputs at execution time

Use the live conversation and normal banking tools. Do not rely on identifiers or personal data from an earlier execution.

Collect or determine:

- the customer's identifying information sufficient to find one account record;
- the requested replacement email address;
- whether the customer has passed the required identity check; and
- whether the customer has requested a human agent.

## Workflow

1. **Honor a request for a human.** If the customer asks to be transferred, do not continue to pressure them for the new email or make an account change. Call `transfer_to_human_agents` with:
   - `reason`: `customer_requests_human_no_specific_reason`, unless a more specific applicable reason is established;
   - `summary`: a concise factual description of the requested profile change, what information was unavailable or what was attempted, and that the customer requested a human.

   A request for a human after an unavailable required item is still a human request; it is not a completed email update.

2. **Locate the customer cautiously.** When no transfer is requested, use a supplied name or current email with the matching normal lookup tool. If lookup produces no unique record, ask for another permitted identifier or offer transfer. Never infer that an email belongs to the customer merely because it was supplied.

3. **Verify identity before account discussion or change.** Retrieve the identified customer's record and have the customer confirm at least two of the four identity fields: date of birth, existing email, phone number, and mailing address. Do not reveal unconfirmed values as a verification prompt. After two fields are confirmed, call `get_current_time` and then `log_verification` with the complete retrieved record and that timestamp.

4. **Obtain the replacement address.** Ask for the exact new email address. If it is absent, malformed, or the customer does not have it, explain that the change cannot be completed without it. Do not call `change_user_email` with a blank, guessed, current, or partially supplied address. If the customer wants a human at this point, transfer using step 1.

5. **Validate and update.** Use `scripts/assess_email_change.py` to perform only local format/prerequisite assessment. When it returns `change_email`, call `change_user_email` with the verified `user_id` and exact customer-provided `new_email`. Report the tool outcome without claiming success before the tool succeeds.

6. **Close safely.** For an incomplete request, tell the customer they can return with the new address. The dedicated senior support team can assist with profile updates, including email changes, through the dedicated phone line, secure message topic, or a digital-banking call-back option. Do not invent a phone number. For sensitive communication, recommend secure messaging rather than ordinary email. Never request an online/mobile-banking password or unsolicited one-time passcode.

## Human-transfer reason selection

Use another enum only when its meaning clearly matches the live situation. For example, use `customer_frustrated_demands_human` when frustration is explicitly evident, or `accessibility_or_special_needs` for a transfer driven by an accommodation need. Mere inability to provide a replacement email followed by a request for an agent is `customer_requests_human_no_specific_reason`.

## Local helper

`scripts/assess_email_change.py` reads one JSON object from standard input and writes one JSON object to standard output. It does not call banking tools or change an account.

Input schema:

```json
{
  "user_id": "verified customer id or null",
  "identity_verified": true,
  "new_email": "customer-provided address or null",
  "customer_requested_human": false
}
```

Output `action` is one of:

- `transfer_to_human`: the customer requested an agent;
- `request_new_email`: no usable replacement address is present;
- `complete_identity_verification`: a replacement address is present but verification/user ID is missing;
- `change_email`: prerequisites and basic email format are present.

The helper's output is a recommendation. The executor must still follow the workflow, use normal banking tools, and confirm tool results.

Example runnable call:

```bash
printf '%s' '{"user_id":"u123","identity_verified":true,"new_email":"new@example.com","customer_requested_human":false}' | python3 scripts/assess_email_change.py
```

A valid `change_email` recommendation must include a nonblank `user_id`, `identity_verified: true`, and an email with one `@`, a nonempty local part, and a dot-containing domain. This is basic input validation, not proof of mailbox ownership.
