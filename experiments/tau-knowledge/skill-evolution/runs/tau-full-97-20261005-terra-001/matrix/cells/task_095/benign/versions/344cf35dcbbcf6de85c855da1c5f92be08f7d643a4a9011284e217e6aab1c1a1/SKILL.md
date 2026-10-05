---
name: gold-savings-interest-discrepancy
version: 1.1.0
description: Investigate a possible Gold savings interest shortfall by verifying the caller, collecting authoritative account and transaction data, selecting non-stacking card and checking APY bonuses, calculating a reproducible expected monthly credit, and—only for a verified shortfall—applying the required correction before filing an interest discrepancy report.
---

# Gold Savings Interest Discrepancy

Use this Skill when a customer questions interest credited to a Gold savings account, particularly when they may hold multiple eligible checking accounts or credit cards. It supports explanation of current or likely rate components, but it does **not** authorize an adjustment without a verified account, period, balance history, and posted interest credit.

## Governing rules

For a Gold savings account, determine the rate from authoritative product documentation and historical account facts for the statement period:

1. Confirm the account was eligible for the documented Gold base APY. The documented base APY is **5.5%**; the normal minimum balance is $10,000. Do not invent a lower-tier rate if eligibility or balance history is unavailable.
2. Evaluate eligible active credit cards for the period. Credit-card APY bonuses do **not** stack: apply only the single highest applicable card bonus. For Gold, the documented bonuses include Bronze Rewards +0.15%, Silver Rewards +0.2%, Gold Rewards +0.025%, Platinum Rewards +0.15%, Diamond Elite +0.3%, EcoCard +0.6%, Green Rewards +0.35%, and Crypto-Cash Back +0%.
3. Evaluate checking accounts only when their Gold-savings pairing was active/linked for the period. Linked-checking boosts do **not** stack: apply only the highest qualifying boost. Green checking + Gold savings qualifies for +0.75%; Purple checking + Gold savings qualifies for +0.1%. Neither may be presumed linked merely because the customer owns both accounts.
4. Card and selected checking bonuses may stack with each other. Documented relationship bonuses are separate additive components when their own eligibility is verified. In particular, Gold Rewards Card holder documentation describes a +0.025% Gold relationship bonus and a reduced $5,000 Gold minimum; do not confuse that relationship bonus with the card-bonus selection rule.
5. Gold interest compounds daily and is credited monthly. A reported approximate balance and an unlabeled monthly credit cannot establish either the statement APY or a dollar shortfall.

For a historical investigation, use account status, linkage, balances, and cards **during the affected statement period**, not only their current values.

## Required controls and data collection

1. **Verify identity before account-specific disclosure or any account action.** Ask the caller to confirm two of the four identity fields (date of birth, email, phone number, address). Retrieve the customer record using the normal user lookup tool, compare the supplied values without unnecessarily repeating sensitive data, obtain the current time, then call `log_verification` with all required record fields and the timestamp. A name alone, a user ID, or data visible in a prior agent observation is not two-field verification.
2. After verification, use `get_all_user_accounts_by_user_id_3847` (unlock it as a discoverable agent tool if required) to identify the Gold savings account, relevant checking accounts, and active credit cards. Confirm the savings account ID and ownership.
3. Use `get_bank_account_transactions_9173` (unlock if required) for the Gold savings account. Locate the affected transaction with `type: interest_credit` and `status: posted`. Record its posting date and positive amount. Transaction results are reverse chronological, so inspect the relevant prior monthly credit rather than assuming the most recent item is the disputed one.
4. Obtain the statement start/end dates and daily balance history for the cycle. Also establish the checking-to-savings linkage and eligible card status for that cycle from authoritative account records. If the available tool output cannot prove a historical fact, ask the customer for their statement or explain that no precise determination is possible; do not infer it from current ownership.
5. Check for Gold base-rate eligibility and each applicable documented component. Preserve the source/reason for every component used or excluded.

If verification, account ownership, the statement period, a posted interest credit, period balances, historical card status, or historical linkage is unavailable, provide a limited explanation of the selection policy and state exactly what is missing. Do not apply a credit or submit a discrepancy report based on an estimate.

## Required current/prospective rate guidance

After the authorized all-accounts lookup, give useful **current/prospective** guidance whenever the returned portfolio establishes the relevant current holdings, even if historical statement facts remain unavailable. This guidance is not a conclusion about the disputed cycle.

For a current Gold account with an active EcoCard, Green checking, and Purple checking, tell the customer explicitly:

- Gold's documented base APY is **5.5%**.
- **EcoCard +0.6%** is the highest eligible card bonus among the observed cards. Card bonuses do **not stack**; this is the highest eligible card bonus, **not all card bonuses** added together.
- Green's documented Gold linked-savings boost is **+0.75%**, while Purple's documented Gold linked-savings boost is **+0.1%**.
- If each pairing is currently linked and otherwise qualifying, Green is the higher/highest qualifying checking boost. Checking boosts do **not** stack: use the highest qualifying checking boost, **not both** Green and Purple boosts.
- The selected card bonus and selected checking boost can combine with the Gold base APY when the applicable eligibility conditions are met.

Use wording such as: “Currently, the documented Gold base APY is 5.5%. Your active EcoCard is the highest eligible card bonus at +0.6%, rather than all card bonuses stacking. Green's Gold boost is +0.75% and Purple's is +0.1%; if linked and qualifying, the highest qualifying checking boost is Green's +0.75%, not both checking boosts.”

Immediately distinguish this from the historical investigation: current ownership or current account status cannot establish the historical statement-period linkage, historical eligibility, applied APY, daily balances, or an exact October-cycle shortfall. Do not state that the current components were applied, or should have been applied, to the past cycle unless that period-specific evidence is verified.

## Calculation

Build input for `scripts/apy_audit.py` from the verified facts. The script receives only calculation inputs; do not put account IDs, customer identifiers, or sensitive identity data into its input.

Run it with:

```text
python3 scripts/apy_audit.py < audit_input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

```json
{
  "base_apy": "number, percentage points",
  "card_bonuses": [{"name": "string", "apy": "number", "applicable": true}],
  "checking_bonuses": [{"name": "string", "apy": "number", "applicable": true}],
  "relationship_bonuses": [{"name": "string", "apy": "number", "applicable": true}],
  "period_days": "positive integer, required for dollar calculation",
  "constant_balance": "nonnegative number, optional alternative to daily_opening_balances",
  "daily_opening_balances": ["nonnegative numbers, one per accrual day, optional"],
  "actual_interest": "nonnegative number, optional posted interest amount",
  "days_in_year": "optional positive integer; defaults to 365"
}
```

`daily_opening_balances` means each day’s principal balance before that day’s interest accrual and excludes unposted accrued interest. It is preferred whenever balances changed. Provide exactly one of `constant_balance` or `daily_opening_balances` for a dollar calculation. `period_days` must equal the number of daily balances when that form is used. Supply only bonuses already confirmed applicable for the historical period; the script chooses the maximum card and checking bonus and adds all supplied relationship bonuses.

The script returns the component breakdown, total expected APY, and—when balance data is present—the daily-compounded expected interest. It uses the APY as an effective annual yield and a daily factor of `(1 + APY/100)^(1/days_in_year) - 1`. It reports the expected amount rounded to cents and, if `actual_interest` was supplied, the rounded expected-minus-actual difference. This creates an auditable calculation; it does not prove a discrepancy when the inputs are not verified.

Validate the result before action:

- `selected_card_bonus` is the highest eligible card bonus, not a sum.
- `selected_checking_bonus` is the highest eligible linked-checking boost, not a sum.
- `total_expected_apy` includes documented, verified relationship components separately.
- `expected_interest_rounded` is based on the actual statement length and balance data.
- `amount_difference` is positive before considering an interest-correction credit.

## Resolution workflow

When an exact, verified positive shortfall exists:

1. Unlock and call `apply_savings_account_credit_6831` with the verified Gold savings `account_id`, the positive verified shortage in dollars, and `credit_type: "interest_correction"`.
2. **Only after the credit succeeds**, unlock and call `submit_interest_discrepancy_report_7294` with the savings `account_id`, verified `user_id`, `expected_apy`, `actual_apy`, and the verified dollar difference. Use the actual applied APY from the statement/system record; do not derive it from an approximate balance and payment.
3. Tell the customer the correction amount and that the backend report addresses the underlying calculation issue.

If the actual credit equals or exceeds the verified expected amount, do not apply an interest-correction credit. If a system record nonetheless conflicts with the calculation, document the evidence and follow the bank’s escalation/reporting procedure without falsely reporting a customer shortfall.

## Customer-facing explanation when evidence is incomplete

First report any confirmed transaction fact precisely, for example its posted interest-credit amount and posting date. Then provide the applicable current/prospective rate guidance described above when current holdings support it. Explain that this does not prove historical eligibility.

State that the highest—not all—eligible card bonus is used, and the highest qualifying linked-checking boost is used; the checking boosts are **not both** applied. The selected card and checking categories can combine with an eligible relationship bonus. State that an approximate balance and a monthly credit alone cannot confirm the correct APY because interest is daily compounded and balance/linkage may have changed. Request the statement period, posted interest-credit date and amount, displayed or applied APY, daily balance changes, and confirmation or account-record evidence of which checking account was linked during that period. Clearly say that you cannot establish a historical shortfall or issue a correction until those facts are verified.
