---
name: senior-support-email-update-escalation
description: Handle a customer who wants to update their account email but cannot provide the exact replacement address and requests human help. Route them to the dedicated senior support team using the normal human-transfer tool without attempting an incomplete profile update.
---

# Senior Support Email Update Escalation

## When to use
Use this Skill for an email/profile-update request when all of the following apply:

- The customer needs to change an email address on an account.
- The exact new email address required for the update is not available or not provided.
- The customer asks to speak with, be transferred to, or otherwise receive help from a human agent.
- The customer has access to the dedicated senior support service, which handles profile updates including email changes.

## Operating procedure

1. Review the conversation for the requested new email address. Do **not** infer, invent, substitute a phone number for, or reuse an incomplete new email address.
2. Do not call `change_user_email` unless the customer has supplied the exact replacement email and the applicable identity-verification process has been completed.
3. Because the email update cannot be completed with the information available and the customer has requested human help, transfer the customer to the dedicated senior support team.
4. Call `transfer_to_human_agents` with:
   - `reason`: `specialized_department_required`
   - `summary`: a concise, factual summary stating that the customer wants to update their account email, provided the currently registered email if they volunteered it, does not have the exact new email address available, and requested human assistance/dedicated senior support. State that no email change was made.
5. Tell the customer that they are being connected with the dedicated senior support team. Explain that the team can help with profile/email updates and will perform standard identity verification before discussing account details or making changes. Do not expose account data in the response.

## Important safeguards

- A phone number is not a replacement email value. It may only be relevant to identity verification or contact preferences if the human support process requests it.
- Never make a profile change with a missing, guessed, malformed, or ambiguous replacement value.
- Do not retrieve additional account information merely to complete an escalation when the customer has not supplied what is needed for the requested change.
- If an email update is to be performed directly in a different case, first verify identity using the supported process: confirm two of the four identity fields (date of birth, email, phone number, address), retrieve the matching user record through an authorized lookup, obtain the current time, and call `log_verification` with the complete required audit fields before changing the email.
- Never ask for or accept an online/mobile-banking password or an unsolicited one-time passcode.

## Tool contract

This Skill uses the normal banking tool directly; no local script performs or authorizes the transfer.

`transfer_to_human_agents` input:
```json
{
  "reason": "specialized_department_required",
  "summary": "Customer requests help updating account email. They do not have the exact new email address available and requested transfer to dedicated senior support. No email change was made."
}
```

Replace the summary wording with facts from the live conversation. Do not add account identifiers, unverified assertions, or invented contact information.

## Validation before finishing

Confirm that:

- the live request includes a human-transfer request;
- no exact new email is available for a direct update;
- no `change_user_email` call was made;
- the transfer reason is `specialized_department_required`;
- the transfer summary accurately says what was attempted and that no change occurred; and
- the customer-facing response sets the expectation of standard identity verification by senior support.
