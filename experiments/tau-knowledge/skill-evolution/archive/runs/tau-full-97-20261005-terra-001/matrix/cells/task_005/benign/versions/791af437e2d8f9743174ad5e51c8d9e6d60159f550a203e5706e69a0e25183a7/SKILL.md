---
name: credit-card-balance-identity-and-product-match
description: Verify a customer before discussing a credit-card balance, match the requested card product to the authenticated customer's accounts, and safely handle a requested card product that is not found. Use for credit-card balance inquiries when the customer supplies identifying details or there is a possible card/profile mismatch.
---

# Credit-card balance identity and product matching

## When to use
Use this Skill for a customer asking for the balance of a particular credit-card product, especially when prior lookup results show a different product, an absent account, or conflicting contact details.

## Rules
1. Treat lookup output as evidence, not as permission to disclose account data. Identity verification requires the customer to confirm **two of these four fields** against the retrieved profile: date of birth, email, phone number, and address.
2. A field is verified only when the customer supplied or confirmed it and it matches the retrieved profile. Do not count a name, user ID obtained from a lookup, a failed lookup, or an agent-read profile value as one of the two fields.
3. Once two fields match, get the current timestamp and call `log_verification` with every required field copied from the retrieved customer profile and that timestamp.
4. Use `get_credit_card_accounts_by_user` for the authenticated `user_id`. Match the requested product to the returned `card_type`; do not infer a product from transactions, rewards, or the existence of another card.
5. Disclose a balance only after verification and only for an account belonging to the verified customer. If the requested product is absent, clearly say it was not found on that profile. Do not substitute a different card or disclose that card's balance unless the customer asks for that card's balance after verification.
6. Do not use payment, card-number, account-change, or application tools for a read-only balance request.

## Runtime procedure

1. **Resolve a profile.** Use a supplied name, user ID, or email with the corresponding lookup tool. If a supplied identifier has no record, say it did not match and request another registered identifier; do not claim that it proves account ownership.
2. **Verify identity.** Compare customer-confirmed identity values to the resolved profile. If fewer than two of email, phone, address, and date of birth match, request only the number of additional fields needed. Never reveal the profile value as a hint.
3. **Audit verification.** When two matching fields are available, call `get_current_time`, then `log_verification` using the full resolved profile and the returned timestamp.
4. **Retrieve and match accounts.** Call `get_credit_card_accounts_by_user` if a current account lookup is needed. Select only accounts whose `card_type` matches the requested card product.
5. **Complete the inquiry.**
   - One matching account: state the requested card product and its current balance.
   - No matching account: state that no requested-product account was found under the verified profile. If another product is present, it is acceptable to identify its product name, but ask whether the customer wants its balance rather than volunteering its amount.
   - Multiple matching accounts: identify the ambiguity without disclosing balances and ask the customer to identify the intended account using a non-sensitive differentiator available in the account view.
6. **If verification cannot be completed**, do not disclose account or balance information. Ask for another verification field or a different registered identifier.

For the supplied interaction history, process the newly supplied phone number as a customer-confirmed field by comparing it to the already resolved profile. Also count any previously customer-confirmed registered email only if it matches that same profile. Do not treat an unmatched email attempt as verification. After the required two-field verification and audit, the account lookup result remains authoritative: a card product absent from the account list must not be represented as present.

## Deterministic helper

`scripts/assess_balance_inquiry.py` checks which customer-confirmed identity fields match a retrieved profile and evaluates whether the requested product has zero, one, or multiple matching accounts. It does not call banking tools and never creates a verification audit record.

### Input JSON
```json
{
  "customer_record": {
    "user_id": "string",
    "name": "string",
    "email": "string",
    "phone_number": "string",
    "address": "string",
    "date_of_birth": "MM/DD/YYYY"
  },
  "confirmed_identity": {
    "email": "string optional",
    "phone_number": "string optional",
    "address": "string optional",
    "date_of_birth": "string optional"
  },
  "requested_card_type": "string",
  "accounts": [
    {"account_id": "string", "user_id": "string", "card_type": "string", "current_balance": "number or string"}
  ]
}
```

### Output JSON
The helper emits `verified_fields`, `verification_complete`, `matching_account_count`, `decision`, and `next_step`. A `decision` of `need_identity_field` means no balance may be disclosed. `requested_card_absent` means do not substitute another card. `one_requested_card` permits disclosure only after the executor has logged verification.

Example runnable call (with runtime-provided data):
```sh
python3 scripts/assess_balance_inquiry.py < inquiry.json
```

Validate that (a) every reported verified field was actually provided in `confirmed_identity` and matched the record, (b) `verification_complete` is true only with at least two matching fields, and (c) every account counted as a match has both the authenticated `user_id` and the requested `card_type`.
