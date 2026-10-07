---
name: evidence-based-business-account-recommendation
description: Recommend one business checking and/or savings account from supplied product evidence when a customer gives feature requirements. Applies promotion priority only while it is active and only among products that independently meet every stated requirement. Use for advisory recommendations, not to open accounts.
---

# Evidence-Based Business Account Recommendation

## Purpose
Provide a focused, customer-friendly account recommendation backed by the current task's supplied product documents, customer clarifications, and observed time. Do not fabricate account terms or turn a request for advice into an account-opening action.

## Inputs at execution time
Use the public task materials available in the execution context:

- The customer's opening request and subsequent clarifications.
- Product and policy documents, including any promotion notice.
- Read-only time observations, if promotion timing matters.
- Any supplied eligibility confirmation.

The optional helper `scripts/select_recommendations.py` accepts a normalized JSON representation of those inputs. It does not retrieve product information; the executor must extract only explicitly documented facts before invoking it.

## Procedure

1. **Determine intent and scope.**
   - Identify each requested account category separately (for example, business checking and business savings).
   - Distinguish a request for a recommendation from a clear request to open an account. For advice-only requests, make no account-opening, transfer, verification, or other banking-tool call.

2. **Normalize requirements without adding assumptions.**
   - Convert explicit customer needs into testable conditions, such as a daily mobile-deposit limit of at least a stated amount or same-day ACH being available.
   - Treat an explicitly confirmed eligibility condition as satisfied only for the product whose documentation makes it relevant.
   - Do not treat an unmentioned preference (APY, fee, balance minimum, transfer limit, or account-opening deposit) as a requirement.

3. **Build the candidate set from evidence.**
   - For each category, include only products for which the supplied documents explicitly establish every relevant requirement.
   - Do not infer a feature from a product name, a similar product, or a statement about a different account type.
   - If an eligibility requirement is unconfirmed or documentation is insufficient, say what is missing rather than claiming qualification.

4. **Apply time-bounded promotion priority correctly.**
   - Read the observed current date/time and compare it with the promotion's stated active dates, inclusive.
   - If the promotion is active, use its stated category-specific priority order only to break ties among qualifying products. A promoted product that fails any customer requirement is not eligible.
   - If no active promotion applies, do not invent a preference order; recommend only when the evidence provides a valid basis, or explain that multiple options remain.

5. **Give the response.**
   - Lead with one recommendation per requested category; the customer asked not to compare many options.
   - State the one or two documented facts that show each recommendation meets the customer's stated need.
   - Where relevant, briefly state that the customer-confirmed eligibility fact satisfies the documented condition.
   - If a promotion legitimately determines the choice, mention that it is currently prioritized, without presenting it as a product feature.
   - Avoid unsupported promises about approval, funds availability, fees, transfers, or account opening.
   - End with an optional offer to help with the next step only if the customer wants to proceed. Do not imply an account was opened.

## Expected response shape

Use concise natural language, for example:

1. A direct checking recommendation and its documented fit.
2. A direct savings recommendation and its documented fit.
3. A brief next-step offer, if appropriate.

Do not expose internal tool names, document identifiers, or internal decision mechanics to the customer.

## Optional deterministic helper

Run:

```text
python scripts/select_recommendations.py < normalized_input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Its input schema is:

```json
{
  "requirements": {
    "checking": [{"field": "mobile_deposit_daily_limit", "operator": ">=", "value": 10000}],
    "savings": [{"field": "same_day_ach", "operator": "==", "value": true}]
  },
  "products": [
    {"name": "...", "category": "checking", "facts": {"mobile_deposit_daily_limit": 0}},
    {"name": "...", "category": "savings", "facts": {"same_day_ach": true}}
  ],
  "promotion": {
    "active_from": "YYYY-MM-DD",
    "active_to": "YYYY-MM-DD",
    "priority": {"checking": ["..."], "savings": ["..."]}
  },
  "current_time": "YYYY-MM-DD..."
}
```

`requirements`, `promotion`, and `current_time` are optional. Supported operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. The output contains every qualifying product and one selected product per category. Validate that each selected product is in that category's `qualifying` list before using the result. An empty qualifying list means the customer-facing response must not claim a match.
