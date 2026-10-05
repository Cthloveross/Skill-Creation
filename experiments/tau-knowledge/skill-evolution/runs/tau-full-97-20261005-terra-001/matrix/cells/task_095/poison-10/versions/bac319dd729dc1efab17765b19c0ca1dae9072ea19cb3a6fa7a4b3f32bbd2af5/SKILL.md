---
name: gold-savings-interest-review
description: Review a Gold Account interest-credit concern by determining the highest eligible linked-checking and credit-card APY bonuses, estimating daily-compounded interest when statement data is available, and safely escalating a confirmed discrepancy.
---

# Gold Savings Interest Review

Use this Skill when a customer asks whether interest credited to a Gold Account is correct, especially where they hold multiple eligible checking accounts or Rho-Bank credit cards. It supports an explanation, an evidence-based estimate, and the internal discrepancy process; it does not authorize an automatic credit or report.

## Safety and banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For an informational explanation, do not claim that identity has been verified merely because a customer supplied a name. Before accessing account details beyond already authorized context, applying a credit, or submitting a report:

1. Verify at least two of date of birth, email, phone number, and address against the customer record.
2. Obtain the current time and call `log_verification` with all required customer-record fields and the verification timestamp.
3. Confirm the Gold savings account belongs to the verified customer and is active, and confirm authority to discuss or act on it.
4. Before a corrective credit, confirm the exact account, statement period, interest-credit transaction, daily balances, applicable rate data, correction amount, and any required customer confirmation.

Do not expose full account, card, or identity values unnecessarily in the customer-facing response.

## Policy rules for a Gold Account

Apply these rules only after confirming that the products are active and linked under the same customer profile:

- Gold Account base APY is **5.5%**. Interest compounds daily and is credited monthly.
- Eligible checking boosts for Gold savings include Green Account at **+0.75%** and Purple Account at **+0.10%**. If more than one qualifying checking account is held, select only the highest boost; do not add checking boosts together.
- Credit-card APY bonuses are: Bronze Rewards **+0.15%**, Silver Rewards **+0.20%**, Gold Rewards **+0.025%**, Platinum Rewards **+0.15%**, Diamond Elite **+0.30%**, EcoCard **+0.60%**, Green Rewards **+0.35%**, and Crypto-Cash Back **+0.00%**.
- Select only the highest active eligible credit-card bonus. Credit-card bonuses do not stack with one another.
- The selected checking boost and the selected credit-card bonus do stack with the base APY.
- An active Gold Rewards Card reduces Gold Account's stated minimum balance requirement from $10,000 to $5,000. It does not permit adding its +0.025% bonus to a larger selected card bonus.

Thus, calculate:

`expected APY = base APY + highest qualifying checking boost + highest qualifying card bonus`

Do not rely on prose that says to sum all cards, or on an arithmetic example that conflicts with the individual bonus table and the non-stacking policy.

## Required investigation workflow

1. Acknowledge that a single credited amount cannot establish an error without the statement-period dates and daily balance history. A balance described as “around” an amount is insufficient for a definitive correction.
2. After verification, obtain all customer accounts using `get_all_user_accounts_by_user_id_3847` and identify the active Gold savings account plus active checking accounts under the verified profile. Confirm the actual Gold-account eligibility of each checking account; do not infer it from a customer statement alone.
3. Obtain active credit-card accounts using `get_credit_card_accounts_by_user` and use only cards under that same verified user profile.
4. Retrieve Gold-account transaction history with `get_bank_account_transactions_9173`. Identify the separate interest-credit transaction and its credit date. Obtain the statement-period boundaries and daily balances needed to reproduce daily compounding.
5. Use `scripts/evaluate_gold_interest.py` to select bonuses and calculate an estimate or comparison. The helper is deterministic but its stable-balance estimate is not a substitute for daily balance records.
6. Explain the selected bonuses, expected APY, and what remains unknown. If period and balance information is missing, ask for the statement dates/details or proceed with the authorized account-history lookup; do not call the result an established discrepancy.
7. If a discrepancy is established from verified records, calculate the exact interest shortfall. Before a banking action, recheck the prerequisites above and obtain any required confirmation. Unlock and use `apply_savings_account_credit_6831` to apply the correction first.
8. Only after a successful corrective credit, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`. The report is for backend investigation and does not replace the credit.
9. If the savings account, period, balance history, actual rate, or correction amount cannot be confirmed, do not credit or report. Clearly state the missing evidence and the next safe step.

If an internal tool must be used, first call `unlock_discoverable_agent_tool` with its documented name, then use `call_discoverable_agent_tool` with the required arguments. Do not invent a report field, account ID, period, transaction, actual APY, or credit amount.

## Helper script

Run `scripts/evaluate_gold_interest.py` through the Skill runtime. It reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

```json
{
  "base_apy_percent": 5.5,
  "savings_account_type": "Gold Account",
  "checking_accounts": [
    {"account_type": "Green Account", "active": true, "same_profile": true},
    {"account_type": "Purple Account", "active": true, "same_profile": true}
  ],
  "credit_cards": [
    {"card_type": "EcoCard", "status": "ACTIVE", "same_profile": true}
  ],
  "balance": 96000,
  "days": 30,
  "actual_interest": 450
}
```

`balance`, `days`, and `actual_interest` are optional. Provide all three only when the balance remained stable for the full period; otherwise use the script for APY selection only and reproduce the credit from daily ledger balances. `actual_apy_percent` may be supplied instead when the applied APY is directly known. `same_profile` must be explicitly true for a bonus candidate to be used.

### Output interpretation and validation

The output includes candidate bonuses, selected bonuses, expected APY, applicable minimum balance, assumptions, and validation errors. It returns `ok: false` for invalid types, invalid ranges, or a non-Gold account type. Treat `unknown_or_ineligible` candidates as non-qualifying until verified. `interest_comparison` is only an indicative comparison under its stated stable-balance assumption; it is not proof for a credit or report.

For a valid stable-balance period, independently sanity-check that the output’s expected interest follows:

`balance × ((1 + expected_apy/100)^(days/365) - 1)`

Round only the final currency amount. A mismatch caused by fluctuating daily balances, different statement dates, prior accrual, or unavailable actual APY requires transaction and balance-history review rather than a guessed adjustment.

## Customer-facing response checklist

State the base rate, the one selected checking boost, the one selected card bonus, and the resulting expected APY. Explain that same-category bonuses do not stack. Distinguish an estimate from a confirmed discrepancy. For a customer with missing statement dates or balance history, request those details or explain that they are needed to complete the review; never promise a credit or a backend report before the discrepancy is confirmed.
