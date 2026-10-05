---
name: savings-interest-discrepancy
version: 1.0.0
description: Investigate a claimed savings-interest underpayment, calculate supported APY and credit amounts, and safely complete the required interest-correction credit-before-backend-report workflow. Use for alleged missing savings APY boosts, tier rates, relationship bonuses, or other interest calculation errors.
---

# Savings Interest Discrepancy

Use this Skill when a customer disputes interest credited to a savings account. Never accept the customer's stated account, rate, balance, monthly-interest estimate, or claimed boost as verified evidence.

## Inputs and outputs

Runtime inputs are the customer conversation, identity/profile lookup results, account lookup results, credit-card results where relevant, transaction history, and the product documentation applicable to the actual savings account class.

The required operational outputs, when the prerequisites below are met, are:

1. A positive `interest_correction` credit to the verified savings account.
2. A backend discrepancy report submitted *after* that credit succeeds, with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and positive `amount_difference`.
3. A customer-facing explanation using verified figures and the result of each completed action.

Do not perform either money-moving/reporting action merely because the customer alleges an error.

## Mandatory workflow

### 1. Verify identity and authority first

1. Resolve a profile using a customer-provided identifier, such as email or exact case-sensitive name.
2. Confirm two of the four identity fields (date of birth, email, phone number, address) directly with the customer. A lookup result alone is not confirmation. Do not unnecessarily reveal unconfirmed values.
3. Retrieve the current time and call `log_verification` with the complete profile fields and that timestamp only after two fields have been confirmed.
4. Treat the identity as verified only after that logging call succeeds. The savings account selected below must belong to this verified user.

If the customer cannot complete verification, do not retrieve account-specific details, apply a credit, or submit a report. Explain the verification requirement and request the minimum missing confirmation.

### 2. Gather authoritative account and transaction evidence

The account, transaction, credit, and report operations are discoverable agent tools. Unlock each named tool before calling it:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831`
- `submit_interest_discrepancy_report_7294`

Call the account lookup with the verified `user_id`. From its result, select the active savings account whose account class/type matches the disputed product. Also identify active checking accounts on that same profile. Do not infer an account ID from a last-four-digit claim.

Call transaction history for the selected savings account. Locate the posted `interest_credit` for the disputed monthly cycle. Record its exact amount and posting date. Pending transactions, an unrelated interest period, and a verbal interest amount are not sufficient.

Gather any records needed to establish rate eligibility, including active eligible credit cards from `get_credit_card_accounts_by_user`, and relevant balances/statement-period data. If the account view does not establish a claimed link or an exact statement period, obtain an authoritative account/statement detail rather than assuming it.

### 3. Determine the supported APY

Read documentation for the actual savings product and applicable checking pairing. Build the rate only from verified, active, eligible components:

- base APY and any documented balance/tier qualification;
- the highest eligible linked-checking boost, not the sum of checking boosts;
- the highest eligible credit-card APY bonus, not the sum of card bonuses;
- each separately documented relationship bonus and tier bonus that may stack with those categories.

Credit-card bonuses and checking boosts each select their own highest value. The selected credit-card bonus and selected checking boost may stack with separately documented relationship or tier bonuses when product rules allow it. A Gold Rewards Card's distinct Gold-account relationship bonus must not be silently discarded merely because a different card provides the highest *credit-card* bonus; verify that the relationship-bonus eligibility is active separately.

For Gold-account policy facts supplied with this package, consult `references/gold_account_apy_rules.md`. It is a policy reference, not proof that a particular customer qualifies.

Never use a customer-provided base rate or boost when it conflicts with product documentation. Do not treat a customer’s approximate current balance as the balance for every day in a statement cycle.

### 4. Calculate the monetary discrepancy

Use `scripts/calculate_interest_discrepancy.py` after collecting the inputs. It accepts the documented APY components, either daily closing balances or a confirmed constant balance and day count, the posted interest amount, and (for report readiness) the actual APY applied by the system/statement.

The helper assumes that a published APY is an effective annual yield and models daily compounding using `(1 + APY) ** (1/365) - 1`. Confirm that this agrees with the applicable statement/product calculation convention before relying on it. Use authoritative statement calculations instead if the bank supplies a different convention, partial-period treatment, day-count convention, or rounding rule.

Only round the final expected interest and difference to cents. The amount to credit is `expected_interest - actual_interest`; it is not a simple annual rate times an approximate balance divided by twelve unless the authoritative statement supports that approximation.

The actual APY in the backend report must be the actual rate applied/displayed by the system or statement. Do not relabel an inferred monthly yield as the applied APY. If the rate is unavailable, continue gathering evidence; do not submit a report with a guessed value.

### 5. Execute in the required order

Proceed only if all conditions hold:

- identity verification was logged;
- the selected account is the verified customer's savings account;
- a relevant posted interest credit and correct period/balance data were verified;
- the expected and actual calculation is supported by documentation;
- the difference is positive; and
- both expected and actual APYs are known for the report.

Then:

1. Call `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive calculated cent amount, and `credit_type: "interest_correction"`.
2. Confirm that the credit succeeded. If it fails or has an ambiguous result, do **not** submit the backend report and do not retry blindly; preserve the result and follow the normal operational escalation path.
3. Only after a successful credit, call `submit_interest_discrepancy_report_7294` with the verified `account_id`, verified `user_id`, documented `expected_apy`, authoritative `actual_apy`, and the same positive `amount_difference` credited.
4. Inform the customer of the correction and investigation status without promising a backend outcome. Do not make a duplicate credit if the report later fails.

## Stop and clarification conditions

- **No discrepancy or a non-positive difference:** do not credit and do not report. Explain the supported calculation.
- **Unverified identity/ownership:** stop before account-specific actions.
- **Missing account, posting, period, daily/average balance data, linkage eligibility, or actual applied APY:** request the missing authoritative detail or use an available internal source. Do not fabricate a rate or amount.
- **Unsupported account product or undocumented bonus:** do not assume that a rate rule applies; obtain the corresponding product documentation.
- **Multiple possible interest credits:** identify the precise statement cycle before calculation.

## Calculator interface

Run `scripts/calculate_interest_discrepancy.py` through the Skill script runner. The script reads one JSON object on stdin and writes one JSON object on stdout.

Required fields:

- `base_apy` (number): documented base APY percentage.
- `checking_boosts` (array of numbers): verified eligible checking boosts; use `[]` if none.
- `credit_card_bonuses` (array of numbers): verified eligible card bonuses; use `[]` if none.
- `relationship_bonuses` and `tier_bonuses` (arrays of numbers): verified additive bonuses; use `[]` if none.
- Either `daily_balances` (nonempty array of nonnegative daily closing-balance numbers) **or** `constant_balance` (nonnegative number) plus `days` (positive integer).
- `actual_interest` (nonnegative number): posted interest for the exact cycle.

Optional:

- `actual_apy` (nonnegative number): exact APY actually applied/displayed. Supplying it enables report-readiness validation.
- `days_in_year` (positive integer, defaults to `365`) only when documentation authorizes another convention.

For example, a non-production calculation can be run with an input shaped like:

```json
{
  "base_apy": 4.0,
  "checking_boosts": [0.25],
  "credit_card_bonuses": [0.1, 0.2],
  "relationship_bonuses": [],
  "tier_bonuses": [],
  "constant_balance": 25000,
  "days": 30,
  "actual_interest": 85.0,
  "actual_apy": 4.1
}
```

Validate the result before actions: `status` must be `ok`, `credit_ready` must be true, `report_ready` must be true, `amount_difference` must be greater than zero, and all returned values must match the evidence collected. The script is calculation support only; it never applies a credit or submits a report.
