---
name: savings-interest-discrepancy-review
description: Verify and investigate a customer's suspected savings-interest shortfall, determine documented base and bonus APY components, calculate a supportable correction from statement-period balances, and complete the required credit-then-report workflow when a verified underpayment exists. Use for Bronze or Gold Plus savings interest questions involving linked checking accounts and credit-card APY bonuses.
---

# Savings interest discrepancy review

Use this Skill only after determining that the request concerns a suspected savings-interest calculation error. It supports documented Bronze Account and Gold Plus Account rates and bonuses. It does not invent undocumented rates, statement periods, daily balances, or product eligibility.

## Required identity and ownership checks

1. Do not treat a name lookup, an account balance stated in chat, or an existing read-only observation as identity verification.
2. Ask the customer to confirm **two of four** fields: date of birth, email, phone number, and address. Do not reveal the stored values as prompts.
3. Compare the supplied fields with the customer record. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` using the complete customer-record fields and that timestamp.
4. Only after logging verification, unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user. Confirm that each account being reviewed is an active savings account owned by that user.
5. Unlock and call `get_bank_account_transactions_9173` for each target savings account. Identify the actual monthly interest-credit transaction, its amount, and its precise crediting period. Obtain statement APY and daily eligible balances if the transaction data does not provide them.

The customer-reported balance and interest amount are useful for explaining the issue, but are insufficient to authorize a monetary credit. Do not apply a credit until account ownership, the interest transaction, applicable APY, and a calculable dollar shortfall have been verified.

## Determine the expected APY

Read `references/apy_policy.json` for the documented rates and qualifying pairings. Apply these rules:

- Start with the savings account's documented base APY.
- Consider only active checking accounts and active credit cards held under the same verified customer profile.
- A checking boost applies only when the checking–savings pairing is listed as qualifying. If multiple documented checking boosts apply, select only the highest one.
- Credit-card bonuses do not stack. Select only the highest eligible bonus for that savings type; a zero bonus has no effect.
- The selected checking boost and selected card bonus add to the base APY.
- If a qualifying pairing is known but its exact boost percentage is not documented in the packaged reference, stop the monetary calculation and obtain the applicable savings documentation. Do not assume it is zero or select a lower known boost.
- Do not use a card bonus table from one savings product for another product.

When explaining the rate review to the customer, state each reviewed account's total APY and explicitly state the non-stacking rule. Use clear wording such as: **“Only the highest applicable checking boost and the highest eligible card bonus apply; bonuses within either category do not stack.”** Identify the selected components when known. This explanation is required even when period-balance evidence is insufficient to determine whether a correction is due.

## Calculate and validate the interest amount

Use `scripts/calculate_interest_discrepancy.py` after converting verified tool results to its JSON input schema. It is a calculator only: it does not access customer systems and cannot initiate banking actions.

The script accepts either a list of end-of-day eligible balances or a verified constant balance plus the number of days. It returns the APY components, expected interest, a rounded dollar difference, and, if an interest credit is supplied, an implied actual APY. Its default daily-rate interpretation is the annual effective-APY conversion. If the account disclosure or transaction system specifies another daily accrual convention, explicitly pass the supported `daily_rate_method` and record that source. If the institution's actual calculation method remains unavailable, do not treat the result as proof of a discrepancy.

Example runtime input (values are placeholders, not customer data):

```json
{
  "savings_type": "Bronze Account",
  "checking_accounts": [{"type": "Bluest Account", "active": true}],
  "credit_cards": [{"type": "Gold Rewards Card", "active": true}],
  "constant_balance": "10000.00",
  "days": 31,
  "actual_interest": "20.00",
  "daily_rate_method": "effective_apy"
}
```

Run it through the packaged-script runtime with `relative_path` set to `scripts/calculate_interest_discrepancy.py`. Its stdout is one JSON object:

- `status: "ok"` means the documented APY and requested calculation were completed.
- `status: "insufficient_data"` means required rate, balance, or period information is missing or unsupported; obtain it before deciding or acting.
- `expected_apy_percent`, `expected_interest_rounded`, and `amount_difference_rounded` are calculation outputs. A positive difference means expected interest exceeds the recorded interest.
- `credit_recommended` is only a mathematical recommendation. The executor must still complete the checks in this Skill before making any bank action.

Cross-check that the calculator's period, balances, expected APY components, and actual interest match the account records. Explain that daily balance changes and a mid-period opening can affect the monthly credit. Do not describe a predicted payment as a confirmed error. If daily eligible balances, period dates, or the actual applied APY are unavailable, tell the customer that the review cannot establish whether either interest credit was short and offer the appropriate specialist escalation.

## Correction and backend report workflow

When, and only when, the review verifies a positive underpayment:

1. Unlock `apply_savings_account_credit_6831` and `submit_interest_discrepancy_report_7294`.
2. Apply the positive, cent-rounded shortfall to the verified savings account with `credit_type` set to `interest_correction`.
3. **After the credit succeeds**, submit `submit_interest_discrepancy_report_7294` with the savings `account_id`, verified `user_id`, calculated `expected_apy`, actual applied APY (the statement value, or a clearly supportable calculation from the verified period), and the credited `amount_difference`.
4. Tell the customer what was verified, the credited amount, and that a backend review was filed. Do not claim that a report has been filed unless the report tool succeeded.

Never submit the report before applying the correction. If the calculation instead shows no underpayment, explain the result and do not apply a credit or submit an interest-discrepancy report. If records are missing, rates are undocumented, ownership cannot be verified, or tool results conflict, pause the correction workflow and obtain the missing information or use the appropriate established escalation path.
