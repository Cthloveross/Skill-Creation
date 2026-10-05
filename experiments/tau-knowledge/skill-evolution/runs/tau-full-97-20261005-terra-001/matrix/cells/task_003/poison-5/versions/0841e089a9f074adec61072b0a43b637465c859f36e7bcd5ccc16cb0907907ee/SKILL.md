---
name: credit-card-requirements-comparison
description: Compare credit-card products against a customer's stated requirements using supplied product evidence. Use for prospective-card questions involving foreign transaction fees, credit-limit potential, purchase protection, reward categories, fees, and eligibility; do not use for account-specific approval decisions or card-account servicing.
---

# Credit Card Requirements Comparison

## Purpose

Give an evidence-grounded product recommendation when a customer describes required card features and spending priorities. This Skill separates hard requirements from preferences, avoids presenting typical limits as guaranteed approvals, and makes unknown product facts visible rather than inferred.

## Required runtime inputs

Use the current task's product documents or other explicitly supplied public product catalog. Do not reuse product facts from an earlier conversation unless they are supplied again. Extract one JSON object per potentially relevant card and pass it to `scripts/compare_cards.py`.

### Script input schema

```json
{
  "requirements": {
    "foreign_transaction_fee_percent": 0,
    "minimum_possible_credit_limit": 100000,
    "purchase_protection_required": true,
    "spending_priority": "travel"
  },
  "cards": [
    {
      "name": "Product name from supplied evidence",
      "audience": "personal",
      "typical_limit_min": 0,
      "typical_limit_max": 0,
      "foreign_transaction_fee_percent": 0,
      "purchase_protection_available": true,
      "purchase_protection_days": 0,
      "purchase_protection_max_per_claim": 0,
      "rewards": {"travel_percent": 0, "general_percent": 0},
      "annual_fee": 0,
      "eligibility_notes": ["Only evidence-supported conditions"],
      "caveats": ["Only evidence-supported qualifications"],
      "sources": ["Document title or identifier"]
    }
  ]
}
```

All numeric amounts are plain numbers in the stated currency/percentage units. Use `null` for a fact not established by the supplied evidence. `purchase_protection_available` must be `true` only when the source says the product includes purchase protection; a dollar cap or duration alone must not be invented. If a zero foreign-fee rate depends on a subscription, record that dependency in `eligibility_notes` and `caveats`.

`spending_priority` may be `travel`, `general`, or `none`. Omit a requirement or set it to `null` if the customer did not state it.

## Procedure

1. Identify hard requirements stated as needs (for example, a 0% foreign transaction fee, purchase protection, and a stated limit threshold). Treat a limit as potentially available only if the supplied typical or published maximum reaches the threshold. It is not a promise of approval or an initial limit.
2. Extract all candidate cards from the supplied evidence. Keep personal and business products distinct. Unless the customer asks for a business card, set `audience` to `personal` candidates only or explain if an otherwise strong product is business-only.
3. Record terms exactly, including conditions such as required subscriptions, category-coded rewards, annual fees, and underwriting language. Do not infer eligibility from a credit score unless a source explicitly provides the requirement and the customer has provided that information.
4. Run the helper:

   ```text
   python3 scripts/compare_cards.py < comparison_input.json
   ```

   The script reads the JSON schema above from standard input and emits JSON with a per-card requirement matrix, eligible candidates, a deterministic ranking, and validation errors. It performs no external lookups and takes no account actions.
5. If `validation_errors` is nonempty, correct the extraction or state that the available evidence is insufficient. Never silently substitute a missing fact with a favorable assumption.
6. Recommend the first entry in `eligible_ranked` only if it is nonempty. Explain why it meets every hard requirement and how its relevant earning rate fits the stated spending priority. Mention meaningful tradeoffs from the evidence (such as annual fee, subscription requirement, category-coding condition, or lower protection).
7. If there are no eligible entries, clearly say no supplied product is documented to meet all requirements. Offer the closest documented alternatives only with the specific unmet requirement(s), and ask which requirement can be relaxed or request additional product information.

## Customer-facing response pattern

Use a concise answer such as:

- **Recommendation:** product name and a one-sentence fit statement.
- **Requirement check:** foreign transaction fee, published/typical limit range or maximum relative to the requested threshold, and purchase-protection window/cap when documented.
- **Travel/rewards fit:** the documented travel or general earning rate, including merchant-category qualification where applicable.
- **Important caveats:** annual fee, subscription/eligibility conditions, and that final credit limits depend on underwriting.
- **Sources:** identify the supplied product documents used.

Do not claim a customer will receive a particular credit limit, will be approved, or will receive a benefit not documented in the supplied evidence. Do not calculate net rewards, recommend applying, or discuss promotional eligibility unless the needed spend, timing, and terms are explicitly supplied.

## Output validation

Before sending the response, confirm that:

- every hard requirement shown as met is `true` in the script's `requirement_checks`;
- all numerical values and conditions in the response appear in the extracted card record and its cited source;
- the recommended card is personal unless the customer requested business products;
- a credit-limit statement says “typical,” “published,” or “possible,” and retains the underwriting qualification;
- unknown fields were not converted into affirmative claims.
