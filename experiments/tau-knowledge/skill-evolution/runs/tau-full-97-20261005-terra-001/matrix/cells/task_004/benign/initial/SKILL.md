---
name: verified-email-profile-change
version: 1.0.0
description: Safely handles a request to change an account email address. Use after receiving a requested email and account locator, when account lookup, identity verification logging, and email-change tools are available. It validates the request, requires two matching identity fields before any profile change, and routes incomplete verification to dedicated senior support when applicable.
---

# Verified email profile change

Use this Skill for a customer who wants to replace the email address on an existing account. A name, user ID, or claimed current email may locate an account, but is **not** by itself sufficient authorization to change it.

## Required security rule

Before discussing account details or changing an email, verify **two out of these four** fields against the located account record:

1. date of birth;
2. current email address;
3. phone number;
4. mailing address.

The customer's full name and user ID are locators, not part of the two-field verification threshold. Never count an asserted value that does not match the account record. Do not disclose stored identity values merely to help the customer guess them.

Never request an online/mobile banking password or an unsolicited one-time passcode. Prefer secure messaging or the bank's authenticated support channels for sensitive information.

## Runtime inputs

Collect at runtime:

- the requested new email address;
- a locator: full name, current email, or user ID;
- customer-supplied verification assertions, if any; and
- account lookup and requested-email availability lookup results.

`public_inputs` from a prior incomplete interaction can be used as conversation history, but values from tool results are the authoritative account record. Do not hardcode account IDs, names, addresses, emails, or any other values from a prior case.

## Procedure

1. **Clarify the request.** Ask for the new email and one locator if either is missing. Explain that standard identity verification is required before the change.
2. **Locate the account.** Use the available read-only lookup corresponding to the locator (`get_user_information_by_id`, `get_user_information_by_name`, or `get_user_information_by_email`). If no unique account is found, request a different locator or route to support; do not attempt a change.
3. **Validate the new address and its availability.** Check basic syntax and use `get_user_information_by_email` for the requested new email. It must not be assigned to a different account. If it is already assigned, ask for another email. If it is the same as the located account's current email, explain that no email change is needed; do not call the change tool.
4. **Assess identity assertions.** Compare only customer-provided values with the located record. Use `scripts/assess_email_change.py` to make the comparison auditable and to identify which additional verification field is needed. Provide only the profile values and assertions already obtained through authorized runtime tools/conversation.
5. **If fewer than two fields match, stop.** Do not call `log_verification` or `change_user_email`. Ask for one of the remaining verification fields without revealing the stored value. If the customer cannot provide a matching field or asks for another supported verification route, offer the dedicated senior support channel when the customer is eligible. That team can assist with profile updates and will perform standard authentication. Use the dedicated number shown in account materials, on the back of the debit card, or in digital banking; alternatively use secure-message Senior Support or request a digital-banking call-back. If an in-session transfer is needed, call `transfer_to_human_agents` with reason `specialized_department_required` and summarize that the request is an email profile update blocked by incomplete standard verification. Do not include unnecessary sensitive values in the summary.
6. **Log successful verification.** Once at least two qualifying fields match, call `get_current_time`, then call `log_verification`. Supply the complete values from the authoritative located account record, the account user ID, and the obtained timestamp. This tool is an audit record and must precede the profile update.
7. **Perform and confirm the update.** Call `change_user_email` with the located account's user ID and the validated, available requested email. Only state that the email was changed after a successful tool response. If the tool errors, do not claim completion; preserve the verified status as appropriate and route to support for resolution.

## Current incomplete-case handling

When a customer has supplied only one matching verification field and either gives an incorrect claimed current email or says they do not have the other requested fields, verification remains incomplete. A new email being unassigned does not count as identity verification. Do not infer a match from the customer name, a lookup result, or a desired-email availability check. Use the incomplete-verification path above.

## Helper script

Run the assessor with JSON on stdin:

```json
{
  "profile": {
    "user_id": "runtime account id",
    "date_of_birth": "MM/DD/YYYY",
    "email": "current@example.com",
    "phone_number": "555-0100",
    "address": "mailing address"
  },
  "assertions": {
    "date_of_birth": "optional customer-supplied value",
    "email": "optional customer-supplied value",
    "phone_number": "optional customer-supplied value",
    "address": "optional customer-supplied value"
  },
  "new_email": "requested@example.com",
  "new_email_availability": "available"
}
```

```text
python scripts/assess_email_change.py < input.json
```

`new_email_availability` is one of `available`, `taken`, or `unknown`, based on the runtime email lookup. The script writes one JSON object containing the number and names of matching fields, asserted mismatches, unprovided fields, new-email validation, and a safe recommended next state. It intentionally does not echo account values or customer assertions.

Validate the result as follows:

- `verification.verified` must be `true` before logging or changing the email.
- `email_change.permitted` must be `true` before calling `change_user_email`.
- A result containing `input_errors` is incomplete input; correct it rather than treating it as verified.

The script is decision support only. It does not invoke banking tools, disclose data, create audit logs, or change an account.
