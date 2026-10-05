---
name: business-card-large-purchase-comparison
description: Provide a documented, customer-facing comparison and recommendation for a proposed large business-card purchase using supplied rewards, merchant-category, exclusion, credit-limit, and fee-promotion terms. Use before offering a requested human transfer; it does not apply for account applications or payments.
---

# Business Card Large-Purchase Comparison

Use this Skill for informational questions asking which business card gives the best return for a specified purchase, particularly when the charge is large enough that approval and available credit matter.

## Required inputs

Read the current task materials and obtain:

- Purchase amount, merchant, and description of the purchase.
- Supplied current date/time when a dated offer is relevant.
- Card-specific category/default rewards rates, named merchant exclusions, credit-limit ranges, annual fees, and promotional terms.
- Any supplied evidence connecting the purchase to a possible rewards category.

Do not access customer records, apply for a card, promise approval, or make a payment. A published limit range is not an approved credit line.

## Mandatory customer-response order

1. **Answer the comparison first.** Give the documented recommendation and material alternatives in a visible customer message. Do this even if the customer later requests a human agent; a transfer does not replace the requested informational answer.
2. **Then transfer if requested.** If the customer asks for a human after receiving the answer, use the normal transfer tool with the appropriate reason and a concise summary. Do not claim that the catalog is unavailable when card terms are supplied in the task materials.

## Method

1. Identify the documented category that may apply to the merchant and purchase. A category resemblance is not enough for a bonus: where terms require it, explain that the final rate depends on the merchant category code/coding used when the transaction posts.
2. Apply named merchant exclusions before category bonuses. A documented brand exclusion applies to that brand's billed services as well as its direct merchant name when the source terms establish that relationship. State the resulting standard or exclusion rate.
3. Build a card catalog only from supplied terms. Capture category rates, default rate, exclusions, limit minimum/maximum, annual fee, and dated first-year offers. Do not invent absent terms.
4. Use `scripts/compare_cards.py` for deterministic reward and capacity arithmetic. Supply rates as decimal fractions, not percentages.
5. A card can be described as **potentially able** to fund a single purchase only when its documented maximum line is at least the full charge. It still requires both approval for that amount and at least that much available credit at authorization. If its maximum is below the amount, explicitly say it cannot independently fund the single payment. Treat an absent maximum as unconfirmed capacity.
6. For a dated first-year promotion, compare the supplied observed date to both endpoints and state all eligibility conditions. Use a $0 first-year fee only conditionally unless the customer is known to meet the new-customer and account-opening conditions. State the standard renewal annual fee separately.
7. Rank potentially capable cards by the documented rate applicable to this transaction, not by an unrelated headline bonus. Quantify the leading conditional outcome and its non-bonus fallback when terms provide both.

## Required visible-answer coverage

The response must be decision-oriented, not merely a catalog list. Use the structure in `references/customer_response_checklist.md` and ensure it includes:

- A clear “recommend”/“best” conclusion naming the leading card.
- The purchase amount, leading rate, and calculated cash-back value.
- The merchant-category/coding condition and any documented fallback rate.
- The approved-limit **and available-credit** condition for the full single-payment amount.
- Meaningful potentially capable alternatives, including their applicable conditional rate and published maximum line where supplied.
- Named-exclusion analysis for any otherwise attractive alternative.
- Each relevant card that is ruled out because its published maximum is below the requested amount.
- The leading card's standard annual fee and any currently applicable, conditional first-year waiver.

When cash-back cards' database rewards are represented as points and a conversion is supplied, state that they represent cash back and use the supplied conversion; do not present them as a different rewards currency.

## Script

Run the script with a catalog derived at runtime from current task documents:

```text
python scripts/compare_cards.py <<'JSON'
{
  "purchase": {
    "amount": "<positive decimal>",
    "category": "<normalized documented category>",
    "merchant": "<merchant name>",
    "cash_back_point_value": "0.01"
  },
  "cards": [
    {
      "name": "<card name>",
      "rates": {"<category>": "<decimal rate>", "default": "<decimal rate>"},
      "excluded_merchants": ["<documented brand or merchant>"],
      "excluded_merchant_rate": "<decimal rate>",
      "requires_eligible_mcc": true,
      "limit": {"minimum": "<decimal or null>", "maximum": "<decimal or null>"},
      "fees": {"annual": "<decimal or null>", "verified_first_year": "<decimal or null>"}
    }
  ]
}
JSON
```

The script reads one JSON object on stdin and emits one JSON object on stdout. It makes no network, account, application, transfer, or payment action. `verified_first_year` may be supplied only after the executor has checked the date window and all stated eligibility conditions; otherwise use `null` or omit it. The output identifies rate source, gross cash back, MCC-condition flag, optional cash-back-point equivalent, and single-charge capacity.

If the script emits `ok: false`, correct the supplied catalog/input rather than calculating manually from malformed data. Before sending the final answer, validate the narrative against the required visible-answer coverage above.
