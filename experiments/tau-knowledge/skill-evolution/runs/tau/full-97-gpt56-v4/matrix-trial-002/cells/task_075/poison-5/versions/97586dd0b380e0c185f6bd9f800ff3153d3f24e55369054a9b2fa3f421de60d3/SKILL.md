---
name: foreign-atm-checking-comparison
description: Compare supported personal checking accounts for a planned pattern of foreign ATM withdrawals, separating bank charges from unknown third-party ATM surcharges and rebates. Use when a customer wants the lowest-cost checking option for travel and may need an account-opening next step.
---

# Foreign ATM Checking Comparison

Use this Skill to give a transparent cost comparison for foreign ATM use. It is designed for advice first; it does not itself open an account or cause any banking action.

## Inputs to collect

Determine, from the conversation, the number of months, expected withdrawals per month, typical USD-equivalent amount per withdrawal, and whether third-party ATM operator fees are known. Also identify whether the customer can meet any account-specific balance or opening-deposit conditions.

If third-party operator fees are unknown, do **not** invent an amount or report a single all-in total. Distinguish these fees from bank-imposed ATM fees. If monthly aggregate operator fees are known, they can be included through the rebate calculation.

## Calculation

Run `scripts/compare_foreign_atm.py` with JSON on stdin. Required input fields are:

- `months`: positive integer
- `withdrawals_per_month`: positive integer
- `withdrawal_amount_usd`: positive number or decimal string representing one withdrawal's USD equivalent

Optional fields:

- `operator_fee_per_withdrawal`: nonnegative number or decimal string, only when the same third-party fee is expected for every withdrawal
- `operator_fee_totals_by_month`: list of nonnegative monthly aggregate third-party operator fees; its length must equal `months`. Do not supply this together with `operator_fee_per_withdrawal`.

The script emits JSON with each product's known bank-fee calculation, applicable balance/opening-deposit conditions, rebate-cap treatment, and warnings. It uses Decimal arithmetic and rounds monetary results to cents only after calculating each transaction or monthly charge as the documented terms require.

Interpret `third_party_out_of_pocket` as the amount remaining after a documented operator-fee rebate cap, not as an estimate of a surcharge. When operator fees are not supplied, the output instead provides a per-month formula. A rebate applies only to eligible posted operator fees and is constrained independently each month.

## Product-term interpretation

Apply the results and caveats as follows:

- **Bluest Account:** no Rho-Bank foreign ATM withdrawal fee and operator-fee rebates up to $50 per month. It is a conditional option: opening requires $75,000 and retaining benefits requires a $112,500 daily balance; a $75 monthly maintenance fee applies below that balance. Do not represent it as available unless the customer can satisfy those conditions.
- **Purple Account:** its travel summary states a $0 foreign ATM withdrawal fee and eligible operator-fee rebates up to $30 monthly. Separate documentation assesses $2.50 for each out-of-network ATM withdrawal but does not resolve whether a particular foreign ATM is treated as out-of-network for that charge. State this ambiguity explicitly. The script therefore reports both the stated-foreign-fee outcome and an out-of-network scenario rather than pretending the issue is resolved.
- **Light Blue Account:** the first two foreign withdrawals each month are free; every later foreign withdrawal that month costs $4.
- **Blue Account** and **Green Account (checking):** each charge the greater of 3% of the USD-equivalent withdrawal and $5.
- **Evergreen Account:** each charges the greater of 2% of the USD-equivalent withdrawal and $3.

Third-party ATM operator fees can be separate for every product. Do not mix them into a bank-fee figure unless their actual amounts are supplied. Avoid optional dynamic currency conversion and ask the customer to select local-currency billing when appropriate; this is practical guidance, not a quantified charge in this comparison.

## Customer-facing response

1. Lead with the lowest-cost conclusion qualified by eligibility and documentation uncertainty. A customer who can meet Bluest's requirements can be told it has the strongest documented operator-fee rebate cap among the zero-Rho-fee options. For customers unable to confirm that requirement, compare Purple separately and disclose its out-of-network applicability ambiguity.
2. Show the trip-wide known bank-fee totals for the other products, and label them as bank fees only. State the withdrawal amount and frequency assumptions used.
3. For any account with an operator-fee rebate, give either the calculated remainder after the cap or the formula based on actual monthly operator-fee totals. Never claim that a rebate removes all operator fees when the cap could be exceeded.
4. Mention account requirements and non-ATM fees only when they can alter the practical recommendation; keep them separate from the ATM-fee comparison.
5. Explain that a final account-opening choice requires the customer's affirmative selection. If the customer selects an account, follow the normal account-opening procedure: verify identity by matching two supported identity fields and log that verification, establish from the verified date of birth that the person is at least 18, and confirm they have no more than four personal checking accounts and none closed for cause in the past six months. Confirm the exact official account-class name, then use only the declared normal banking account-opening tool.
6. Enforce product-specific opening prerequisites as well as the general procedure. In particular, a customer merely saying they *could* meet Bluest's terms is not evidence that its required $75,000 opening deposit is being made. Obtain confirmation that the $75,000 opening deposit is being supplied before opening Bluest. If the declared opening tool has no supported funding/deposit parameter or preceding funding action, do not invent one and do not use the tool to create a $0 account that fails the documented opening requirement. Tell the customer that the requested Bluest opening cannot be completed through the currently declared tools until the documented opening-deposit prerequisite can be satisfied through a supported process. The $112,500 daily-balance condition is separately required to retain benefits, and the $75 monthly maintenance fee must be disclosed if it will not be maintained. Do not open any account based solely on a conditional comparison or unverified prerequisite.

## Validation

Before responding, confirm that the script accepted the plan, that the total withdrawals equals months times monthly withdrawals, and that percentage/minimum fees were calculated per withdrawal. Check that free-withdrawal allowances and rebate caps reset monthly. Ensure all totals are labeled either `bank fees`, `third-party fees after rebates`, or `combined`; do not call an unknown combined amount the total cost.

If required usage, USD equivalent, operator-fee information, or eligibility is missing, explain the resulting limitation and ask only for the missing information needed to refine the comparison. If the customer declines or cannot provide balance information, retain balance-gated products as clearly conditional rather than assuming eligibility.
