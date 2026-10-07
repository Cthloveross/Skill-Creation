---
name: travel-checking-account-opening
description: Recommend and, after all eligibility, identity-verification, and consent gates are satisfied, open the checking account that best fits a customer's international ATM-use needs. Use for travel-focused checking-account comparisons and account-opening requests.
---

# Travel checking account selection and opening

Use the supplied product documents and the live banking runtime. Product facts in the task inputs are the source of truth; do not infer benefits, fees, eligibility, or tool arguments that are not documented.

## Required outcome and safety gates

The customer may be given a recommendation without opening an account. Do **not** open an account until all of these are true:

1. The customer has explicitly selected an account class using its full official name ending in `Account`.
2. Identity has been verified by matching **two of four** customer-provided fields (date of birth, email, phone number, address) against the profile, and a verification record has been logged.
3. The customer is at least 18, has no more than four personal checking accounts, and has no checking account closed for cause in the previous six months.
4. Any product-specific opening requirements are met.

Willingness to complete verification is not verification. A name, a profile lookup, or a partial match is not enough. Never reveal profile values merely to solicit confirmation.

## 1. Understand the request and make a transparent comparison

1. Locate the customer only from an identifier they supply (such as their full profile name or email) using the applicable profile lookup tool. If several records match, ask for an unambiguous identifier; do not guess.
2. Identify the trip duration, intended ATM behavior if it is material, and product constraints (for example, an opening-deposit or balance requirement). Do not fabricate an expected number or size of withdrawals.
3. Compare only bank fees that the supplied product materials actually establish. Keep these categories separate:
   - foreign-ATM withdrawal fees;
   - out-of-network ATM fees;
   - third-party ATM operator fees and any documented rebate cap;
   - foreign-transaction or currency-conversion charges, which are not automatically ATM fees.
4. Apply both general checking eligibility and account-specific age, funding, and balance constraints. Exclude an account only for a documented unmet condition; state that condition concisely.
5. If withdrawal counts and amounts are supplied, use `scripts/atm_fee_compare.py` to calculate the documented *bank* component under each candidate's published fee rule. It does not estimate operator surcharges, exchange rates, or unprovided usage.
6. Explain the recommendation and material caveats. If two fee rules could apply to the same transaction based on the documents, disclose both rather than silently assuming one overrides the other. If the user needs an exact lowest-cost answer but has not supplied necessary usage facts, ask for those facts.

Do not recommend an account solely because it has a low fee if its documented opening requirements are unavailable to the customer. Do not treat a special account's fees as applicable unless the customer meets its eligibility.

## 2. Obtain selection and conduct identity verification

If the customer has not yet explicitly selected the recommended account, ask for confirmation using the exact official account-class name. In the same concise turn, ask them to provide any two of: date of birth, email address, phone number, or street address exactly as held on their profile. Do not prefill the answer with sensitive profile data.

After the customer responds:

1. Retrieve the identified profile again with the normal lookup tool as needed.
2. Compare at least two customer-supplied identity fields with the profile. Fields must match; do not count a field that the customer did not actually provide or one that conflicts.
3. If two fields match, call `get_current_time`, then call `log_verification` with the complete profile fields, profile user ID, and that exact returned timestamp. Log only after successful matching.
4. If fewer than two fields match, explain that verification is incomplete and request the missing/correct fields. Do not log and do not open the account.

## 3. Check eligibility immediately before opening

Use the verified profile date of birth and current date to confirm the customer is at least 18. Confirm the checking-account-count and closure-for-cause conditions from the customer’s clear attestation or a documented normal banking record tool when available. If a required condition is unknown, contradictory, or fails, do not open the account; explain the blocking condition.

Reconfirm product-specific requirements relevant to the selected account (such as age band, required opening deposit, or required balance). A customer statement that they cannot meet a requirement is a failure of that option, not a request to bypass it.

## 4. Open only after all gates pass

The documented account-opening action is `open_bank_account_4821`.

1. Unlock it with `unlock_discoverable_agent_tool`.
2. Read the unlocked tool's required argument schema and use only those documented arguments. Do not invent argument names or substitute a nickname for the official account class.
3. Call it through `call_discoverable_agent_tool` only once all gates above pass, using the verified customer and the explicitly selected official account class.
4. Treat the tool response as authoritative. If it reports a failure, eligibility failure, or `UNKNOWN` status, do not retry the action. Tell the customer the account was not confirmed as opened and, if available, convey the safe next step from the result.

The recommendation or a script result never opens an account; only the normal banking tool can do that.

## 5. Close the interaction accurately

After a successful opening response, confirm the official account class and only the account details returned by the opening tool. Reiterate important documented ATM-fee caveats (including separate operator surcharges and rebate caps) without claiming reimbursement that was not documented. If the account cannot be opened, offer the closest documented eligible alternative or explain what information/action is required next.

## Fee-calculator script

`scripts/atm_fee_compare.py` reads JSON on stdin and emits JSON on stdout. It is a generic calculator for published bank-fee rules, not a product catalog.

Input schema:

```json
{
  "withdrawals_by_month": [[100.0, 250.0], [80.0]],
  "offers": [
    {
      "name": "Official Account Name",
      "eligible": true,
      "fee_rule": {
        "kind": "percentage_min_max",
        "percentage": 0.03,
        "minimum": 5.0,
        "maximum": null
      }
    }
  ]
}
```

Supported `fee_rule.kind` values are `flat`, `percentage_min_max`, `tiered`, and `free_allowance_then_flat`. Values in `withdrawals_by_month` are positive USD-equivalent amounts, with each inner list representing one calendar month. `tiered` rules use ordered `{ "up_to": number-or-null, "fee": number }` tiers. `free_allowance_then_flat` uses `free_count` and `fee_after_free`. Set `eligible` to false to exclude an offer from ranking while retaining an explanatory result.

The output contains each offer's monthly and trip bank-fee totals, any validation errors, and a stable ranking of eligible valid offers. Before relying on a comparison, check that the input models every documented fee component relevant to the requested comparison.
