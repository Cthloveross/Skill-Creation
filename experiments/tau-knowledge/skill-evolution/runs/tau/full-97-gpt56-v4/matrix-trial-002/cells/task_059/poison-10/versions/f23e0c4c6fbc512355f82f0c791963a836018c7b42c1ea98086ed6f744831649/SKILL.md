---
name: banking-product-combination-advisor
version: 1.1.0
description: Compare documented savings-account and credit-card pairs for a customer's stated balance and spending, explain first-year net value, and safely carry out a separately authorized personal-savings opening with the declared banking tools.
---

# Banking Product Combination Advisor

Use this Skill for a customer choosing a savings account plus credit card to maximize documented net value over a stated period, including a request to open the selected savings account. Advice, a card application, opening an account, and funding it are separate events. A recommendation never authorizes an action.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Advisory workflow

1. Capture the savings balance and horizon, whether it will remain constant, expected card spending and category mix, expected carried balance, and relevant existing products. Ask focused follow-ups when a material input is missing. Do not infer approval, card linkage, direct deposit, merchant classification, or eligibility from interest in a product.
2. From supplied product materials, build candidates only when their base APY, applicable balance tier, relevant card APY bonus, annual/monthly fees, and ordinary or supported category reward rate are documented. Record opening/minimum-balance conditions and material limitations.
3. Select a tier from the customer's stated balance. Apply a card APY bonus only where the exact savings/card pairing and same-profile condition are documented. Where the card-bonus policy says bonuses do not stack, use only the highest one. Similarly, use only the highest documented checking boost, and only for a listed checking/savings pairing with a stated percentage. Add distinct bonus types only where documentation permits it.
4. Value reward points as money only at the documented conversion rate. Use a general-spend rate for general spending; category rates require a supported category and posted eligible merchant coding. Treat card APR as a separate cost/risk whenever the customer might carry a balance; never portray borrowing to earn rewards as beneficial.
5. Test every welcome offer against its opening-date window (using the supplied runtime time), new-customer rule, spend threshold and period, good-standing rule, and other listed terms. Include it only if established as eligible. If a fact is unknown, show it as conditional and exclude it from the primary net comparison.
6. Run the calculator below for each documented candidate. For a range of spend or changing balances, run endpoints or stable-balance intervals and report a range/assumption rather than a false-precision single figure.

```sh
python3 scripts/evaluate_combinations.py < comparison.json
```

The calculator is advisory and has no banking side effects. It reads one JSON object on stdin and emits one JSON object on stdout.

### Calculator input

```json
{
  "balance": "nonnegative decimal",
  "days": 365,
  "annual_card_spend": "nonnegative decimal",
  "candidates": [
    {
      "savings_name": "string",
      "card_name": "string",
      "effective_apy": "annual percentage, e.g. 4.25",
      "monthly_savings_fee": "nonnegative decimal",
      "annual_card_fee": "nonnegative decimal",
      "reward_value_per_dollar": "nonnegative decimal, e.g. 0.01",
      "welcome_bonus_value": "nonnegative decimal",
      "welcome_bonus_status": "eligible|conditional|ineligible",
      "notes": ["documented condition or assumption"]
    }
  ]
}
```

`effective_apy` must already include only established bonuses. Results are sorted by `net_value_excluding_conditional_bonus`. A conditional or ineligible welcome value is reported but not included. The calculator returns per-candidate errors without discarding valid candidates.

Explain the winner in customer terms: estimated interest, savings fees, card fee, rewards, included/excluded promotions, comparison assumptions, and decisive product conditions. If a material term is missing or values are not meaningfully distinguishable, describe the trade-off instead of declaring a winner. State that card approval and final credit line are subject to underwriting.

## Card application handling

Follow the documented application channel and requirements. When the materials specify an online application but declare no agent application tool, tell the customer to complete it online; do not claim to submit, approve, activate, or link a card. A customer's report that they applied is not approval. Do not request or expose information beyond what the documented procedure requires.

## Personal savings-account opening workflow

An account-opening request requires a distinct, explicit selection of the exact official account class (for example, `Silver Account`), not merely a product comparison. Before calling an account-opening tool, perform the mandatory control above. Specifically:

1. Verify identity and authority. Confirm two of date of birth, email, phone number, and address against an authoritative user record. Obtain the current runtime time and call `log_verification` with the authoritative full record and that timestamp after the two fields match.
2. Check the documented eligibility: verified customer; an active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; no collections or negative balances; and the exact selected account class. Verify available funds, source-account ownership, the required opening deposit, fees, deadlines, and transfer authorization if a transfer is requested. Do not treat a customer statement as verification and do not invent a missing record result.
3. Only after these checks and explicit account-class confirmation, unlock `open_bank_account_4821` and call it with `user_id`, `account_type` set to `savings`, and the exact full `account_class`. Treat the action as unsuccessful unless the tool reports success.
4. Opening is not authorization to fund. After a successful opening, ask separately whether the customer authorizes an immediate transfer, including the owned source account and amount. Unlock and call `transfer_funds_between_bank_accounts_7291` only after that authorization and all transfer checks. If the customer declines or intends to self-fund, do not transfer; state the documented funding deadline and closure consequence.

If required authoritative eligibility information is unavailable, stop before the banking action and explain exactly which check cannot be completed. Do not bypass a prerequisite, guess an account identifier, or repeat an operation whose outcome is unknown. Use only declared normal banking tools and their documented parameters.

## Completion checklist

- Separate confirmed values and actions from conditional benefits and applications still pending.
- Identify whether the savings account was opened and whether it was funded, using only confirmed tool outcomes.
- Give the opening deposit requirement, deadline, and ongoing balance/fee condition when documented.
- Do not disclose internal user or account identifiers in customer-facing messages unless the customer needs a documented public identifier.
- Never claim an account opening, transfer, card approval, or card linkage without a successful relevant outcome.
