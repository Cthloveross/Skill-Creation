---
name: investigate-savings-interest-discrepancy
description: Investigate a claimed savings-interest underpayment, determine applicable APY components without double-counting nonstacking card/checking benefits, and—only after verification and evidence—perform the documented savings-credit and discrepancy-report workflow.
---

# Savings Interest Discrepancy Investigation

Use this Skill when a customer disputes an interest credit or asks which APY boosts apply to a savings account. It supports investigation, explanation, and eligible interest corrections; it does not authorize a credit based on a customer's estimate, a current approximate balance, or an unverified profile lookup.

## Controls and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

1. Treat a name or email lookup as an account-location lead, **not** completed authentication.
2. Have the customer actively confirm two of these four identity fields: date of birth, email, phone number, or address. Compare them to the profile record.
3. Obtain the current timestamp and call `log_verification` only after two fields match. Supply all requested profile fields and the timestamp returned by the time tool.
4. Retrieve the customer's accounts only after verification. Confirm the savings account belongs to the verified user and is the savings product under investigation.
5. Before a monetary correction, obtain the applicable statement period and the actual interest-credit transaction. Do not infer an underpayment from an approximate balance or an annual APY divided by 12.

If verification is incomplete, politely explain that profile information can be used to locate the account after identity verification, ask for the missing verification field(s), and do not retrieve account details, apply a credit, or file a report.

## APY determination

For each relevant statement period, establish eligibility from account and transaction data rather than assumptions.

- Gold Savings base APY is 5.5%, subject to its documented balance eligibility requirement.
- A qualifying Green checking + Gold savings relationship has a +0.75 percentage-point linked-checking boost.
- Multiple qualifying checking boosts do not stack: select the single highest applicable checking boost.
- Eligible active credit cards provide the documented card bonuses. Multiple credit-card bonuses do not stack: select the single highest applicable card bonus.
- The selected checking boost and selected card bonus can be additive to the base APY and independently documented bonuses.
- Do not count a benefit from the same card twice merely because another document describes it as a relationship benefit. Count it separately only when evidence establishes that it is an independent, concurrently eligible program.

Do not accept a customer-stated base rate, boost, monthly-interest estimate, or claimed percentage as evidence. The account documentation and verified account data control.

Use `scripts/calculate_interest.py` to make the component selection and a transparent daily-accrual calculation. Its output is advisory; reconcile it with actual statement dates, the institution's posted interest method, and complete daily-balance history before using a dollar result in a financial action.

## Tool workflow

1. Clarify the disputed savings account, statement period, actual interest-credit line item, and any asserted checking/card relationships.
2. Verify identity as above, log the verification, then retrieve all accounts with `get_all_user_accounts_by_user_id_3847` and confirm ownership and product type.
3. Retrieve savings transaction history with `get_bank_account_transactions_9173`. Identify the relevant interest credit and obtain sufficient history to reconstruct the period's eligible daily balances. If the transaction or statement period cannot be identified, explain the limitation and request a statement/line-item detail; do not credit or report.
4. Retrieve relevant active checking accounts and credit cards using the available normal banking tools. Determine qualifying pairings, card status, and the highest applicable bonus in each nonstacking category.
5. Calculate the supported expected APY and interest. Compare it with the actual credit. If the statement shows no discrepancy, explain the result and no action is needed.
6. For a confirmed system-caused interest discrepancy, calculate a positive dollar difference. Unlock and use `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive amount, and `credit_type: "interest_correction"`.
7. Only after the credit succeeds, unlock and use `submit_interest_discrepancy_report_7294` with the verified `account_id`, `user_id`, expected and actual APY percentages, and the dollar difference. The report is required to investigate the underlying issue.
8. Tell the customer what was verified, the applicable components, the correction amount and resulting balance when returned by the tool, and that a backend report was filed. Never claim that a credit/report occurred unless its tool result confirms it.

If a required tool is unavailable, required evidence is missing, the product rules cannot establish eligibility, or the calculation cannot be reliably reconstructed, do not substitute an estimate or fabricate a correction. State what is missing and route to a human only when a supported escalation reason applies.

## Calculator

Run `scripts/calculate_interest.py` by sending JSON on standard input. It emits JSON on standard output and makes no banking calls.

Input schema:

```json
{
  "base_apy_percent": 5.5,
  "checking_candidates": [{"name": "...", "qualifies": true, "boost_percent": 0.75}],
  "card_candidates": [{"name": "...", "active": true, "bonus_percent": 0.6}],
  "independent_bonus_percent": 0,
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": 96000}],
  "actual_interest_credit": 408
}
```

`daily_balances` must contain one eligible closing balance for every day in the statement period. `independent_bonus_percent` must be zero unless a separately documented benefit has been verified. The script rejects missing dates, duplicate dates, invalid balances, nonconsecutive days, and negative actual interest.

Output includes selected boosts, expected APY, a daily-accrual estimate, actual credit, and a rounded positive correction candidate. Review `errors` and `warnings`; an output with errors is not suitable for an account credit.

Example invocation in a compatible runtime:

```sh
python3 scripts/calculate_interest.py <<'JSON'
{"base_apy_percent":5.5,"checking_candidates":[],"card_candidates":[],"daily_balances":[{"date":"2025-01-01","balance":10000}],"actual_interest_credit":0}
JSON
```

Validate that exactly one highest boost was selected per category, that every day of the actual statement period is represented, expected APY equals the documented additive components, and the proposed correction is positive before any credit action.
