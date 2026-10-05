---
name: savings-interest-discrepancy-correction
description: Investigate and resolve a verified savings-account interest underpayment. Use when a customer disputes a posted savings interest credit and the agent can verify identity, ownership, account product, transaction history, applicable APY components, and the precise correction amount. Applies a savings interest-correction credit before filing the required backend discrepancy report.
---

# Savings Interest Discrepancy Correction

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and guardrails

Use this workflow only for a verified interest-calculation discrepancy on a savings account. A credit is permitted only after the investigation establishes a positive underpayment. Do not use it for an estimate, a customer-stated rate that conflicts with product documentation, a pending interest item, or an unsupported account type.

A customer name, email lookup, or account lookup alone is not identity verification. Before any banking action, have the customer confirm at least two of these profile fields: date of birth, email, phone number, and address. Compare the responses to the profile record, obtain the current timestamp with `get_current_time`, then call `log_verification` with all required profile fields and that timestamp. The customer must also be the owner or a verified authorized party, and their request to investigate/correct the interest establishes the purpose and authority for this workflow.

Do not treat a quoted balance, approximate statement period, claimed rate, or claimed account pairing as verified evidence. Use the documented tools and records below.

## Required investigation sequence

1. **Verify identity and authority.** Complete and log the two-field identity verification described above. If it cannot be completed, do not reveal account details or take action. For an ownership/verification failure requiring specialist handling, transfer using `account_ownership_dispute`.
2. **Retrieve and validate accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Select only an active savings account owned by that user whose account class/product matches the disputed product. Record its account ID, current balance, status, and product type. Also inspect active checking accounts relevant to linked-APY eligibility.
3. **Retrieve posted transaction evidence.** Unlock and call `get_bank_account_transactions_9173` for the selected savings account. Locate the relevant `interest_credit` transaction with `status: posted`; record its date, amount, and description. Use the account activity to establish the covered cycle and daily balance changes. Do not rely solely on a customer recollection when the period or balance history is material to the calculation.
4. **Determine the documented APY components.** Identify the base rate for the savings product, qualifying active checking/savings pairings, active eligible cards, and any documented relationship or tier bonuses. Validate that the accounts/cards are active and under the same customer profile where required.
5. **Apply non-stacking rules.** Select only the highest qualifying checking boost and only the highest qualifying credit-card bonus. Those selected amounts may be added to the base APY and separately documented tier/relationship bonuses. Do not add every card or checking boost.
6. **Calculate and validate.** Calculate the expected interest over the verified interest period using the institution's documented accrual convention and the verified daily balances. Compare it to the posted interest credit. The helper script can calculate component selection and an explicit accrual model, but it does not verify records or authorize a banking action.
7. **Decide.** Proceed only if all prerequisites are satisfied and the rounded expected interest exceeds the posted amount by a positive amount. If the period, balances, actual applied APY, product eligibility, or calculation convention cannot be substantiated, explain that a precise correction cannot yet be applied and obtain the missing records or transfer for a technical system issue. Never issue a goodwill credit merely because interest evidence is incomplete.
8. **Apply before reporting.** Unlock `apply_savings_account_credit_6831` and call it with the verified savings `account_id`, the positive, cent-rounded discrepancy, and `credit_type: "interest_correction"`. Do not submit a report first and do not call the credit tool with zero or a negative amount.
9. **Submit the backend report.** Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, verified `expected_apy`, verified `actual_apy`, and the credited `amount_difference`. APY values are percentages, not decimal fractions. The amount difference must match the correction supported by the calculation.
10. **Confirm outcome.** Retrieve the account information again if the credit response does not provide an updated balance. Tell the customer the correction amount, that an investigation report was filed, the applicable rate components at a high level, and the resulting balance. Do not claim a new balance that has not been returned or refreshed.

## Gold Account rate reference

Use this reference only when the verified savings product is a Gold Account and the associated qualifying products are active under the same profile. For all other products, obtain their product documentation rather than extrapolating these rates.

- Gold Account base APY: **5.5%**; interest compounds daily and is credited monthly.
- Green checking + Gold savings is a qualifying linked pairing; the Green checking boost is **+0.75%**.
- Gold Account credit-card bonus candidates: Bronze Rewards +0.15%, Silver Rewards +0.20%, Gold Rewards +0.025%, Platinum Rewards +0.15%, Diamond Elite +0.30%, EcoCard +0.60%, Green Rewards +0.35%, and Crypto-Cash Back +0.00%. Use the highest applicable active card bonus only.
- A Gold Rewards Card holder has a separately documented Gold Account relationship bonus of +0.025%. Add it only if the relationship-bonus eligibility is verified; do not confuse it with, or silently duplicate, the Gold Rewards Card credit-card bonus.

For example, a customer assertion that a linked checking boost is 1% is not a basis for a credit when the verified product documentation specifies a different amount. Likewise, an active lower-value card bonus cannot be added to a higher active card bonus.

## Calculation helper

`scripts/interest_discrepancy.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs deterministic arithmetic only; it does not call banking tools.

Input schema:

```json
{
  "base_apy": 0,
  "checking_boosts": [0],
  "credit_card_bonuses": [0],
  "relationship_bonuses": [0],
  "tier_bonuses": [0],
  "actual_interest": 0,
  "actual_apy": 0,
  "daily_balances": [0],
  "accrual_method": "nominal_daily",
  "days_per_year": 365
}
```

All rates are percentage points (for example, `5.5`, not `0.055`). `daily_balances` must contain one verified balance per day in the interest period. `actual_apy` is required for a report-ready result; it must come from verified account/calculation evidence, not an unsupported customer claim. Allowed `accrual_method` values are:

- `nominal_daily`: daily rate is `APY / days_per_year` and each day's interest is accrued against that day's supplied balance.
- `effective_apy_daily`: treats the stated APY as an effective annual yield and derives a daily effective rate.
- `simple_period`: uses `periods_per_year` and a single `average_balance` instead of `daily_balances`; use only where that convention is documented for the product.

Example runnable call (illustrative placeholders only):

```sh
python3 scripts/interest_discrepancy.py <<'JSON'
{"base_apy":5.5,"checking_boosts":[0.75],"credit_card_bonuses":[0.6],"relationship_bonuses":[0.025],"tier_bonuses":[],"actual_interest":400,"actual_apy":5.0,"daily_balances":[100000,100000],"accrual_method":"nominal_daily"}
JSON
```

The result contains `expected_apy`, the chosen highest boost in each non-stacking category, `expected_interest`, `actual_interest`, `amount_difference`, and validation flags. A result is eligible for a correction only when `can_credit` is true. Before using the result, independently confirm that every input is tied to the selected account and actual statement cycle, that the documented accrual convention matches the selected method, and that the cent-rounded output matches the proposed tool amount.

## Failure handling

- If no active owned savings account or no posted interest credit is found, stop; do not choose an account based on a customer guess.
- If the account is not a savings account, this skill does not apply.
- If expected interest is equal to or below actual interest, do not credit and do not file an interest-underpayment report.
- If a bank-system error prevents retrieval or required completion after verification, transfer with `technical_system_error` and summarize the missing tool result and completed investigation steps.
- If the request is actually an incorrectly charged fee, use the fee-refund process instead; do not label it an interest correction.
- If a customer requests a human after the investigation has been completed, use the highest-priority applicable transfer reason; for a completed request with follow-up, use `request_completed_customer_wants_human_followup`.
