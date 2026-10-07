---
name: savings-card-yield-advisor
version: 1.0.0
description: Advise a Rho-Bank customer who wants a savings account and credit card combination that maximizes one-year savings interest net of annual card fees; calculate documented APY bonuses, disclose assumptions, and safely proceed with savings-account opening only after verification, eligibility checks, and customer authorization.
---

# Savings and card yield advisor

Use this Skill for a customer comparing a personal savings account and a credit card based on annual savings earnings minus annual card fees. It supports recommendation and, when the customer expressly chooses a savings account, the documented internal account-opening workflow. It does **not** represent that a credit-card application or approval has occurred.

## Product facts available in this package

Use `references/product_terms.json` only for documented terms. Do not infer an undisclosed APY, opening deposit, fee, eligibility condition, checking boost, or card benefit. The facts currently support these comparison rules:

- Savings APY bonuses from credit cards are additive to base APY, but multiple card bonuses do not stack: only the highest applicable card bonus applies.
- A qualifying linked-checking boost, if documented, can be added to the base APY and the selected card bonus. Multiple qualifying checking boosts do not stack; use only the highest. If the customer's checking/savings pairing is absent from an exhaustive qualifying-pairing list, treat its boost as 0%.
- A savings account whose required opening deposit or ongoing required balance exceeds the customer's planned balance is not a suitable recommendation for a customer who intends to maintain only that amount. Do not conceal recurring below-minimum fees as an equivalent alternative.
- Credit-score and subscription statements are preliminary eligibility comparisons, not an approval guarantee. Underwriting and the actual application remain required.

## Recommendation procedure

1. Determine the planned savings balance, whether it will remain on deposit for a full year, known credit-score range, subscription status where required, existing cards, and checking-account type. Resolve material ambiguity before presenting dollar estimates.
2. Build runtime JSON from the documented facts and the customer's supplied circumstances. Use `scripts/rank_combinations.py` to compare documented feasible savings/card pairings. Do not put customer identifiers, a precomputed winner, or an instance-specific answer into the input template or package.
3. For a stable one-year balance, describe the estimate as:

   `estimated net one-year return = balance × (effective APY / 100) − annual card fee`

   where effective APY is base APY plus the applicable card bonus and, only when documented, the selected checking boost. Treat APY as an annual return estimate, not as a promise of a particular daily-balance result. State that withdrawals, deposits, loss of eligibility, rate changes, and account fees can change actual earnings.
4. Present the leading eligible, feasible combination, its effective APY, estimated dollar return, annual card fee, account funding/ongoing balance requirements, and any relevant eligibility conditions. Briefly identify material exclusions, especially accounts whose minimum balance exceeds the planned balance and checking relationships that produce no documented boost.
5. If a card is required to receive the result, explain that it must be applied for through the normal card application channel and that approval is subject to underwriting. Do not claim the customer has a card, has been approved, or has received a bonus until a normal banking tool or account record confirms it.
6. Ask for an explicit choice and authorization before beginning account opening. Advice or a request to compare products is not authorization to open an account or move funds.

### Script interface

Run the following through the packaged runtime:

```text
python scripts/rank_combinations.py <<'JSON'
{
  "balance": 30000,
  "credit_score": 760,
  "subscription": true,
  "checking_boost_pct": 0,
  "savings_products": [
    {
      "name": "Example Savings Account",
      "base_apy_pct": 5.0,
      "opening_minimum": 1000,
      "ongoing_minimum": 1000,
      "below_minimum_monthly_fee": 0,
      "card_bonuses_pct": {"Example Card": 0.2}
    }
  ],
  "cards": [
    {"name": "Example Card", "annual_fee": 0, "minimum_credit_score": 700, "requires_subscription": false}
  ]
}
JSON
```

The script reads one JSON object from stdin and emits one JSON object to stdout. Required top-level fields are `balance`, `savings_products`, and `cards`; each savings product needs `name`, `base_apy_pct`, `opening_minimum`, `ongoing_minimum`, and `card_bonuses_pct`; each card needs `name` and `annual_fee`. `credit_score`, `subscription`, `checking_boost_pct`, `below_minimum_monthly_fee`, `minimum_credit_score`, and `requires_subscription` are optional. It returns `ranked`, `excluded`, and `input_warnings`. Validate that the leading result is feasible, its component APYs match the cited terms, and the displayed net return equals the returned `net_annual_return` rounded to cents.

## Safe opening workflow

Only use this section after the customer explicitly requests account opening and selects the full official savings account class.

1. Authenticate the customer and verify **two of four** identity fields (date of birth, email, phone number, address) against the customer record. After successful matching, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete record values and that timestamp. A name alone is not two-field verification.
2. Complete every prerequisite check before opening: verified identity; at least one active Rho-Bank checking account; checking tenure of at least 14 days; fewer than five personal savings accounts; no accounts in collections or with negative balances. If any condition is false or cannot be confirmed, do not open the account. Explain the specific blocker without exposing unnecessary information.
3. Reconfirm the selected `account_class` exactly as its official full name ending in `Account`, the funding requirement, and the customer's authorization. Do not replace it with an abbreviation.
4. Unlock and call the documented agent tool `open_bank_account_4821` only after the preceding steps pass, with the authenticated user ID, `account_type` of `savings`, and the exact selected `account_class`.
5. After a successful opening, ask whether the customer authorizes an immediate opening-deposit transfer from a specific checking account. If yes, use `transfer_funds_between_bank_accounts_7291` only with the named source account, newly created destination account, and required amount. If the customer declines or has not authorized a transfer, state that the account must be funded within 30 days by internal transfer or external deposit or it will be closed.
6. Report the actual opening and funding outcomes only after the relevant tools succeed. Never repeat an operation whose outcome was reported as unknown.

If a needed normal banking action or required account information is unavailable, explain the limitation and stop rather than fabricating a completion or using unrelated tools.
