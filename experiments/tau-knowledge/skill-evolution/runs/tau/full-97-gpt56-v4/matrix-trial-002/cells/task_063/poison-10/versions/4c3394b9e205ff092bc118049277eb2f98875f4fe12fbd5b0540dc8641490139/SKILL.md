---
name: savings-card-yield-recommendation
version: 1.2.0
description: Compare a personal savings account and a credit card that can affect savings APY, honoring account-delivery requirements and safely handling any later request to apply, open, or fund products.
---

# Savings and credit-card yield recommendation

Use this Skill when a customer wants a savings account and credit card combination that maximizes savings yield. It produces a conditional, evidence-based recommendation first. A recommendation is not an application, account opening, transfer, or statement-preference change.

## Gather and classify facts

Use the current task's authoritative product materials; do not fill gaps from memory. Gather:

- Planned savings balance and whether it will remain constant for the comparison period.
- Savings opening and ongoing minimums, APY tiers, fees, compounding/crediting, and statement-delivery rules.
- Customer hard requirements (for example, mailed paper statements), direct-deposit status, and existing checking product.
- For every candidate card: published score rule, credit-review requirement, subscription requirement, annual fee, and the APY bonus for the specific savings product.
- Bonus stacking rules and the exact checking/savings pairing rule.

Treat a customer's stated score, income, balance, account ownership, or eligibility as unverified. It can support an **estimated** recommendation, never an approval or completed action.

## First conversational turn

If the live conversation has not established the hard constraints, ask a short clarification before naming a best pair. Ask for the approximate credit score, any required-card subscription status, whether the customer wants a card that requires a credit review, whether mailed paper statements are mandatory, and whether direct deposit is active. Do not say that a customer supplied facts merely because they appear in background task materials; use such materials as product evidence unless they are explicitly an authenticated customer answer in the live interaction. Once the customer answers, acknowledge the hard paper-statement requirement directly before comparing products.

If those facts are already present in the live conversation, do not ask them again. Give the recommendation with its conditional eligibility language.

## Compare options

1. Exclude an account if it cannot meet a hard delivery preference. Exclude a card if known facts fail a required score, subscription, or requested credit-review condition. Identify unknowns instead of assuming they pass.
2. Determine the actual tier for the stated balance. Do not treat a tier as marginal unless the disclosure explicitly says it is marginal.
3. Exclude a pair if the balance cannot meet its opening or effective ongoing minimum. Where a documented card changes a savings minimum, use that pair-specific minimum rather than the standard one.
4. Add only active, documented bonuses. Card bonuses do not stack: a comparison row must contain one card's bonus, never a sum of card bonuses. Do not infer a checking boost without an exact qualifying pair.
5. For a constant one-year balance, calculate gross interest as `balance × total_APY / 100`. APY is already annual yield; do not compound it a second time. Separately show card annual fees and, when paper statements are required, twelve monthly paper-statement fees.
6. Recommend the eligible pair with the strongest disclosed net result, while also showing gross interest when the customer's goal is interest specifically. Explain ties rather than inventing a preference. State that rates, daily balances, qualification status, and underwriting can change actual results.

Run `scripts/compare_options.py` for deterministic comparison. It reads one JSON object on standard input and emits one JSON object on standard output. The script never performs a banking action.

### Calculator input schema

```json
{
  "balance": "8000.00",
  "profile": {
    "credit_score": 700,
    "credit_score_confirmed": false,
    "require_credit_review": true,
    "paper_statements_required": true,
    "direct_deposit_active": false,
    "subscriptions": []
  },
  "savings_options": [
    {
      "name": "Official Account Name",
      "opening_minimum": "0",
      "ongoing_minimum": "0",
      "ongoing_minimum_overrides": {"Eligible Card Name": "0"},
      "paper_statements_available": true,
      "paper_statement_monthly_fee": "0",
      "tiers": [{"minimum_balance": "0", "apy_percent": "0"}],
      "direct_deposit_bonus_percent": "0",
      "other_active_bonus_percent": "0"
    }
  ],
  "card_options": [
    {
      "name": "Card Name",
      "minimum_credit_score": 0,
      "credit_review_required": true,
      "subscription_required": null,
      "annual_fee": "0",
      "savings_apy_bonus_percent": {"Official Account Name": "0"}
    }
  ]
}
```

`other_active_bonus_percent` is for non-card bonuses only. Put each card's bonus only in that card's `savings_apy_bonus_percent` map. The output has `ranked_combinations`, `excluded_combinations`, `warnings`, and fee-aware estimates. Before communicating a result, require `status: "ok"`, ensure the recommended row meets the paper requirement and both balance minimums, and review warnings. An empty ranking means no supported savings-plus-card recommendation—not permission to relax a constraint.

Example executor invocation:

```sh
python3 scripts/compare_options.py < comparison_input.json
```

## Transition to banking actions

Only proceed after the customer selects exact products and explicitly authorizes each action. A request to ask whether a transfer is possible is not authorization to transfer.

**Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.** A successful action response is not retroactive proof that skipped prerequisites were verified.

### Identity verification

For an action requiring identity verification, obtain a customer lookup key and two of date of birth, email, phone number, or address. Retrieve the record with the appropriate declared user-information tool, match two supplied fields, obtain the current time, then call `log_verification` with the retrieved record and timestamp. Do not expose unneeded record data. Stop if the lookup or either match fails.

### Savings opening and funding

Before opening a personal savings account, positively verify: identity, authority, account ownership, an active checking account with at least the required tenure, fewer than the permitted number of personal savings accounts, no collections or negative balances, product eligibility, exact official account class, opening requirement, fees, limits, cutoffs, and explicit opening confirmation. If the documented `open_bank_account_4821` tool is available, unlock it and call it only after all of those facts are verified; use `account_type: "savings"` and the exact full official class name.

After a successful opening, ask separately whether the customer authorizes immediate funding. Before an internal transfer, verify the owned source and destination account IDs, available source balance after pending items, amount, fees, limits, cutoff, and explicit transfer confirmation. If the documented `transfer_funds_between_bank_accounts_7291` tool is available, unlock it and use it only with verified IDs and the verified amount. If account lookup or balance verification is not supported by the declared tools, do not accept an unverified ID or balance as a substitute and do not transfer; explain that the transfer cannot be completed in the current channel. If funding is deferred, communicate the documented funding deadline and outcome accurately.

### Credit-card application and statements

Before a card application, verify identity, authority, product eligibility, score/subscription requirements, any available credit conditions, fees, limits, card details, disclosures, explicit credit-check consent, and final submission confirmation. A published minimum and customer-stated income do not guarantee approval. Use only a documented normal banking tool for an application. If no such tool is declared, do not claim to submit an application; explain the supported application route.

Likewise, do not claim paper statements were enabled unless a declared tool completed that preference change. Explain the documented availability and fee, and direct the customer to the supported account-settings route if no tool is available.

Use `scripts/check_action_prerequisites.py` immediately before an action as a completeness check. It reports missing fields only; it neither verifies facts nor performs an action. Its JSON input includes `action` (`open_savings`, `internal_funding_transfer`, `credit_card_application`, or `statement_delivery_change`) and boolean fields for every applicable prerequisite. Proceed only when it returns `status: "ready"` and the booleans are supported by actual verification.
