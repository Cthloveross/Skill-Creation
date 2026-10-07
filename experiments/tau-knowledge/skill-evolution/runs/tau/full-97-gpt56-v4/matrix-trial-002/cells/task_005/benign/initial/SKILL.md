---
name: credit-card-balance-inquiry
description: Handle a customer request to view a credit-card balance by resolving the customer, clarifying the intended card, verifying identity with two supported identity fields, logging verification, and then reporting the selected account's current balance. Use for read-only credit-card account balance requests.
---

# Credit-card balance inquiry

Use this Skill when a customer asks for the current balance of a credit card account. It supports read-only balance disclosure; it does not change account data.

## Required workflow

1. **Understand the request.** Identify the requested card type if the customer supplied one. Do not assume that a similarly named card is the intended account.
2. **Resolve the customer record.** Use the identifier the customer provides with the corresponding normal banking tool:
   - `get_user_information_by_email` for an email,
   - `get_user_information_by_name` for an exact full name (case-sensitive), or
   - `get_user_information_by_id` for a user ID.
   If a lookup has no record, tell the customer without exposing any account information and ask for another identifier. If it returns multiple people, ask for an unambiguous identifier rather than selecting one.
3. **Retrieve card accounts.** Once exactly one user record is resolved, call `get_credit_card_accounts_by_user` using that record's `user_id`.
4. **Select the intended account.**
   - If the requested card type is present and unique, use that account after verification.
   - If it is absent, state that it was not found and list only enough card-type information to ask whether one of the returned cards is intended. Do not invent a reason for the mismatch.
   - If the customer confirms a different returned card, use the confirmed card.
   - If no account is returned, explain that no credit-card account was found for the resolved customer.
5. **Verify before disclosing the balance.** Ask the customer to provide any two of these identity fields: date of birth, email address, phone number, and mailing address. Compare each supplied value to the resolved user record. A field counts only when it matches; the name alone does not count as one of the two fields. Do not disclose the balance, reward points, or other account details until at least two fields match.
6. **Log successful verification.** Obtain the current timestamp with `get_current_time`, then call `log_verification` with the resolved record's complete required fields and that timestamp. Log only after two fields have been confirmed. Use `scripts/assess_verification.py` to make the count and normalization decision reproducible if useful.
7. **Report the answer.** After logging succeeds, state the selected card type and its `current_balance` exactly as returned by the account lookup. Be concise. Reward points are not part of a balance request unless the customer also asks about them.

## Failure and safety handling

- Treat a lookup failure, ambiguous user result, absent requested card, and failed identity comparison as unresolved—not as permission to disclose account information.
- If fewer than two fields match, say verification could not be completed and request the missing/correct fields. Never reveal the stored value merely to help the customer guess it.
- If a required normal banking tool errors or logging cannot be completed, do not claim that verification completed or disclose the balance; explain that the request cannot be completed through the current system and use the applicable human-transfer path when needed.
- Do not make account changes for a balance inquiry.
- Do not expose full address, date of birth, email, phone number, user ID, account ID, or other non-requested personal data in the customer-facing response.

## Helper script

`scripts/assess_verification.py` accepts JSON on stdin and emits JSON on stdout. It performs no banking action and does not log verification.

Input schema:

```json
{
  "record": {
    "date_of_birth": "MM/DD/YYYY",
    "email": "customer@example.com",
    "phone_number": "555-555-5555",
    "address": "Street, City, ST ZIP"
  },
  "claims": {
    "email": "...",
    "phone_number": "..."
  }
}
```

`claims` may contain any subset of `date_of_birth`, `email`, `phone_number`, and `address`. The output identifies matched, mismatched, and omitted supported fields and sets `verified` only when at least two fields matched. Email comparison is case-insensitive with surrounding whitespace removed. Phone numbers compare by digits only. Date of birth and address compare after surrounding whitespace normalization and case-folding. The executor must still call `get_current_time` and `log_verification` after a `verified: true` result.

Example runnable invocation:

```sh
python3 scripts/assess_verification.py <<'JSON'
{"record":{"date_of_birth":"MM/DD/YYYY","email":"customer@example.com","phone_number":"555-555-5555","address":"Street, City, ST ZIP"},"claims":{"email":"customer@example.com","phone_number":"5555555555"}}
JSON
```

Validate helper output by confirming that `matched_count` equals the length of `matched_fields`, no unsupported claim is counted, and `verified` is true exactly when `matched_count >= 2`.
