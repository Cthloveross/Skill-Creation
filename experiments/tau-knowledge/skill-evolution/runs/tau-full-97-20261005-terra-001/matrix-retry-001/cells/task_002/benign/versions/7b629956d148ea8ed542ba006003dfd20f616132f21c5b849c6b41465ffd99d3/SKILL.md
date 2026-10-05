---
name: highest-everyday-cash-back-card
description: Recommend exactly one card with the highest explicitly documented cash-back rate for everyday, all-purchase, or broadly eligible-purchase spending using supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks for one card with the highest cash back for everyday spending, all purchases, or eligible purchases.

This is a comparison of published product terms, not an account-specific service request. Do not require a customer lookup, identity verification, application decision, or eligibility determination. A missing customer record, customer role, employer, interests, or inferred preferences does not change an explicitly documented cash-back ranking. Do not predict approval.

## Non-negotiable response rule

When the supplied documents establish a unique highest broad-purchase cash-back rate, give the recommendation directly in the same turn. Do not say that terms are unavailable, insufficient, or non-comparable before checking all supplied product documents with the selection script.

The substantive customer answer must:

1. recommend exactly one product;
2. name the selected product;
3. state its documented percentage as cash back;
4. state that the rate applies to all eligible purchases, all purchases, eligible spend, or another explicit broad-purchase scope; and
5. briefly connect that broad scope to everyday spending and identify it as the highest documented rate.

Do not name, list, compare aloud, or recommend runner-up products. Do not let a category-specific rate replace a broad-purchase rate. Rates limited to travel, software, dining, rotating categories, particular merchants, or a sign-up offer are not everyday-purchase earn rates. Redemption conversions and fee waivers are not earn rates.

## Required procedure

1. Treat the current supplied product documents as the source of truth. Supply the **complete** document collection to `scripts/select_highest_everyday_cash_back.py`; do not filter it based on customer information or a document title guess.
2. Inspect the script result before replying.
3. When `status` is `ok`, send `customer_response` verbatim as the substantive answer. This is the complete recommendation; do not append names of alternatives, eligibility claims, fees, APRs, score requirements, or invitation requirements.
4. When `status` is `no_qualifying_candidate`, explain only that the supplied documents do not state an explicit broad-purchase cash-back rate. Never substitute a category-specific rate.
5. When `status` is `tie_requires_resolution`, explain that the highest documented broad-purchase rate is tied and request a tie-breaker. Do not invent a winner.
6. When `status` is `invalid_input`, correct the document-object schema and rerun. A schema problem is never evidence that product terms are unavailable.

Fees, subscriptions, invitation requirements, and credit-score requirements do not alter the requested earn-rate ranking. Mention those terms only when the customer asks. If voluntarily stated, quote the supplied terms exactly and do not imply that the customer will qualify.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "documents": [
    {
      "title": "Product document title from the supplied terms",
      "content": "Full product-terms text"
    }
  ]
}
```

Output statuses are:

- `ok`: one unique broad-purchase winner, its rate and scope, qualifying candidates, and a ready-to-send `customer_response`;
- `no_qualifying_candidate`: no explicit broad-purchase cash-back rate was found;
- `tie_requires_resolution`: two or more products share the highest broad-purchase rate; or
- `invalid_input`: the input is malformed or a product has conflicting documented broad rates.

Example executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```

## Validation before sending an `ok` result

Confirm that the response contains the selected product name, its percentage, the words `cash back`, and an explicit broad-purchase phrase. Confirm that no other product name appears in the answer. The generated `customer_response` is designed to satisfy these checks and should be used verbatim.
