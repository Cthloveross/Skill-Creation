---
name: savings-card-first-year-value-and-opening
version: 1.1.0
description: Recommend and explain a savings-account and credit-card combination using supplied product evidence and customer assumptions, calculate estimated first-year net value, and safely open a chosen personal savings account only after all banking prerequisites and explicit authorization are verified.
---

# Savings and Credit-Card Combination Evaluation

Use this Skill for a customer who wants to grow savings, compare credit cards, or select both products. A comparison is informational; it is not an account-opening, transfer, or card-application authorization.

## Safety control for banking actions

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a supplied name, an account assertion, or a prior lookup as identity verification. Do not disclose profile fields while asking for verification. Before an opening or transfer, have the customer confirm two of date of birth, email address, phone number, and street address; retrieve the authorized profile; obtain the current timestamp; and call `log_verification` with the complete retrieved profile and timestamp.

A request to compare products, including a statement that the customer wants to open products eventually, is not authorization to create an account, submit an application, or move money.

## 1. Use the supplied evidence and customer facts

1. Extract the planning balance, expected monthly card spend, spend categories, time funds are expected to remain on deposit, existing products, subscription status, and known credit information from the conversation and authorized read-only observations.
2. Treat the current task's supplied product documents as the authoritative source for the recommendation. Do **not** refuse or hand off merely because a separate product-lookup tool is unavailable when the needed terms are already supplied in those documents.
3. For each plausible savings/card pair, identify:
   - savings base APY, applicable balance tier, opening and ongoing balance requirements, recurring fees, and operational requirements;
   - card annual fee, rewards rate and redemption value, application prerequisites, and promotion conditions;
   - linked-checking boosts and card-linked APY bonuses;
   - whether a requirement is `eligible`, `ineligible`, or `unknown`.
4. Apply only documented combinations. An unlisted checking/savings pairing has no linked-checking APY boost. If more than one checking boost or card bonus is relevant, use only the highest applicable boost in that category unless the evidence expressly says otherwise. Do not add card bonuses to one another.
5. Reconcile product text carefully. Calculate an additive APY from its documented base rate plus its documented bonus rather than repeating an internally inconsistent illustrative total. If the actual governing terms conflict and cannot be reconciled, disclose the conflict and do not represent the disputed result as certain.

A recommendation-only response may use stated planning facts and product evidence. It must not claim the customer is identity-verified, savings-opening eligible, card-approved, or product-linked unless that has actually been confirmed through the appropriate process.

## 2. Calculate a useful first-year comparison

Use `scripts/compare_combinations.py` for repeated arithmetic when possible. Supply product facts from the current interaction at runtime; never embed customer identifiers, preselected products, or instance results in the script input.

For each candidate:

- estimated savings interest = planned balance × effective APY;
- estimated card rewards = annual card spend × documented blended reward rate;
- estimated first-year net = interest + only verified one-time value − known annual savings fees − known card fees.

APY is already annualized, so do not compound it a second time. For tiered accounts, use the tier supported by the modeled balance. If the balance will cross tiers, model periods separately or label the estimate as simplified.

Do not include a signup offer unless the customer can meet its timing, spending, new-customer, and account-status conditions. Do not assume all spending earns a category bonus when spending mix is unknown. State both the ordinary reward case and the conditional category/merchant case when that distinction is material. Only include a points value after confirming the documented redemption conversion and any redemption threshold relevant to the estimate.

When a customer expressly wants both a card and savings account, recommend the strongest supported **pair** among the available alternatives. If a savings-only option would produce more net value at the customer's low or unspecified card spend, state that separately so the customer can decide whether the card's non-monetary benefits justify its fee. Do not replace the requested paired comparison with a handoff.

### Required customer-facing recommendation content

The response must be concrete, not just a list of questions or a referral. It should:

1. Name the recommended savings account and card, and say why the pair is the best supported option under the stated assumptions.
2. Show the base APY, each applicable bonus, effective APY, approximate annual interest on the stated deposit, all annual fees, ordinary-spend rewards, and conditional higher reward rates. Explain what is excluded from the estimate because it is unknown or conditional.
3. State material savings requirements, including the opening deposit, ongoing minimum, monthly-maintenance-fee treatment, and paperless or withdrawal requirements if documented.
4. Explain every material excluded alternative. In particular, distinguish a known blocker (such as a missing required subscription, insufficient balance, or a published minimum score above the customer's known score) from an unknown underwriting outcome. A documented minimum score of zero means an unknown score is not itself a stated minimum-score blocker, but approval remains subject to application review.
5. Explicitly say when the customer's existing checking account does not qualify for a linked-checking boost; never invent a boost for a non-listed pairing.
6. End with a safe next step: the customer may choose a savings account for opening and/or apply through the documented card application channel. Do not claim either action is complete.

Do not send the customer to a human merely to obtain a comparison that the supplied evidence supports. A human handoff is appropriate only for a genuine unsupported issue, customer request for one, or a required action that cannot safely be completed after explaining the available comparison.

### Comparator script interface

`scripts/compare_combinations.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "balance": "decimal dollars",
  "monthly_card_spend": "decimal dollars",
  "candidates": [
    {
      "name": "display name",
      "eligibility": "eligible | unknown | ineligible",
      "eligibility_notes": ["requirement or uncertainty"],
      "savings": {
        "base_apy_percent": "decimal percentage",
        "checking_apy_boosts_percent": ["decimal percentage"],
        "credit_card_apy_bonuses_percent": ["decimal percentage"],
        "additive_apy_bonuses_percent": ["decimal percentage"],
        "annual_fee": "decimal dollars",
        "opening_deposit_min": "decimal dollars",
        "ongoing_balance_min": "decimal dollars"
      },
      "card": {
        "annual_fee": "decimal dollars",
        "blended_rewards_rate_percent": "decimal percentage",
        "first_year_bonus_value": "decimal dollars"
      },
      "additional_annual_fees": "decimal dollars"
    }
  ]
}
```

Card fields are optional for a no-card candidate. `first_year_bonus_value` must be zero unless all relevant conditions have been verified. The script rejects malformed or negative numbers and invalid eligibility labels. It chooses the highest supplied checking boost and highest supplied card bonus, then adds only explicitly supplied additive bonuses.

Invoke it through `run_skill_script` with `relative_path: "scripts/compare_combinations.py"`. Before relying on its ranking, confirm that candidate eligibility, tier selection, balance requirements, and treatment of conditional offers are accurate. The script performs arithmetic only; it does not establish eligibility or approval.

## 3. Open a selected personal savings account only after explicit authorization

After the customer selects an account and explicitly asks to open it:

1. Complete and log identity verification as described in the safety control.
2. Verify authority and ownership; selected-product eligibility; at least one active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no collections or negative balances; and all product requirements, fees, limits, and confirmation requirements.
3. Confirm the exact official `account_class` string with the customer. It must be the full official name ending in `Account`. Confirm `account_type` is `savings` and verify that the opening deposit can be funded.
4. Only when every prerequisite passes, unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type: "savings"`, and the exact confirmed `account_class`.
5. If opening fails or does not return an identifiable new savings account, do not attempt funding. Report the supported failure state.
6. Ask whether the customer authorizes an immediate opening-deposit transfer from a specified owned checking account. Confirm source account, destination account, exact amount, available balance, transfer fees, limits, cutoff, and final confirmation.
7. Only with affirmative transfer authorization, unlock and call `transfer_funds_between_bank_accounts_7291` with the confirmed source account ID, new destination account ID, and exact amount.
8. If immediate funding is declined, explain that the account must be funded within 30 days by internal transfer or external deposit or it will be closed.

Never open an account when any required item is failed or cannot be verified. Do not use a savings-opening tool to apply for a credit card. If no authorized card-application tool is available, explain the documented online or dashboard application process and its known prerequisites without claiming submission or approval.

## 4. Completion response

For a recommendation-only interaction, provide the comparison, assumptions, caveats, excluded alternatives, and next decision. For an opened account, provide the official account class, returned account details, funding result or 30-day funding deadline, and any remaining card-application step. Never claim a card was opened, approved, linked, or bonus-qualified without an authoritative confirmation.
