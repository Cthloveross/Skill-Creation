---
name: senior-support-profile-email-update
version: 1.0.0
description: Handle a customer's request to change a profile email when dedicated senior support applies. Use for secure email updates, identity-verification requirements, and a requested human transfer.
---

# Senior-support profile email update

Use this Skill for a customer seeking to change the email address on their profile. Dedicated senior support can help with profile updates, including email, and offers phone, secure-message, and call-back routes. It requires standard identity authentication before account details are discussed.

## Safety and prerequisites

1. Do not disclose account details or change the email until identity has been authenticated.
2. Obtain the customer's full name and intended new email address. Confirm the email address carefully.
3. Locate the customer record using the normal banking lookup tools only after obtaining enough identifying information to search.
4. Ask the customer to independently confirm at least **two** of these fields: date of birth, current email, phone number, and mailing address. Do not reveal the stored values as prompts.
5. Compare the supplied values to the customer record. If two fields match, get the current timestamp and call `log_verification` with the complete required record fields and timestamp. The audit call is required before changing the email.
6. Check whether the proposed email belongs to another customer using `get_user_information_by_email`. If it is already associated with a different user, do not overwrite it; explain that the address cannot be used and request another email or transfer if asked.
7. Once verification is logged and the email is available, call `change_user_email` with the verified `user_id` and the requested new email. Confirm only that the profile email was updated; do not unnecessarily repeat sensitive account data.

The supplied `scripts/plan_email_update.py` helper can be used to validate email format and select a safe next action. Its output is a recommendation only; the executor must perform banking actions through the declared banking tools.

## Human-agent handoff

If the customer explicitly asks to speak to or be transferred to a human after the issue has not been resolved, do not continue troubleshooting or ask further verification questions. Call `transfer_to_human_agents` with:

- `reason`: `customer_frustrated_demands_human`
- `summary`: a concise, factual summary of the email-update request, information already collected, verification status, checks attempted, and that the customer requested a human agent.

If the customer requests a human without indicating frustration or an unresolved attempt, use `customer_requests_human_no_specific_reason` instead. Do not claim an update, verification, or account eligibility that did not occur.

## Contact guidance when an update cannot be completed in-session

Direct the customer to the dedicated senior support number on their account materials, debit card, or online/mobile banking; secure messaging in digital banking using the Senior Support topic; or a digital-banking call-back request. If they cannot find the number, they can send a digital-banking message asking to be connected to senior support. Remind them that support will authenticate them and that the bank never asks for an online/mobile-banking password.

## Runtime helper

Run:

```json
{"request_type":"email_update","new_email":"customer-provided@example.com","authenticated_fields":0,"verification_logged":false,"email_is_available":null,"requested_human":false,"unresolved":false}
```

with `scripts/plan_email_update.py`. Input fields:

- `request_type`: must be `email_update` for this workflow.
- `new_email`: requested address, if supplied.
- `authenticated_fields`: number of independently confirmed identity fields that matched the record (0–4).
- `verification_logged`: whether `log_verification` succeeded for this request.
- `email_is_available`: `true`, `false`, or `null` if not yet checked.
- `requested_human`: whether the customer requested a human.
- `unresolved`: whether prior attempts have not resolved the request.

The script writes JSON with `action`, `reason`, and `message`. Valid actions are `transfer_to_human`, `collect_identity`, `log_verification`, `check_email_availability`, `request_different_email`, `change_email`, and `reject_invalid_input`.

Before finalizing, ensure the tool result for `change_user_email` is successful. If it fails or is ambiguous, do not retry blindly; give the supported contact routes or transfer the customer if requested.
