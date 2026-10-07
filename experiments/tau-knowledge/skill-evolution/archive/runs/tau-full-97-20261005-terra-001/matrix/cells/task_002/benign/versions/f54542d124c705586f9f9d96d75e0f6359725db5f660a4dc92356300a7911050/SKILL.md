---
name: highest-flat-cash-back-card
version: 1.0.0
description: Recommend exactly one personal Rho-Bank credit card when a customer asks for the highest cash-back rate on ordinary/everyday purchases. Use this for evidence-based product comparison, not for account servicing, applications, or suitability advice.
---

# Highest Flat Cash-Back Card Recommendation

## Scope
Use this Skill when the customer wants one card with the highest reward rate for everyday spending. "Everyday" means a flat rate that applies to all eligible posted purchases; a category-only travel, software, or merchant-category bonus is not a substitute.

Do not use the customer's job title, organization, or inferred financial status as an eligibility fact. Do not access customer data or perform an application. The recommendation is product information, not an approval decision.

## Evidence collection and interpretation
1. Read the supplied product documents and task evidence at execution time.
2. Build one candidate record for each **personal** card with a documented cash-back rate. Preserve source-supported facts only:
   - card name;
   - flat cash-back percentage;
   - whether the rate applies to all eligible purchases;
   - exclusions or posting/return conditions;
   - annual fee;
   - explicit access or application prerequisites;
   - source identifiers or quotations.
3. Exclude cards whose stated rate is limited to categories, as well as points-only earning programs unless the evidence explicitly establishes a cash-equivalent conversion and the request permits that comparison.
4. Exclude a card from an ordinary application recommendation only if evidence explicitly says it is unavailable to ordinary applicants (for example, invitation-only). Do not exclude a card merely because it has a credit-score requirement; disclose that requirement instead.
5. Run `scripts/recommend.py` with the candidate records. The script selects the unique highest eligible flat rate and rejects ties or incomplete comparison data rather than inventing a tie-breaker.
6. Give the customer exactly one card recommendation. State the card name and flat rate first. Briefly disclose material tradeoffs supported by the sources, especially annual fee, minimum credit score, invitation-only status if relevant, and the meaning of eligible purchases. Do not name runner-up cards when the customer asked for exactly one recommendation.

## Required response shape
Use a concise response such as:

> I recommend **[selected card]**. It earns **[rate]% cash back on all eligible purchases**, the highest documented flat everyday rate. [State documented annual fee and access prerequisite.] Eligible purchases and posted-transaction/return rules apply; [state documented exclusions if available].

This is one recommendation, not a ranked list. If the evidence does not establish a unique highest flat rate, say that the supplied information cannot support a single recommendation and request the missing product terms. Do not guess.

## Script interface
Run:

```text
python scripts/recommend.py < candidates.json
```

Input is one JSON object:

```json
{
  "cards": [
    {
      "name": "string",
      "personal": true,
      "cash_back_rate_percent": "decimal number",
      "applies_to_all_eligible_purchases": true,
      "ordinary_application_available": true,
      "annual_fee": "decimal number or null",
      "eligibility_constraints": ["source-supported string"],
      "conditions": ["source-supported string"],
      "evidence": ["source identifier or quotation"]
    }
  ]
}
```

`ordinary_application_available` may be omitted when the evidence does not state an invitation-only or equivalent restriction; it then defaults to `true`. `evidence` must be nonempty for each candidate. The script emits JSON with `status: "ok"` and one `recommendation`, or `status: "needs_review"` with a reason. It never selects a winner in a tie.

## Validation before responding
- Confirm the selected rate is explicitly flat across all eligible purchases, not only a bonus category.
- Confirm every compared candidate has source evidence and that no known higher qualifying rate was omitted.
- Confirm exactly one card name appears as the recommendation.
- Ensure every fee, prerequisite, and eligibility statement in the customer response is supported by the candidate evidence.
- If the customer asks to apply, determine personal eligibility, or make account changes, explain that approval depends on the issuer's process and use the appropriate available workflow; this Skill itself performs no such action.
