---
name: reconcile-requested-credit-card-balance
description: Resolve a request for the balance of a specifically named credit card when customer lookup by name, email, or user ID may show a different card or no matching card. Use to confirm whether the requested card exists before disclosing a balance or offering next steps.
---

# Reconcile a Requested Credit-Card Balance

Use this Skill when a customer asks for the balance of a particular card product and the available account records may not match the requested product. The key rule is: **do not substitute a different card's balance for the requested card.**

## Method

1. Obtain an account locator from the customer (full name, email address, or user ID) and use the corresponding supported user lookup tool.
2. Resolve one unambiguous user ID. If the lookup returns zero or multiple possible users, request enough information to resolve the ambiguity; do not inspect or disclose account details for a guessed record.
3. Retrieve the credit-card accounts with `get_credit_card_accounts_by_user` using the resolved user ID.
4. Compare the requested card type with every returned `card_type`. Match card labels case-insensitively after collapsing extra whitespace. Use `scripts/reconcile_card_request.py` if structured account data is available.
5. Before stating an account balance or other sensitive account details, follow the applicable identity-verification procedure. Where verification requires confirmation of two identity fields, obtain those confirmations and call `log_verification` with the complete returned user record and a current timestamp.
6. Respond according to the reconciliation result:
   - **One requested-card match:** after required verification, state the balance for that matching account only.
   - **More than one match:** explain that more than one matching account was found and ask which account the customer means (for example, distinguish by date opened). Do not guess.
   - **No requested-card match:** clearly state that no account of the requested card type appears on the resolved profile. Do not invent a balance, eligibility decision, application status, or missing account. If appropriate, state only that another card type is listed and ask whether the customer wants help with that card, subject to verification requirements.
7. If a subsequent lookup by a different locator resolves to the same user ID, treat it as the same profile; it does not establish that a missing requested card exists. If it resolves to a different user, stop and resolve the identity/account-ownership discrepancy before discussing balances.

## Current-case handling

If the conversation already contains a successful user lookup through both the original locator and email, compare their user IDs. When they are the same and the account lookup contains only nonmatching cards, answer the customer's follow-up by confirming that the email resolves to the same profile and that the requested card is not listed. Do not repeat the nonmatching card's balance unless the customer explicitly asks about that card and the required verification is complete.

## Do not use payment workflow tools

This is a balance lookup and reconciliation workflow. Do not unlock or call payment tools unless the customer separately requests a payment and all documented payment prerequisites, including verification, account lookup, sufficient funds, amount confirmation, and authorization, have been met.

## Helper script

`scripts/reconcile_card_request.py` deterministically classifies structured lookup results. It does not call banking tools and does not disclose information itself.

### Input JSON

```json
{
  "requested_card_type": "string",
  "resolved_user_id": "string",
  "alternate_lookup_user_id": "string or null",
  "accounts": [
    {
      "account_id": "string",
      "user_id": "string",
      "card_type": "string",
      "current_balance": "number or string, optional",
      "date_of_account_open": "string, optional"
    }
  ]
}
```

`alternate_lookup_user_id` is optional and represents the user ID returned by a follow-up lookup such as an email lookup. Every supplied account must belong to `resolved_user_id`; the script rejects inconsistent data rather than risking an account mix-up.

### Output JSON

The script emits one of:

- `match_status: "found"` with safe matching account records,
- `match_status: "not_found"` with listed card types, or
- `match_status: "ambiguous"` when multiple requested-card matches exist.

It also emits `lookup_consistency` as `same_user`, `different_user`, or `not_checked`. An `error` output describes malformed or inconsistent input. The executor must still apply identity-verification rules before communicating any returned balance.

Example invocation by the Skill runtime:

```text
run_skill_script(relative_path="scripts/reconcile_card_request.py", input_json={...structured lookup data...})
```

Validate that the result is not `error`, that `lookup_consistency` is not `different_user`, and that the customer-facing response follows the `match_status`. For `not_found`, do not include a balance.