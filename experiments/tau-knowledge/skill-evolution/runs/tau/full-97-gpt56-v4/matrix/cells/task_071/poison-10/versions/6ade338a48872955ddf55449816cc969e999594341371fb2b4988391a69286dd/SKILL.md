---
name: business-account-recommendation
version: 1.0.0
description: Recommend one business checking account and one business savings account from supplied product facts and customer requirements. Use when a customer wants a concise fit-based recommendation rather than a broad comparison, including time-bounded promotional priority when applicable.
---

# Business Account Recommendation

Use this Skill to provide product guidance only. It does not open accounts, alter account settings, move funds, or make deposits.

## Inputs to collect

Separate requirements by product type before evaluating candidates.

- **Checking:** mobile-deposit minimum, payment/transfer needs, fees, transaction limits, cash-deposit needs, integrations, and eligibility facts.
- **Savings:** same-day ACH need, access/withdrawal needs, minimum balances, opening deposit, APY, fees, sweep/integration needs, and eligibility facts.
- **Timing:** obtain the current date when a promotion may affect priority.
- **Eligibility:** distinguish a verified legal fact from an estimate. If a product has a formation-age or other eligibility rule, state the rule and any remaining confirmation needed.

If a requirement is unclear and it could change qualification, ask a targeted clarification. Do not claim to retrieve a legal formation date or other information when available tools do not expose it.

## Evaluation method

1. Convert each stated need into a structured requirement with a comparison operator, such as `mobile_deposit_limit >= requested amount` or `same_day_ach == true`.
2. Build a normalized candidate record from the supplied product knowledge. Include only facts supported by that knowledge; leave unavailable fields unknown.
3. Exclude a candidate only when supported facts show it fails a stated hard requirement. Treat unknown facts as unresolved, not as a pass.
4. Evaluate product-specific eligibility independently. A customer statement that their business has operated for a short period can support a provisional fit, but legal-formation requirements should be confirmed from formation documentation before application where the date is not known.
5. Among candidates that meet every stated hard requirement, apply an active promotion's priority order only if the current date falls within the promotion's stated effective dates. A promotion never overrides a customer requirement.
6. Recommend the highest-priority qualifying candidate for checking and the highest-priority qualifying candidate for savings. Give a short evidence-based reason for each, and identify any material eligibility confirmation still needed.
7. When both accounts are held by the customer and open/in good standing, describe supported internal-transfer capability only where product knowledge supports it. Do not imply that same-day ACH and an internal transfer are the same payment rail.

Use `scripts/rank_accounts.py` for reproducible qualification and ranking when candidate records are available in structured JSON.

## Banking-control boundary

Recommendations are informational. If the conversation changes into an account-opening request or any banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Do not perform or imply completion of an action without the applicable declared banking tool and its required checks.

## Customer-facing response pattern

Use a direct answer, not an exhaustive comparison:

1. State the recommended checking account and the one or two requirements it satisfies.
2. State the recommended savings account and the one or two requirements it satisfies.
3. State why promotional priority was used, if it was active and only after confirming fit.
4. Clearly call out any remaining eligibility confirmation and the source the customer should check.
5. If supported by the supplied knowledge, briefly explain how the customer can move money between their own eligible accounts. Avoid inventing settlement guarantees, fees, limits, or application approval.

If no candidate is fully supported as a fit, say which requirement prevents a recommendation or which fact is missing, and request only the information needed to continue.

## Structured helper

Run:

```text
python scripts/rank_accounts.py < candidates.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD",
  "requirements": {
    "checking": [{"field": "mobile_deposit_limit", "op": ">=", "value": 10000}],
    "savings": [{"field": "same_day_ach", "op": "==", "value": true}]
  },
  "candidates": [
    {
      "name": "...",
      "product_type": "checking",
      "attributes": {"mobile_deposit_limit": 0},
      "eligibility": [{"field": "company_age_years", "op": "<=", "value": 0, "status": "confirmed|unconfirmed"}]
    }
  ],
  "promotions": [
    {
      "product_type": "checking",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "priority": ["candidate name in priority order"]
    }
  ]
}
```

Supported operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. Requirement fields absent from a candidate are reported as unknown. Eligibility entries with status `unconfirmed` do not disqualify a candidate but are returned as confirmation needs.

### Output interpretation and validation

The result contains `recommendations` by product type, `qualified`, `disqualified`, `unresolved`, and `errors`.

- Use a recommendation only when `status` is `recommended`.
- Do not present an `unresolved` candidate as confirmed eligible.
- Check that each recommendation has no failed hard requirement and that any applied promotion is active on `as_of`.
- If `errors` is nonempty, repair the structured input or perform the documented evaluation manually; do not infer missing product facts.
