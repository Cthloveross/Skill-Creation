---
name: credit-card-preference-matcher
description: Evaluate credit-card products against a customer's stated eligibility and feature preferences, then provide a precise, non-binding recommendation or explain why no verified match exists. Use for informational card-selection conversations; do not use it to submit applications, alter accounts, or perform payments.
---

# Credit Card Preference Matcher

Use this Skill when a customer asks which card best fits measurable preferences such as credit score, fees, payment terms, rewards, or virtual-card availability.

## Scope and safety

This is an informational comparison workflow, not an application or account-servicing workflow. Do not claim approval, preapproval, an exact credit limit, or that a stated credit score guarantees eligibility. Do not perform a banking action, collect unnecessary personal data, or look up a customer account merely to answer a product question.

If a later request changes into an account, card, transfer, payment, rewards-redemption, dispute, blocking, or profile-change action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Use only the declared banking tools for such an action, obtain any required confirmation immediately before committing it, and report the resulting status accurately.

## Method

1. Extract each customer requirement without strengthening it:
   - Credit-score suitability: compare the stated score with the published minimum score. A product with no score requirement meets this criterion; an unknown requirement is not a verified match.
   - Numeric ceilings, such as a foreign-transaction-fee maximum or minimum-payment percentage: require the published value to be less than or equal to the ceiling.
   - Required features, such as virtual-card management: require an explicit affirmative availability statement.
   - Payment flexibility: distinguish a required *minimum payment* from paying the full statement balance. Record the published payment basis (for example, outstanding balance) rather than silently treating it as a different basis.
2. Read the current task's supplied product evidence and build structured product records. Do not infer absent facts, mix facts between products, or substitute generic market terms for published terms.
3. Optionally run `scripts/card_matcher.py` to make the comparisons repeatable. Supply only facts obtained from the current product material; the script does not discover product facts.
4. Recommend a product only when every required criterion is explicitly satisfied. State the relevant terms concisely and identify the payment basis if it differs from the customer's wording.
5. If no product is a verified full match, say so plainly, identify the closest alternatives and the specific failed or unknown criteria, and offer to adjust preferences. Do not invent an exception or imply discretionary underwriting.
6. If the customer signals they want a human after an unavailable-offer refusal or remains dissatisfied, use the declared human-transfer tool with the applicable reason and a short factual summary.

## Response pattern

For a verified match, respond in a helpful, direct form:

- Name the matching product.
- Tie each requested criterion to its published term.
- Explain that the customer can pay the published minimum rather than the full statement balance, while noting that carrying a balance may accrue interest under the published terms.
- State that final eligibility and approval are determined during the application.
- Offer to explain application steps or compare another preference, without starting an application unless the customer expressly asks.

For a non-match, lead with the unavailable result, then list each relevant mismatch. Avoid a long catalog of unrelated card features.

## Script interface

`scripts/card_matcher.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "preferences": {
    "credit_score": 0,
    "foreign_transaction_fee_max_pct": 0,
    "minimum_payment_max_pct": 0,
    "require_virtual_card_management": true
  },
  "products": [
    {
      "name": "string",
      "minimum_credit_score": null,
      "foreign_transaction_fee_pct": 0,
      "minimum_payment_pct": 0,
      "minimum_payment_basis": "string",
      "virtual_card_management": true
    }
  ]
}
```

`null` means the source explicitly states that no minimum credit score is required. Omit a field or use `null` for an unknown fact. The output contains `verified_matches`, `non_matches`, and per-criterion results. A product with an unknown required fact is not included in `verified_matches`.

Example runnable call (with values populated from the current task evidence):

```sh
python3 scripts/card_matcher.py < comparison_input.json
```

## Validate before responding

- Confirm every recommended product has a passing result for every requirement.
- Confirm that all numbers, units, and percent signs match the supplied evidence.
- Check that the credit-score conclusion uses the product's actual minimum, including an explicit no-minimum condition.
- Check that virtual-card availability is affirmative, not merely mentioned.
- Check that the response does not convert an outstanding-balance minimum-payment term into an unsupported statement-balance claim.
- Confirm that no application, payment, or other banking action was performed as part of the comparison.
