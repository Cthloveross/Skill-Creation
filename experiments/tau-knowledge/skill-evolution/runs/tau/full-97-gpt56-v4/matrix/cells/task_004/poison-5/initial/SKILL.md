---
name: verified-email-profile-update
description: Safely change a banking customer's email address using the available user lookup, identity-verification audit, and email-change tools. Use for customer-requested email/profile updates when the customer must be authenticated before account details are discussed or changed.
---

# Verified email profile update

Use this Skill to handle a request to replace the email address on a customer's profile. A name and desired new email identify the request, but **do not constitute identity verification**.

## Required inputs

Obtain at runtime:

- The customer's full name as shown on the account.
- The requested new email address.
- Confirmation of at least two distinct current identity fields chosen from: date of birth, current email address, phone number, and mailing address.

Do not disclose stored account details while asking for verification. Ask the customer to provide the values rather than suggesting them. If an input is missing, ask only for the missing item(s).

## Validation helper

`scripts/validate_email_change.py` validates the requested email format and, when record values and customer-provided confirmations are supplied, determines whether two distinct verification fields match. It is a local decision aid only; it does not access the bank or perform any update.

Example invocation (JSON on stdin):

```json
{
  "new_email": "customer@example.com",
  "confirmations": {
    "date_of_birth": "MM/DD/YYYY",
    "phone_number": "customer-provided phone"
  },
  "record": {
    "date_of_birth": "MM/DD/YYYY",
    "email": "current@example.com",
    "phone_number": "stored phone",
    "address": "stored address"
  }
}
```

The script emits JSON containing `valid_new_email`, `matched_fields`, `verification_sufficient`, and `errors`. Never treat a script error, an absent record, or fewer than two matches as verified.

## Execution workflow

1. Confirm the request is specifically to change the customer's profile email. Collect the full account name and desired new email if they have not already been provided.
2. Ask for two current verification fields (for example, date of birth and phone number). Do not ask for a password or a one-time passcode.
3. Use `get_user_information_by_name` with the supplied full name. If zero records are found, explain that the account cannot be located with that name and request a corrected name. If multiple records are found, do not guess; collect enough information to resolve the customer through the supported process or transfer to human support if the ambiguity cannot be resolved safely.
4. Compare the customer-provided verification values against the returned record. Require exact date-of-birth agreement and sensible normalized comparisons for email, phone, and address. At least two of the four fields must match. Use the helper if useful. Do not reveal which particular value failed.
5. Validate that the requested email is syntactically usable with the helper. If it is invalid, ask for a corrected email. Do not perform an update until both identity and email validation pass.
6. Immediately before logging, call `get_current_time`. Call `log_verification` with the located record's `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and the returned timestamp. This must occur only after two successful customer confirmations.
7. After the verification log succeeds, call `change_user_email` with the verified record's `user_id` and the requested new email. Never substitute an ID supplied only by the customer.
8. Treat a failed, malformed, or unknown update result as not completed. Do not retry an update whose outcome is unknown. If it succeeds, optionally use `get_user_information_by_id` to confirm the email now equals the requested value.
9. Tell the customer only that the email update was completed (or that it could not be completed and what non-sensitive next step is needed). Do not repeat full account details, identity data, account IDs, passwords, or one-time codes.

## Failure and escalation handling

- Fewer than two matching identity fields, conflicting details, or an unresolvable name match: do not log verification and do not change the email. Offer another verification attempt without exposing stored values; transfer to human support if safe resolution is not possible.
- If a required banking tool has a technical failure, use `transfer_to_human_agents` with `technical_system_error` and summarize the requested update and non-sensitive failure state.
- If the customer asks for a person or needs specialized support, transfer with the applicable supported reason (normally `customer_requests_human_no_specific_reason` or `specialized_department_required`).
- Customers may use the dedicated senior support phone line, secure message in digital banking, or a digital-banking callback request for profile-update assistance. Standard authentication is still required before account details are discussed.

## Completion checklist

Before stating completion, ensure all are true:

- The full name lookup resolved one intended record.
- Two of date of birth, current email, phone, and address matched customer-provided values.
- `log_verification` succeeded with the current timestamp and the record's complete fields.
- `change_user_email` reported success for that verified `user_id` and requested email.
- If a follow-up lookup was performed, it shows the requested email.
