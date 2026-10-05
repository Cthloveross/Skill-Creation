---
name: highest-everyday-cash-back-card
description: Compare supplied card-product terms and directly recommend exactly one card with the highest explicitly documented cash-back rate for everyday or broad eligible-purchase spending.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks for one card with the highest cash back for everyday purchases, all purchases, or broadly eligible purchases.

This is a comparison of published product terms, not an underwriting, account-access, or personalized eligibility decision. Customer records, a failed customer lookup, occupation, employer, interests, and inferred preferences do not change a ranking based on published rates. Do not predict whether the customer will be approved or eligible.

## Required procedure

1. Treat the card-product documents supplied in the task context as the available terms. A public product document available in the task corpus is supplied evidence; do not ask the customer to provide it again or claim it is unavailable.
2. Gather the complete supplied set of current product documents, preserving each document's `title` and `content`.
3. Run `scripts/select_highest_everyday_cash_back.py` with those documents.
4. Handle the result:
   - For `status: "ok"`, send `customer_response` verbatim as the substantive reply.
   - For `status: "no_qualifying_candidate"`, explain that the supplied terms do not establish an explicitly broad-purchase cash-back rate. Do not substitute a category-specific rate.
   - For `status: "tie_requires_resolution"`, state that the highest documented broad-purchase rate is tied and request a tie-breaker. Do not invent a winner.
   - For `status: "invalid_input"`, correct the script input schema and rerun. This is not evidence that product terms are absent.

When supplied product terms support a unique winner, answer directly in the same turn. Do not withhold the recommendation because no user record was found.

## What qualifies as everyday cash back

Rank only an earn rate whose surrounding text explicitly applies broadly, such as to all purchases, all eligible purchases, eligible purchases, eligible spend, or everyday purchases. Exclude rates that are limited to a merchant category or other restriction, including travel, software, dining, rotating categories, introductory offers, sign-up bonuses, redemption conversion amounts, fees, APRs, and examples.

Do not rely on a product title alone. The qualifying rate and scope must be stated in product content.

## Customer-response requirements

For an `ok` result, send the generated response unchanged. It contains exactly one recommendation and explicitly states:

- the selected product name;
- the documented percentage and the words `cash back`;
- an explicit broad purchase scope; and
- that it is the highest documented rate for everyday spending.

Do not hedge, decline, say that terms are unavailable, list alternatives, or mention runner-up products. The customer requested a single best card.

Do not add annual fees, APRs, credit-score requirements, subscription requirements, invitation status, or approval claims unless the customer asks for that information. If asked, use only the exact supplied terms and avoid implying eligibility or approval.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads JSON from standard input and writes one JSON object to standard output.

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
  input_json={"documents": current_supplied_product_documents}
)
```

Output statuses:

- `ok`: includes `recommendation`, `qualifying_candidates`, and ready-to-send `customer_response`.
- `no_qualifying_candidate`: no explicitly broad-purchase earn rate was found.
- `tie_requires_resolution`: multiple products share the highest qualifying rate.
- `invalid_input`: the input did not follow the required schema or has conflicting broad earn rates for one product.

## Final validation

Before sending an `ok` response, verify that it names only the selected product, contains its percentage and `cash back`, and says the rate applies to broad eligible purchases. Sending `customer_response` verbatim satisfies these checks.
