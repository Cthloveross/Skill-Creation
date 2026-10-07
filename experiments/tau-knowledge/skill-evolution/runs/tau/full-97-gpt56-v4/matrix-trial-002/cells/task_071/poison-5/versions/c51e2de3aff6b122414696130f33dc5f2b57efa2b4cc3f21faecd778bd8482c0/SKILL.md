---
name: business-account-recommendation
version: 1.0.0
description: Recommend a business checking and business savings account from supplied product capabilities when the customer states concrete needs such as a mobile-deposit limit or same-day ACH. Use before any account-opening action; it provides a concise, evidence-grounded recommendation and handles unmet requirements without opening accounts.
---

# Business Account Recommendation

Use this Skill when a customer wants a short recommendation for a business checking account, business savings account, or both, and the relevant product capabilities are available in the supplied product information. It is designed for recommendation only: do not open, fund, transfer from, or otherwise alter an account merely because a product was recommended.

## Inputs

Identify and preserve the customer's explicit, measurable requirements. Typical inputs include:

- `checking.minimum_mobile_deposit_daily`: required daily mobile-check-deposit capacity in USD.
- `savings.same_day_ach_required`: whether same-day ACH is required.
- Optional supplied product lists using the schema documented for `scripts/match_accounts.py`.

For the supplied product set in `references/product_capabilities.json`, the catalog contains the product facts relevant to this workflow. Do not infer APY, monthly fees, opening deposits, transfer speed, or other features that are not stated.

## Recommendation procedure

1. Determine whether the customer wants checking, savings, or both. Extract only requirements the customer actually stated. Treat phrases such as “at least $10,000 per day” as a minimum, not an exact target.
2. Run the deterministic matcher:

   ```sh
   python3 scripts/match_accounts.py <<'JSON'
   {"checking":{"minimum_mobile_deposit_daily":10000},"savings":{"same_day_ach_required":true}}
   JSON
   ```

   The command reads JSON from standard input and writes one JSON object to standard output. The example values are illustrative; replace them with the current customer's requirements.
3. Interpret the output:
   - A recommendation with `status: "matched"` meets every stated hard requirement for that product type.
   - A recommendation with `status: "no_match"` means the supplied catalog cannot substantiate a qualifying product. State that plainly and ask whether the customer wants to relax a requirement or provide another priority.
   - `requirements_not_provided` means the customer needs to specify the missing priority before a reliable recommendation can be made.
4. Give the customer one direct recommendation per requested account type, rather than an unnecessary list. State the specific supporting capability and numeric limit where available. Do not claim the recommendation is universally “better” than the customer’s existing account unless the supplied facts support the comparison.
5. If a recommendation is selected from a preference tie-break, describe it as the recommended fit based on the stated needs and available information, not as the only product that could ever qualify.
6. End by asking whether the customer wants to proceed with opening the recommended account(s). A positive response to the recommendation alone is not sufficient to execute an opening; obtain the account selection and perform all eligibility and authorization checks first.

## Customer-response pattern

For each matched product, use a concise structure:

- **Recommendation:** product name.
- **Why it fits:** connect the customer’s stated threshold or feature requirement to the documented product capability.
- **Scope:** mention any relevant limitation only if it is documented (for example, the customer must choose the same-day option when scheduling ACH).
- **Next step:** ask whether the customer wants to begin the opening process.

If the customer requested both account types, present both recommendations in the same response. Do not present comparisons against unrelated products unless the customer asks for them.

## If the customer asks to open an account

Recommendation and account opening are separate workflows. Before any banking action, verify the customer's identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Then obtain the exact official account-class selection and complete the applicable eligibility checks:

### Business checking

Before opening, confirm that the customer is verified; has at least one existing personal checking account with status `OPEN`; has no more than six business checking accounts; has no accounts with status `CLOSED`; and has an existing checking balance of at least $500. Only after those checks and customer confirmation should the executor use the normal declared account-opening tool with account type `checking` and the selected official account class.

### Business savings

Before opening, confirm that the customer is verified; has at least one `OPEN` business checking account; has fewer than four business savings accounts; has no accounts with negative balances; and has a qualifying existing business checking account that has been open at least 30 days and has a balance of at least $2,500. Only after those checks and customer confirmation should the executor use the normal declared account-opening tool with account type `savings` and the selected official account class.

After a savings account is successfully opened, ask whether the customer authorizes an opening-deposit transfer from the qualifying business checking account. If authorized, use only the normal declared internal-transfer tool and the qualifying account as source. If the customer declines or the transfer fails, explain that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed. Do not assume a deposit amount or initiate a transfer without explicit authorization.

## Validation

Before responding, check that:

- each recommended checking product has a documented daily mobile-deposit limit at least equal to the requested threshold;
- each recommended savings product has documented same-day ACH availability when required;
- no missing or undocumented feature is represented as confirmed;
- no banking action has been taken during a recommendation-only request; and
- account-opening actions, if requested later, are gated on verification, eligibility, exact product selection, and explicit authorization.

## Matcher interface

`scripts/match_accounts.py` accepts this JSON schema:

```json
{
  "checking": {"minimum_mobile_deposit_daily": 10000},
  "savings": {"same_day_ach_required": true},
  "catalog": {
    "checking": [{"name": "...", "mobile_deposit_daily_limit": 0, "preferred": false}],
    "savings": [{"name": "...", "same_day_ach": true, "preferred": false}]
  }
}
```

`catalog` is optional. When absent, the packaged capability catalog is used. Amounts must be non-negative numbers in USD. The output contains `checking` and `savings` result objects, each with a status, evaluated requirement, and either a recommended product or an explanation. Invalid input produces `{"error": "..."}` and a nonzero exit status.
