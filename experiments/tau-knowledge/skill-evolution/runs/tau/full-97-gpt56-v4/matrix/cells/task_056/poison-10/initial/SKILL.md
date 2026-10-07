---
name: business-checking-recommendation
version: 1.0.0
description: Recommend the best business checking account from supplied product facts and customer requirements, including eligibility screening, mandatory requirements, current promotional priority, and transparent fee/limit caveats. Use for advisory account-comparison requests; do not use it to open, convert, or modify an account.
---

# Business Checking Recommendation

Use this Skill when a customer asks which business checking account best fits their needs or asks for an upgrade recommendation. It produces an advisory recommendation only. Do not represent a recommendation as an account opening, conversion, enrollment, or other completed banking action.

## Safety boundary

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A recommendation is not a banking action. If the customer subsequently asks to open, change, fund, transfer, or otherwise act on an account, pause the recommendation workflow and use the applicable normal banking workflow and tools. Do not infer identity, authority, balances, or eligibility from a conversational account recommendation.

## Required runtime input

Compile the current task facts into the JSON schema consumed by `scripts/rank_accounts.py`. Product values must come from the current supplied account documentation, not memory or an earlier customer instance.

```json
{
  "requirements": {
    "zero_overdraft_required": true,
    "business_age_years": null,
    "max_monthly_fee": null,
    "min_daily_transaction_limit": null,
    "minimum_apy": null,
    "required_features": []
  },
  "products": [
    {
      "name": "...",
      "overdraft_fee": 0,
      "monthly_fee": 0,
      "waiver_balance": null,
      "minimum_balance": null,
      "daily_transaction_limit": null,
      "apy": null,
      "features": [],
      "eligibility": {"max_business_age_years": null},
      "promotion_priority": null,
      "promotion_active": false,
      "source_notes": []
    }
  ]
}
```

Use numbers without currency symbols. Use `null` only when the supplied material does not establish a value. `promotion_priority` is an integer where a lower positive number is more preferred; set it only when the promotion is active on the current date and applies to this recommendation.

## Method

1. Identify explicit non-negotiable requirements. Treat phrases such as “must,” “need,” and “non-negotiable” as hard requirements. Do not convert vague preferences such as “reasonable cost” into an invented dollar limit.
2. Record known business-age or product-eligibility facts. Exclude a product when a known fact fails its stated eligibility rule. If eligibility is necessary but unknown, identify that gap rather than claiming eligibility.
3. Build the product records from current supplied documentation. Capture applicable monthly fees, waiver thresholds, minimum balances, overdraft fees, limits, APY, and relevant features separately. Do not merge values from different products.
4. Run the deterministic filter and ranking helper:

   ```sh
   python3 scripts/rank_accounts.py < request.json
   ```

   The script reads one JSON object from standard input and emits one JSON object to standard output. It does not contact services or take banking actions.
5. Recommend the first `selection` when it is non-null. A promotional priority breaks ties only among products that satisfy every known hard requirement. It never overrides an eligibility failure or an explicit customer requirement.
6. Give a concise customer-facing answer that includes:
   - one clear best option and why it meets the stated must-haves;
   - the material fee, waiver, balance, eligibility, and limit facts that affect the choice;
   - a brief contrast with the customer’s current account or the nearest alternative only where supported by supplied facts;
   - any unresolved information that could change the fit, stated as a caveat rather than an assumption.
7. Do not claim that a fee will be waived without evidence that the customer meets the threshold for the relevant evaluation period. Do not promise overdraft availability, approval, or a particular account outcome.

## Reading the helper result

- `selection` is the top eligible product, or `null` if no product meets known hard requirements.
- `excluded` lists each rejected product and the concrete reason. Mention only customer-relevant exclusions in the final response.
- `unknowns` identifies facts that were not supplied. Ask a focused follow-up if an unknown is needed to determine fit; otherwise disclose it as a caveat.
- `ranked` preserves the decision order and reasons. Use the supplied `source_notes` to retain traceability in internal work, but do not expose document identifiers unless requested.

If no eligible product remains, explain that no documented option satisfies the stated non-negotiable requirements and ask which requirement the customer is willing to revisit. Do not recommend a nonqualifying promotional product.

## Validation

Before responding, confirm that the selected product is present in `eligible`, has no listed hard-failure reason, and that every stated number in the response matches the product record. Confirm that a promotion is both active and applicable before citing it. If `zero_overdraft_required` is true, the selected record must explicitly have `overdraft_fee: 0`; an unknown overdraft fee is not sufficient.
