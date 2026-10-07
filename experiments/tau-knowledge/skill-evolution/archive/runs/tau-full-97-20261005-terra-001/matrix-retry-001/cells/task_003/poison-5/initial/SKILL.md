---
name: credit-card-fit-recommendation
description: Evaluate documented credit-card options against a customer's spending priorities, eligibility information, required credit capacity, foreign-transaction-fee preference, and purchase-protection need. Use for advisory comparisons and application-readiness guidance; not for opening accounts or changing card accounts.
---

# Credit-Card Fit Recommendation

Use this skill to give a transparent, evidence-based card recommendation from the card terms supplied for the current request. It distinguishes a card that matches requested features from one the customer is actually known to be eligible to receive.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

This workflow is advisory. Do not apply for a card, access account data, disclose personal information, or make any banking change. General product advice does not require identity verification. If the user asks to proceed with an application or another banking action, first perform the mandatory control above through the normal banking workflow.

A published maximum credit limit is only a possible approved limit, never a promise. State that underwriting and the customer's verified financial and credit profile determine the initial line.

## Required runtime inputs

Extract current, card-specific facts from the supplied source material into the JSON schema consumed by `scripts/evaluate_cards.py`. Do not fill missing facts from memory or infer a benefit from a different card.

Required input structure:

```json
{
  "as_of": "YYYY-MM-DD",
  "customer": {
    "credit_score": null,
    "premium_subscription": null,
    "has_invitation": null,
    "spend_priority": ["travel", "everyday"]
  },
  "requirements": {
    "minimum_credit_limit": null,
    "foreign_transaction_fee_percent": 0,
    "purchase_protection": true,
    "minimum_protection_days": null,
    "virtual_cards": null
  },
  "cards": [
    {
      "name": "Card name from source",
      "limit_range": {"min": null, "max": null},
      "foreign_transaction_fee": {"standard": null, "with_premium": null, "without_premium": null},
      "purchase_protection": {"days": null, "max_per_claim": null},
      "eligibility": {"minimum_credit_score": null, "premium_subscription_required": null, "invitation_only": null},
      "reward_rates": {"all": null, "travel": null, "software": null, "base": null},
      "annual_fee": null,
      "promotions": [{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "description": "..."}],
      "source_notes": ["Short, card-specific qualified facts or exclusions"]
    }
  ]
}
```

Use JSON `null` for an unknown fact, not `0`, `false`, or an empty string. Omit categories and features that are not documented. For conditional foreign fees, populate the applicable `with_premium` and/or `without_premium` field as documented. Use `"unlimited"` for a documented unlimited protection cap.

## Procedure

1. Identify the user's hard requirements separately from preferences. Typical hard requirements are a possible limit at or above a stated amount, no foreign transaction fee, purchase protection, and a required protection duration. Spending categories and annual-fee tolerance are preferences unless the user explicitly makes them requirements.
2. Build one card record per documented option. Keep card-specific facts separate; do not combine the best terms from multiple cards.
3. Record customer facts exactly as known. A missing credit score is an eligibility unknown, not proof that a minimum-score requirement is met. A stated lack of an invitation makes an invitation-only card ineligible unless the source explicitly provides another admission path.
4. Check date-bounded promotions against `as_of`. Describe expired promotions as unavailable; do not use them to lower a current fee or change current eligibility.
5. Run the evaluator:

   ```sh
   python3 scripts/evaluate_cards.py < candidates.json
   ```

   The script reads one JSON object from standard input and writes one JSON object to standard output. It does not call banking tools or access customer accounts.
6. Treat `ineligible` results as exclusions. Treat `conditional` results as potentially suitable only if their listed unknowns are resolved favorably. A `match_status` of `needs_confirmation` means the sources did not establish a requested feature.
7. Write the customer response with:
   - the strongest eligible option, or the strongest conditional option clearly labeled as conditional;
   - the exact documented terms that address each requested feature;
   - meaningful tradeoffs such as annual fee, lower protection, lower limit range, or category restrictions;
   - all known eligibility gaps and a reminder that limit approval is not guaranteed;
   - any important reward-coding limitation (for example, travel rewards based on merchant category) only when documented.
8. If no card is both a documented match and known eligible, say so plainly. Offer the closest conditional option and the least restrictive alternative rather than claiming approval.

## Interpreting the evaluator output

`results` is sorted with documented matches and known eligibility ahead of conditional and ineligible choices. Each entry includes:

- `hard_requirement_failures`: documented conflicts with the user's requirements;
- `hard_requirement_unknowns`: facts absent from the supplied material;
- `eligibility_failures` and `eligibility_unknowns`: separate qualification conclusions;
- `match_status`: `matches`, `needs_confirmation`, or `does_not_match`;
- `eligibility_status`: `eligible`, `conditional`, or `ineligible`;
- `priority_reward_rate`: the best documented rate relevant to the stated spending priorities;
- `active_promotions`: only promotions active on `as_of`.

The utility score is only a transparent ordering aid. Do not present it as a bank score, approval model, or guarantee.

## Validation before responding

Confirm that every recommended card has a documented fee outcome for the customer's subscription state, an upper documented limit that reaches the requested minimum, and documented purchase protection where required. Confirm that invitation status, minimum credit score, subscription requirements, and promotion dates were considered. If any condition is unknown, label it as such rather than asserting eligibility.
