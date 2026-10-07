---
name: savings-interest-dispute-review
description: Review a savings-interest dispute involving base APY, linked-checking boosts, and credit-card APY bonuses. Use when a customer asks whether an interest credit or displayed savings APY is correct, especially where multiple qualifying cards or checking accounts may be involved.
---

# Savings Interest Dispute Review

Use this Skill to give documented rate information, safely investigate a customer-specific interest payment, and—only when supported by account and transaction evidence—correct an error and file the required backend report.

## Core policy

Treat APY figures as percentage points, not multipliers.

1. Start with the documented base APY for the savings product and confirm that any tier or balance condition was met for the relevant period.
2. Determine all *qualifying* linked checking boosts for that savings product. Checking boosts do not stack: select only the highest qualifying boost.
3. Determine all active eligible credit-card bonuses on the same profile. Credit-card bonuses do not stack: select only the highest applicable card bonus.
4. Add the base APY, selected checking boost, selected card bonus, and any separately documented relationship or tier bonuses that apply. Do not double-count a card benefit as both a card bonus and a relationship bonus unless the governing product documentation clearly establishes them as distinct benefits.
5. The qualifying checking boost and the selected card bonus can stack with one another.

Do not validate a claimed monthly interest amount by simply dividing an APY by 12. Interest may compound daily, balances and rates can change during a statement period, and interest is credited monthly. A period-specific calculation needs the statement-period dates, daily balances (or reliable balance history), and the posted interest-credit transaction.

## Privacy, authentication, and scope

- A name, an account claim, or a profile lookup is not identity verification by itself.
- Before retrieving or discussing private account details, verify two of the four identity fields (date of birth, email, phone number, address) against the customer record, obtain the current time, and call `log_verification` with all required record fields.
- Public product terms and general rate rules may be explained without revealing private account information.
- Never infer account ownership, an account ID, a statement period, a qualifying balance, or an actual applied APY from a customer estimate.

## Investigation workflow

### 1. Address the question that can be answered now

Correct factual misunderstandings politely. State the documented base rate, linked-checking boost, and each relevant card bonus only where supported by the applicable product documentation. Explicitly state the non-stacking selection rule when several cards or checking accounts are mentioned.

If the customer has not completed verification or lacks period details, explain that no determination of an underpayment, dollar shortfall, credit, or report can yet be made. Ask for verification and, after verification, proceed with internal account lookup rather than requiring the customer to guess an account ID.

### 2. Verify and retrieve evidence

After completing verification:

1. Unlock `get_all_user_accounts_by_user_id_3847` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using the verified `user_id`.
2. Identify the active savings account and all active checking accounts. Confirm the savings account type and the checking/savings pairing(s) against product documentation.
3. Unlock `get_bank_account_transactions_9173`, then retrieve transactions for the identified savings account. Locate posted `interest_credit` entries and record their date and amount.
4. Obtain or request the relevant statement-cycle dates and enough balance history to calculate the applicable daily accrual. Do not use an approximate current balance as a substitute.
5. Retrieve active credit cards using the available credit-card lookup when needed, and apply only the highest eligible card bonus.

If account access, period dates, balance history, or the posted interest credit cannot be established, provide the documented general terms and explain precisely what is missing. Do not apply a credit or submit a discrepancy report.

### 3. Calculate and compare

Use `scripts/calculate_apy.py` to make the selection and arithmetic auditable. Provide documented APY components as percentage-point numbers. The script accepts JSON on standard input and emits JSON on standard output.

Input schema:

```json
{
  "base_apy": "number",
  "tier_eligible": "boolean",
  "checking_boosts": ["number"],
  "card_bonuses": ["number"],
  "other_additive_bonuses": ["number"],
  "daily_balances": ["number, optional"],
  "period_days": "integer, required when daily_balances is omitted",
  "actual_interest": "number, optional"
}
```

- `daily_balances`, if supplied, contains one non-negative closing balance for each day in the period and takes precedence over `period_days`.
- If daily balances are unavailable, the script can calculate a constant-balance estimate from `period_days`; label that result an estimate, not a verified correction amount.
- If `tier_eligible` is false, the script returns a validation error rather than inventing a lower-tier rate. Obtain that rate from the governing documentation.

Run it with `python3 scripts/calculate_apy.py`, sending one JSON object on stdin. Review `selected_checking_boost`, `selected_card_bonus`, `expected_apy`, and, when calculation inputs are complete, `expected_interest` and `difference`. A positive `difference` means expected interest exceeds the posted actual interest.

### 4. Correct a verified discrepancy

Only if ownership is verified, the account is confirmed to be savings, the applicable period-specific inputs are documented, and a real discrepancy exists:

1. Unlock and call `apply_savings_account_credit_6831` with the confirmed savings `account_id`, a positive correction amount, and `credit_type` of `interest_correction`.
2. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with the account ID, user ID, expected APY, actual APY, and dollar difference.
3. Tell the customer that the correction was applied and that the report addresses the underlying calculation issue.

Never submit the report before the credit. Never repeat an action with an unknown result. If an authorized correction cannot be completed because of a system failure, preserve the evidence and use the appropriate supported escalation path rather than claiming a credit was made.

## Response checklist

A complete customer response should:

- distinguish documented general rates from verified account-specific findings;
- explain that qualifying checking and credit-card selections are each highest-only, while the two selected categories may be additive;
- avoid unsupported promises or a fixed monthly-interest claim;
- state the balance/tier and period-data limitations that affect the conclusion;
- say what was corrected and reported only after the corresponding tools have actually succeeded.

## Local validation

The calculator rejects invalid APY values, negative balances, non-integer or non-positive period lengths, an ineligible tier, and an actual interest amount without enough data for an expected-interest calculation. Before relying on a result, ensure its selected bonuses correspond to documented eligible products and that `calculation_basis` is `daily_balances` for a correction decision.
