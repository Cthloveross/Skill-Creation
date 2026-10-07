---
name: gold-savings-interest-discrepancy-review
description: Verify and resolve a possible Gold Savings interest underpayment when a customer has linked checking accounts and eligible credit cards. Use for a request to explain an interest credit, select non-stacking APY boosts, calculate a supportable correction, and—only after verification—apply the required savings credit and backend discrepancy report.
---

# Gold Savings Interest Discrepancy Review

Use this Skill for Gold Savings interest concerns involving linked checking accounts and credit-card APY bonuses. It distinguishes an entitlement/rate explanation from a verified monetary discrepancy; never issue a credit merely because a customer reports an approximate balance or interest amount.

## Applicable policy facts

For a Gold Savings account:

- Base APY is **5.5%**, subject to applicable balance eligibility.
- Interest compounds daily and is credited monthly.
- A linked Green checking account provides **+0.75%** APY to Gold Savings; a linked Purple checking account provides **+0.10%**.
- Linked-checking boosts do **not** stack: select only the single highest eligible boost.
- Eligible credit-card bonuses include Gold Rewards **+0.025%**, Platinum Rewards **+0.15%**, and EcoCard **+0.60%**.
- Credit-card bonuses do **not** stack: select only the single highest eligible active-card bonus.
- The selected checking boost and selected card bonus do stack with the base rate.

Thus, calculate the contractual APY as:

`base APY + max(eligible checking boosts) + max(eligible active-card bonuses)`.

Do not represent unlisted account/card types as eligible without applicable product documentation. Consider only active accounts held on the same customer profile and, for a historical correction, confirm they were applicable during the reviewed statement period.

## Required safe workflow

1. **Authenticate before account-specific disclosure or any account-changing action.** Ask the customer to confirm two of the four identity fields (date of birth, email, phone number, address). Compare them to the profile returned by an approved lookup. After both match, get the current timestamp and call `log_verification` with the complete profile values and timestamp. Do not treat data read from the profile itself as the customer's confirmation.
2. Identify the customer using an approved lookup. Do not rely on an identifier or account information embedded in a prior conversation snapshot.
3. Unlock and use `get_all_user_accounts_by_user_id_3847` to retrieve all current linked bank accounts. Identify the Gold **savings** account and all checking accounts. Confirm account status and ownership. If there is no Gold savings account, stop and explain that an interest review cannot proceed.
4. Unlock and use `get_credit_card_accounts_by_user` if it is not directly available. Retain only active cards and identify the documented eligible card bonuses. Confirm historical eligibility if the statement period predates an account opening or closure.
5. Unlock and use `get_bank_account_transactions_9173` for the Gold savings account. Locate the relevant monthly interest-credit transaction and obtain the statement start/end dates, daily balances or an authoritative average/daily-interest detail, and the system-displayed applied APY if available. Use only the discoverable tool's actual argument schema; ordinarily this lookup is made for the savings `account_id`.
6. Determine the rate components using the non-stacking rules. Use `scripts/interest_review.py` to make the selection and, when complete daily balance data are available, calculate the expected daily-compounded interest and difference.
7. **Only correct a confirmed positive discrepancy.** A supportable correction requires: verified customer/account ownership; the exact Gold savings account; the relevant actual interest credit; the statement period; sufficient daily-balance/interest detail to calculate the expected amount; and applicable APY components. An approximate current balance, an unknown statement period, or a customer-reported credit alone is insufficient.
8. If the computed expected interest exceeds actual interest after normal cent rounding, unlock `apply_savings_account_credit_6831` and apply the positive difference first, using `credit_type: "interest_correction"`. Never apply zero or negative amounts.
9. After a successful credit, unlock `submit_interest_discrepancy_report_7294` and submit the report with the savings `account_id`, `user_id`, expected APY, actual APY, and the same positive dollar difference. Use an authoritative displayed applied APY where available; a calculated implied rate should be labelled as such in your notes.
10. If the credit attempt fails or its outcome is unknown, do **not** submit a report claiming that a credit was applied and do not repeat the action. Explain the status and follow the approved escalation path if needed.

The action order is mandatory: **credit first, report second**. Do not report or credit when the records do not establish a discrepancy.

## Calculator

`scripts/interest_review.py` receives one JSON object on stdin and emits one JSON object on stdout.

Input schema:

- `base_apy_pct` (number, required): documented base annual APY as a percentage.
- `checking_boosts_pct` (array of nonnegative numbers, default `[]`): only eligible checking boosts.
- `card_bonuses_pct` (array of nonnegative numbers, default `[]`): only eligible active-card bonuses.
- `daily_balances` (array of nonnegative numbers, optional): one exact end-of-day principal balance for every day in the reviewed interest period, in chronological order.
- `actual_interest` (nonnegative number, optional): the posted monthly interest for that same period.
- `actual_apy_pct` (nonnegative number, optional): the rate displayed by the bank for that period, if available.

Example runnable input (replace placeholders with retrieved, period-specific values):

```json
{
  "base_apy_pct": 5.5,
  "checking_boosts_pct": [0.75],
  "card_bonuses_pct": [0.6],
  "daily_balances": ["<day-1 balance>", "<day-2 balance>"],
  "actual_interest": "<posted-interest>",
  "actual_apy_pct": "<displayed-rate>"
}
```

The output identifies the selected components, `expected_apy_pct`, and, when daily balances are supplied, `expected_interest`. With actual interest, it returns a cent-rounded `amount_difference` (`expected - actual`), a `positive_discrepancy` flag, and (when no displayed actual rate was supplied) a mathematically inferred annual-effective rate. `daily_balances` must cover the complete interest period; otherwise use the script only for rate selection and do not use it to authorize a correction.

## Validation and customer response

Before an account-changing call, verify all of the following:

- The selected checking boost is the maximum among qualifying pairings, not the sum.
- The selected card bonus is the maximum among eligible active cards, not the sum.
- The balance data and actual interest cover the same complete statement period.
- Expected and actual amounts are compared after cent rounding.
- The discrepancy is strictly positive and the credit result is confirmed before reporting.

Tell the customer the base rate, which single checking boost and single card bonus were selected, and whether records verified an underpayment. If records are unavailable, explain the expected rate components but clearly state that no correction or report can be made until transaction/statement detail establishes the period and amount. Do not disclose full account numbers, unrelated balances, addresses, or card details.