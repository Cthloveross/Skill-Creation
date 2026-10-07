---
name: savings-and-credit-card-yield-comparison
description: Compare a customer's eligible savings-account and credit-card combinations by one-year savings interest minus recurring annual card fees, then safely carry out a selected personal-savings opening when authorized and supported by the available banking tools.
---

# Savings and Credit Card Yield Comparison

Use this Skill when a customer wants to choose a savings account, optionally pair it with a credit card for APY benefits, or proceed to open a personal savings account. It separates an informational recommendation from banking actions: a recommendation alone must not create an account, submit a card application, or transfer money.

## Inputs to collect and verify

Collect the intended opening deposit and expected maintained balance, desired savings-account classes, whether the customer requires a new card, and the time horizon (this Skill uses one full year unless the customer specifies otherwise). Confirm which cards are actually available or approved; do not present a card as openable merely because its product terms are known.

For each savings candidate, establish:

- the applicable base APY tier at the assumed balance;
- opening and ongoing balance requirements, plus any relevant fees;
- each eligible card's APY bonus and annual fee;
- any documented relationship or linked-checking boost; and
- whether bonuses stack. Credit-card APY bonuses do **not** stack: use only the highest applicable credit-card bonus.

APY is already an annualized yield. For a stable balance held for one full year, estimate annual interest as `balance × combined APY / 100`; do not apply daily compounding a second time to a stated APY. Add documented additive bonuses only where eligibility is confirmed.

Use `scripts/rank_combinations.py` for deterministic calculations. Its JSON input is:

```json
{
  "balance": 30000,
  "opening_deposit": 30000,
  "require_card": true,
  "relationship_bonus_percent": 0,
  "checking_boost_percent": 0,
  "savings_options": [
    {
      "account_class": "Example Account",
      "opening_minimum": 500,
      "ongoing_minimum": 1000,
      "tiers": [{"minimum_balance": 0, "apy_percent": 2.5}],
      "annual_maintenance_fee": 0,
      "card_options": [
        {"card_name": "Example Card", "eligible": true, "apy_bonus_percent": 0.5, "annual_fee": 50}
      ]
    }
  ]
}
```

The script receives that object on stdin and emits one JSON object on stdout. It returns eligible ranked combinations, rejected savings options, and the highest-net combination. `balance` is the balance assumed for the entire year; `opening_deposit` defaults to it. `require_card` defaults to `false`. Supply only confirmed bonuses and costs. A card option represents one card choice, never a sum of several card bonuses.

Example executor call:

```text
run_skill_script(relative_path="scripts/rank_combinations.py", input_json=<comparison input>)
```

Validate the output before relying on it: `ok` must be true, every recommended row must have `eligible: true`, its `base_apy_percent` must correspond to the selected tier, and `net_one_year` must equal `annual_interest - annual_card_fee - annual_maintenance_fee` to cents. Explain assumptions, unresolved eligibility, and any products excluded because requirements could not be confirmed.

Use `references/product-comparison-data.md` to build candidates from the supplied product evidence. It is a product-data aid, not proof of a particular customer's approval, account status, or current pricing. Do not invent a missing APY, fee, boost percentage, or eligibility rule.

## Customer-facing comparison

Give a concise table containing the savings account, card (if any), total APY, estimated one-year interest, annual card fee, other explicitly modeled annual fees, and net one-year amount. State that this is an estimate assuming the stated balance remains in the account for the year. If a product's qualification is unknown, label it conditional rather than ranking it as an available choice.

If the customer requires both products but no card has confirmed eligibility, provide the best savings-only information separately and explain that no card-inclusive recommendation can yet be confirmed. Follow the documented card-application process through supported channels; no credit-card-opening action tool is supplied by this Skill, so never fabricate one or ask the customer to call an internal tool.

## Mandatory controls before any banking action

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before opening a savings account or moving funds:

1. Verify identity by confirming two of the four identity fields (date of birth, email, phone number, address) against the customer record, obtain the current time, and call `log_verification` with all required record fields. A name or a prior record lookup is not identity verification.
2. Confirm authority and ownership of the selected funding checking account.
3. Confirm personal-savings eligibility: identity is verified; at least one active Rho-Bank checking account exists; the relevant checking account has been held at least 14 days; the customer has fewer than five personal savings accounts; and no account is in collections or has a negative balance. Stop if any condition fails or cannot be verified.
4. Confirm the precise official `account_class` ending in `Account`, the opening-deposit requirement, the customer's selected source account, available balance, applicable fees, transfer limits/cutoffs, destination details, and explicit authorization.

For a selected personal savings account, unlock `open_bank_account_4821` and call it only after all prerequisites pass, with the authenticated `user_id`, `account_type` set to `savings`, and the exact confirmed official `account_class`. Report the new account details.

Then ask whether the customer authorizes an immediate opening-deposit transfer. If yes, unlock and use `transfer_funds_between_bank_accounts_7291` only after reconfirming source ownership, available funds, amount, source and new destination IDs, fees/limits/cutoffs, and transfer confirmation. If no, state clearly that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed. Do not transfer merely because a comparison used an assumed balance.

If any required data, tool result, or authorization is missing, do not proceed with that banking action; explain exactly what must be confirmed or resolved.
