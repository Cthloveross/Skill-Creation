---
name: banking-account-combination-advisor
description: Advise a banking customer on a checking and savings combination that meets stated features and maximizes applicable savings APY, then safely handle confirmed account closure, opening, funding, and overdraft-protection requests using the declared banking tools.
---

# Banking Account Combination Advisor

Use this Skill when a customer wants to compare checking and savings accounts, particularly where linked-account APY boosts, overdraft protection, balance tiers, ATM-rebate benefits, or account replacement are relevant. It supports advice first and only performs banking actions after all required checks and the customer's explicit selections are obtained.

## Mandatory control for every banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Separate information from action

1. Treat a request to compare products or explain eligibility as informational. Provide the comparison without opening, closing, funding, linking, or changing anything.
2. Do **not** infer consent to close an account, open a replacement, transfer an opening deposit, or enable overdraft protection merely because the customer expressed a goal or asked which account is best.
3. After advising, ask for an explicit selection and authorization for each requested action. If the customer wants an immediate opening-deposit transfer, obtain the chosen source account and amount and confirm that transfer separately.
4. A name lookup alone does not authenticate the customer. Before an account action, verify two of date of birth, email, phone number, and address against the customer record, obtain the current timestamp, and log the complete verification record.

## Recommendation method

Use the supplied product disclosures and customer facts at execution time. Do not assume a benefit exists because it is common to a product category.

1. Extract the customer constraints:
   - amount expected to remain in savings;
   - required checking features (for example, an overdraft protection transfer from linked savings rather than merely no overdraft fees);
   - required savings features (for example, actual out-of-network ATM rebates, including their monetary or count cap);
   - opening and ongoing balance requirements, withdrawal needs, and any stated preference for fee avoidance.
2. Remove options that do not clearly meet every required feature. Distinguish an overdraft transfer service from an account that simply declines overdrafts, and distinguish ATM rebates from a waived bank ATM fee.
3. For each remaining savings candidate, calculate the APY applicable to the stated balance. Apply a tier based on the balance for that tier's terms.
4. Add only documented applicable bonuses:
   - A qualifying linked checking boost is additive to the savings APY.
   - When the customer has more than one qualifying checking account, use only the highest applicable checking boost; do not sum checking boosts.
   - When the customer has multiple eligible credit cards, use only the highest applicable card bonus; do not sum card bonuses.
   - Documented relationship or direct-deposit bonuses may stack only where the disclosures say they do.
   - Do not claim a bonus until ownership, eligibility, and the required link/condition are confirmed.
5. Compare effective APY first, then plainly identify material tradeoffs such as balance minimums, rebate caps, transfer fees, and whether a bonus depends on linking. If the customer asks for the highest APY, do not substitute a lower rate merely because it has a stronger ancillary perk unless the higher-rate option fails a stated requirement.
6. Explain the recommendation in a concise calculation, state assumptions and unknowns, and ask the customer whether to proceed with the selected accounts.

Use `scripts/recommend_accounts.py` for deterministic ranking where structured candidate information is available. Its output is advisory; confirm its assumptions against the source disclosures before communicating a result.

## Safe procedure after the customer explicitly selects accounts

### Closing a personal checking account

Before calling a closure tool, verify identity and authority; confirm the target account is owned by the customer; retrieve and verify its status, opening date, current holdings, and pending transactions; identify its closure tier; calculate whether an early-closure fee and notice period apply; and obtain explicit confirmation to close after disclosing the applicable fee and timing.

A closure may proceed only when the account is OPEN, has no pending transactions, and either has a sufficient balance to pay any applicable early-closure fee or has a zero balance when no fee applies. Never infer that “I moved the money out” establishes these requirements. If a needed check cannot be performed with an available tool, explain what remains unverified and do not close the account.

### Opening a checking account

Before opening, verify identity, authority, account ownership where relevant, and the checking-product eligibility requirements: verified customer, required age, no more than the permitted number of personal checking accounts, and no checking account closed for cause within the required lookback. Confirm the full official `account_class` string ending in `Account`, then use the declared account-opening tool with the authenticated user ID and `account_type` of `checking`.

### Opening a savings account and funding it

Before opening, verify the customer is eligible: identity verified; an active qualifying checking account exists and meets any tenure rule; the customer is below the savings-account count limit; no account is in collections or negative; and the customer has selected the exact full official savings `account_class` ending in `Account`.

Use the declared account-opening tool with `account_type` of `savings`. Then ask whether the customer wants the required opening deposit transferred now. Only if the customer explicitly authorizes it, verify source-account ownership, available balance, limits, the required deposit, destination account, fees, and confirmation requirements before calling the declared internal-transfer tool. If funding is deferred, state the documented funding deadline and consequence of non-funding.

### Enrolling overdraft protection

Do not enable overdraft protection simply because it influenced the recommendation. Obtain explicit enrollment authorization. Before enabling it, verify the protected checking account and funding savings account are both customer-owned, eligible for the service, active, and correctly selected; verify the disclosed per-transfer fee; confirm the customer understands that a transfer may be charged even if it covers only part of a shortfall; and use only a declared normal banking tool or documented customer self-service path. If no supported enrollment tool/path is available, explain that limitation without representing the service as enabled.

## Customer response template

For an informational request, respond in this order:

1. Name the checking and savings options that satisfy the stated functional requirements.
2. Show each qualifying savings option's rate calculation at the stated balance, including only confirmed bonuses.
3. Recommend the highest effective APY option that meets all constraints, or explain why no option can be established from the available disclosures.
4. List important conditions: balance thresholds, rebate cap, link requirement, and overdraft-transfer fee.
5. State that no account changes have been made and ask for explicit confirmation if the customer wants a particular closure, opening, funding transfer, or overdraft-protection enrollment.

Avoid asserting exact projected interest dollars unless the day count, balance history, compounding convention, and all applicable bonuses are known. APY is an annualized yield, and daily compounding/variable balances can change credited interest.

## Script interface

Run:

```sh
python3 scripts/recommend_accounts.py <<'JSON'
{
  "balance": 10000,
  "required_checking_features": ["overdraft_protection_linked_savings"],
  "required_savings_features": ["out_of_network_atm_rebates"],
  "checking_options": [],
  "savings_options": [],
  "credit_card_bonuses": [],
  "relationship_bonus_pct": 0,
  "direct_deposit_bonus_pct": 0
}
JSON
```

Input is JSON. `checking_options` uses `name`, `features`, and `boosts` (a map from savings name to APY percentage-point boost). `savings_options` uses `name`, `features`, `tiers` (objects containing `min_balance` and `apy_pct`), `opening_minimum`, and `ongoing_minimum`. Optional candidate-specific `relationship_bonus_pct` and `direct_deposit_bonus_pct` override the top-level values. `credit_card_bonuses` is a list of applicable percentage-point bonuses; only the maximum is used.

The script emits JSON with `recommendations`, sorted from highest effective APY to lowest, plus `excluded` explanations and `errors`. Validate that the proposed recommendation has no unmet required features, the balance satisfies each stated opening and ongoing minimum, and that every reported bonus appears in the calculation components. A nonempty `errors` list means do not use the ranking as a completed recommendation.
