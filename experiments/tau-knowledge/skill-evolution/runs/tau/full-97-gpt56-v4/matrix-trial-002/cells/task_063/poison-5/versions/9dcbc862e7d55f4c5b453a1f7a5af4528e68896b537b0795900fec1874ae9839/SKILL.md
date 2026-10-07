---
name: savings-card-interest-combination-advisor
description: Evaluate eligible savings-account and credit-card combinations for a customer seeking to maximize one-year savings interest, including APY bonuses, stated qualification conditions, and non-stacking rules. Use for informational product comparisons; do not use it to open accounts, apply for cards, or alter customer products.
---

# Savings and Credit-Card Interest Combination Advisor

Use this Skill when a customer wants a fact-based comparison of a savings account plus credit card (and, where documented, linked checking or direct-deposit bonuses). Its purpose is to identify the highest eligible stated APY and translate the difference into estimated annual interest.

## Safety boundary

This workflow provides product information and calculations only. Do **not** submit an application, open an account, activate a card, enroll direct deposit, change account settings, or imply that an approval is guaranteed.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If the customer asks to take an action after receiving the comparison, first complete all applicable verification and confirmation requirements using the declared banking tools and current product terms. Do not treat a recommendation or an estimate as authorization to act.

## Method

1. Extract only the relevant, current product terms from supplied knowledge:
   - savings opening and ongoing balance requirements;
   - APY tier and the balance threshold for each tier;
   - card eligibility requirements, including score, subscription, invitation, and credit-check requirements;
   - card APY bonus for the *specific* savings product;
   - direct-deposit, relationship, or checking-account boosts;
   - whether card bonuses and checking boosts stack or only the highest within their category applies.
2. Determine eligibility separately for every savings account and card. Do not infer eligibility from a similar product. Mark unknown facts as unknown rather than assuming they are satisfied.
3. Exclude combinations that violate the customer's stated requirements or documented eligibility. For example, do not recommend a no-credit-check card when the customer expressly requires a card that checks creditworthiness.
4. Select the savings APY tier that corresponds to the amount the customer expects to keep in the account. A balance must meet both opening and ongoing requirements unless the documentation clearly distinguishes their applicability.
5. Apply bonuses exactly as documented. When a policy says multiple card bonuses do not stack, use only the highest eligible card bonus. Apply checking boosts similarly when the policy requires selecting only the highest one. Do not add a checking boost unless the customer's exact checking/savings pairing is documented as eligible.
6. Run `scripts/evaluate_combinations.py` with a structured transcription of the verified terms. The script ranks eligible combinations and makes its assumptions explicit.
7. Explain the recommendation in customer-facing terms: qualifying products, effective stated APY, estimated one-year interest, and the dollar difference from the next eligible choice. State qualifications the customer must maintain, and distinguish facts supplied by the customer from facts that would need confirmation.
8. If source documents conflict, identify the conflict and avoid presenting a definitive rate or ranking until the authoritative/current term can be confirmed. Never silently resolve conflicting figures by choosing a more favorable result.

## Calculation conventions

- APY is an annual yield. For a simple one-year comparison with a constant balance, estimated interest is `balance × effective APY / 100`.
- Bonus values in this workflow are percentage-point additions only when the relevant product terms describe them as additive. Do not multiply APYs.
- Estimates assume the stated balance remains eligible throughout the year and that all selected bonuses remain active. They do not predict daily balance changes, fees, taxes, card rewards, card interest, approval outcomes, or future rate changes.
- If documentation specifies daily compounding but already states APY, do not compound the published APY again.

## Running the helper

The script reads one JSON object from standard input and emits one JSON object on standard output.

Example invocation shape (replace every value with current, verified task data):

```json
{
  "customer": {
    "available_balance": 0,
    "credit_score": null,
    "premium_subscription": null,
    "requires_credit_check": true,
    "direct_deposit_active": false
  },
  "savings_accounts": [
    {
      "name": "Savings product name",
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "apy_tiers": [{"minimum_balance": 0, "apy_percent": 0}],
      "fixed_bonus_percent": 0,
      "direct_deposit_bonus_percent": 0,
      "checking_boost_percent": 0
    }
  ],
  "credit_cards": [
    {
      "name": "Card product name",
      "minimum_credit_score": null,
      "requires_premium_subscription": false,
      "requires_credit_check": true,
      "invitation_only": false,
      "apy_bonuses": {"Savings product name": 0}
    }
  ]
}
```

`minimum_credit_score`, `credit_score`, and `premium_subscription` may be `null` only when unknown. In that case, the script excludes a product requiring that unknown condition and lists why. `apy_tiers` must be ordered or unordered; the helper chooses the highest qualifying threshold. `checking_boost_percent` must already be zero unless the exact existing checking/savings pairing was verified as eligible.

## Validate before responding

- Confirm the balance used is the customer's intended savings balance, not their credit limit or a card balance.
- Confirm all monetary minima and APY values were transcribed with units intact.
- Confirm each card’s APY bonus is mapped to the exact savings account.
- Confirm whether direct deposit is already active; do not count a contingent bonus as current otherwise. You may separately describe it as an upside scenario.
- Check `excluded` results to ensure each disqualification is understandable and supported by a supplied product term.
- Report a tie as a tie rather than fabricating a preference.
- If there are no eligible combinations, explain the nearest documented alternatives and the unmet conditions without encouraging an unsupported workaround.
