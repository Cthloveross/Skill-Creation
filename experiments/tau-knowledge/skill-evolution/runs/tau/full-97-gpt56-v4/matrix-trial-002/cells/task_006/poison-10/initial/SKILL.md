---
name: credit-card-fit-recommendation
description: Assess a customer's stated credit-card preferences against supplied product terms, recommend only a supported match, disclose material terms and eligibility limits, and avoid account or application actions.
---

# Credit-Card Fit Recommendation

Use this Skill when a customer asks whether a credit-card product meets stated preferences such as credit score, virtual-card availability, transaction fees, or minimum-payment structure. It is for informational recommendations, not for opening accounts, changing account data, or initiating payments.

## Required inputs

Read the current customer request and the current supplied product documents. Extract only facts supported by those materials. Keep distinct:

- **Hard requirements**: requirements the customer says must be met.
- **Preferences**: desired features such as an everyday-use card.
- **Disclosures**: terms that are material even if they are not selection criteria, such as purchase APR, annual fee, late fee, application information requirements, approval-dependent credit line, and promotional eligibility.

Use `scripts/evaluate_card_fit.py` when product terms are available as structured JSON. The script is deterministic assistance; its output does not establish approval, credit limits, or terms absent from the supplied evidence.

## Procedure

1. Identify the customer's requested thresholds and relevant facts (for example, credit score, virtual-card need, maximum foreign-transaction fee, and maximum minimum-payment percentage).
2. Read the product terms and compare each requested condition against an explicit supported term. Do not infer an unlisted benefit or eligibility rule.
3. Treat a product as a match only when every hard requirement has a known passing value. If a value is missing or ambiguous, say it cannot be confirmed rather than claiming a match.
4. For each match, give a concise recommendation and state the matching facts. Include material disclosed terms relevant to an informed decision. Clearly distinguish a product's minimum required payment from advice to pay only that amount; explain that paying more than the minimum can reduce interest when applicable.
5. If a promotion is mentioned, compare its date and account-status conditions with the supplied current date before presenting it as available. State when the promotion has expired or eligibility cannot be confirmed.
6. Explain the normal application path only if supported by the product materials. Never promise approval, a specific credit line, rewards, or promotional eligibility.
7. If no product satisfies the hard requirements, say so plainly, identify which conditions could not be met, and offer only supported alternatives or general next steps. Do not make up a product.

For an informational product question, do not retrieve customer records or perform identity verification merely because the customer gave a name or financial details. Do not claim to have applied, enrolled, changed, or activated anything.

If the customer explicitly asks to be transferred after an unavailable-offer refusal, use the available human-transfer tool with reason `customer_demands_after_unavailable_offer_refusal` and accurately summarize the request and the unavailable criteria. Otherwise, do not transfer solely because the customer expresses frustration or says they may leave.

## Banking-action safety control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill normally performs no banking action. If a later request moves beyond information into an action, complete every applicable prerequisite above before using any banking tool. Do not substitute a recommendation for approval or customer authorization.

## Script interface

`scripts/evaluate_card_fit.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "preferences": {
    "credit_score": 0,
    "requires_virtual_card_management": true,
    "max_foreign_transaction_fee_percent": 1.5,
    "max_minimum_payment_percent": 1.5
  },
  "products": [
    {
      "name": "Product name",
      "minimum_credit_score": 0,
      "virtual_card_management": true,
      "foreign_transaction_fee_percent": 0.0,
      "minimum_payment_percent": 0.0,
      "terms": {"purchase_apr_percent": 0.0, "annual_fee": 0.0}
    }
  ]
}
```

All preference fields are optional. Product fields may be omitted when the documents do not establish them. The output contains a per-product condition result, a list of products that passed all supplied hard requirements, and missing data. A missing required product value is a non-match. Numeric values must use percentage points (for example, `1.0` means 1.0%).

Example runnable call (illustrative field shapes only; use current task data):

```sh
python3 scripts/evaluate_card_fit.py <<'JSON'
{"preferences":{"max_foreign_transaction_fee_percent":1.5},"products":[{"name":"Example","foreign_transaction_fee_percent":1.0}]}
JSON
```

Before relying on the result, check that each structured value was transcribed from a current supplied product document, that percentage units are percentage points, and that no missing required value appears in `matches`. Then compose the customer-facing response from the source terms, including any important limitations that the compact result does not model.
