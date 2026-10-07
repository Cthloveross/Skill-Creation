---
name: savings-card-net-return-advisor
description: Evaluate a customer's one-year savings-interest-minus-annual-fee objective across a savings account and credit-card pairing, explain APY-bonus stacking correctly, and safely complete or prepare the documented savings-account opening workflow.
---

# Savings and Card Net-Return Advisor

Use this Skill when a customer wants to open or compare a savings account and a credit card and defines the objective as one-year savings interest less annual fees. It separates a financial comparison from product eligibility, identity verification, and account-opening authorization.

## Inputs to establish at runtime

1. Confirm the customer profile without disclosing stored personal data. If an account-opening action may occur, verify identity by having the customer confirm two of the required identity fields, then obtain the current timestamp and create the verification record.
2. Determine the amount the customer intends to deposit and whether it will remain at that level for the one-year estimate. Ask before assuming a transfer, a fixed balance, direct deposit, spending, or qualification for an optional promotion.
3. Retrieve the customer's existing bank accounts and cards. For a savings-account opening, verify all documented prerequisites: verified identity, an active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, and no collections or negative balances.
4. Extract current product facts from the supplied product materials: APY or applicable balance tier, opening and ongoing balance requirements, recurring fees, card annual fee, card-specific savings APY bonus, and any individual card-application requirements.
5. Check whether the customer's existing checking account is one of the explicitly listed qualifying checking/savings pairings. Do not infer a linked-checking bonus from a checking account merely being open. A customer who declines a new checking account can still be evaluated using their current checking account.

## Financial method

Model only the requested objective unless the customer separately supplies spending or other required facts.

- For a stable one-year balance, use `annual interest = balance × effective APY / 100`. APY is already an annual yield, so do not compound it a second time.
- Choose the savings account's balance tier using the stated balance.
- Add the applicable savings-account bonuses that are independently additive under the product terms (for example, a qualifying linked-checking boost or an explicitly documented relationship bonus).
- For credit-card APY bonuses, identify every active linked card and apply **only the largest** applicable card bonus. Never add card bonuses together.
- Subtract the selected new card's annual fee and any account fees that are determinable from the stated balance. Do not treat cash-back earnings, sign-up rewards, waived fees, interest on card balances, foreign-transaction fees, or uncertain promotions as part of the estimate unless their required facts and qualification terms are known.
- State all assumptions, especially that the balance remains unchanged, the card remains active and linked, the qualifying tier is retained, and no card balance is carried.

Use `scripts/rank_pairings.py` for repeatable arithmetic and ranking. Supply current extracted terms rather than embedding product facts in the script.

### Script interface

Run:

```text
python3 scripts/rank_pairings.py < request.json
```

The script reads one JSON object from stdin and emits one JSON object on stdout.

Required input fields:

- `balance`: nonnegative USD balance assumed held for one year.
- `savings_options`: array of objects containing at least `name` and either `base_apy` or `tiers`.
- `cards`: array of prospective new-card objects containing at least `name` and `annual_fee`.

Useful savings fields are `minimum_opening_deposit`, `ongoing_minimum_balance`, `annual_fee`, `monthly_fee_if_below_minimum`, `tiers` (objects with `minimum_balance` and `apy`), `card_bonuses` (card name to APY percentage-point bonus), `additive_bonus_apy`, `eligibility`, and `require_ongoing_minimum`.

Useful card fields are `annual_fee`, `eligibility`, and `bonus_by_savings` (savings-account name to APY percentage-point bonus). `existing_cards` may be supplied to ensure the highest active card bonus is selected across cards already held and the prospective card.

The result contains an ordered `ranked_pairings` list, excluded options with reasons, effective APY, gross one-year interest, known annual fees, net one-year result, selected highest card bonus, and whether each result is confirmed or conditional. Validate that the intended balance and all inputs are current, that an included pairing meets its opening and required ongoing balance rules, and that the top result is not marked conditional before representing it as available.

## Customer-facing recommendation

Present the best *eligible* combination first, followed by the arithmetic in dollars and percentages. Explain any material runner-up and why it lost (lower applicable APY, fee, balance requirement, or unavailable eligibility). If the comparison is conditional, say precisely what must be confirmed; do not describe a conditional result as approval or as an opened account.

The customer may need to submit a credit-card application and receive underwriting approval. No documented credit-card-opening action should be invented. Direct the customer to the supported application flow described in the applicable card materials, and disclose the relevant terms before they apply.

## Savings-account execution workflow

Only execute after the customer has selected the exact full official savings `account_class` and all eligibility checks pass.

1. Unlock and use the documented customer-account retrieval tool to inspect account status, checking tenure, account count, balances, and the source checking account.
2. Unlock the documented savings-opening tool and call it with the authenticated user ID, `account_type` set to `savings`, and the exact official `account_class` ending in `Account`.
3. Ask whether the customer authorizes an immediate opening-deposit transfer, including the source account and amount. Do not treat a comparison request or a stated savings balance as transfer authorization.
4. If authorized, verify that source and destination account IDs differ, both accounts are ACTIVE or OPEN, the source has sufficient funds, the accounts belong to the customer, and the amount is positive USD. Then unlock and call the documented internal transfer tool.
5. If the customer declines funding, communicate the documented funding deadline and closure consequence. If they authorize funding but it cannot be completed, report the failure and offer an adjusted amount or valid source account rather than retrying blindly.
6. Confirm only tool-returned account details and funding status.

If any opening prerequisite fails, do not open the account. Explain the blocking condition and the applicable next step. Never expose internal tool names or parameters to the customer.
