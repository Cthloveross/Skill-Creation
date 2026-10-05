---
name: highest-everyday-cash-back-card
description: Select and recommend exactly one card with the highest explicitly documented cash-back rate for everyday, all-purchase, or broadly eligible-purchase spending from supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks which one card has the highest cash back for everyday spending, all purchases, or eligible purchases.

This is a comparison of published product terms, not a personalized account, underwriting, or eligibility decision. A customer lookup is unnecessary. Missing customer records, occupation, employer, interests, and inferred preferences must not change the documented-rate ranking. Do not predict approval or eligibility.

## Required method

1. Collect the complete current set of supplied card-product documents. Use their `title` and full `content`; do not omit a document based on title, a customer attribute, or a customer lookup.
2. Run `scripts/select_highest_everyday_cash_back.py` on that document set.
3. Interpret the result as follows:
   - `ok`: send `customer_response` verbatim as the substantive customer response.
   - `no_qualifying_candidate`: explain only that the supplied terms do not explicitly establish a broad-purchase cash-back rate. Do not choose a category bonus.
   - `tie_requires_resolution`: explain that the highest documented broad-purchase rate is tied and ask the customer for a tie-breaker. Do not invent a winner.
   - `invalid_input`: fix the runtime input schema and rerun. This status is never evidence that product terms are absent.

Do not reply to a highest-cash-back request before performing the comparison when product documents are supplied.

## Customer-response requirements

When the selector returns `ok`, the response must contain exactly one card recommendation and must state:

- the selected product name;
- its documented percentage and the words `cash back`;
- that the rate applies to all eligible purchases, all purchases, eligible spend, or another explicitly broad purchase scope; and
- that this is the highest documented rate for everyday spending.

Use the selector's generated response unchanged. Do not hedge, decline, claim that terms are unavailable, add a second card, or mention a runner-up. Category-specific rewards (for example, travel, software, dining, merchant-specific, rotating-category, introductory, or sign-up rates) do not answer an everyday-spending comparison.

Do not add annual fee, APR, minimum-credit-score, subscription, invitation, or approval details unless the customer asks for them. If the customer asks and the supplied documents support an answer, state the relevant terms exactly and do not imply approval.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads a JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "documents": [
    {"title": "string", "content": "string"}
  ]
}
```

Runnable executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```

Output schema:

- `status: "ok"` includes `recommendation`, `qualifying_candidates`, and a ready-to-send `customer_response`.
- `status: "no_qualifying_candidate"` includes an empty `qualifying_candidates` list.
- `status: "tie_requires_resolution"` includes the tied highest-rate candidates.
- `status: "invalid_input"` includes `error`.

## Final validation

For an `ok` result, verify that the selected response contains its selected card name, percentage, `cash back`, and an explicit broad-purchase scope. Verify that no other card name is added. The emitted `customer_response` is constructed to meet this validation and should be sent verbatim.
