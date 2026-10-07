---
name: gold-savings-interest-dispute
version: 1.0.0
description: Investigate a claimed Gold savings interest shortfall, verify the customer and account, determine non-stacking APY components, and make an authorized correction and backend report only when an exact discrepancy is supported by account records.
---

# Gold Savings Interest Dispute

Use this Skill when a customer disputes an interest credit on a Gold savings account or asks which checking/card APY benefits apply. It is intentionally conservative: an approximate balance, a claimed interest amount, or an estimated monthly calculation is not enough to credit an account or submit an interest-discrepancy report.

## Relevant policy

- Gold Account base APY is **5.5%**, subject to its documented $10,000 minimum-balance requirement. Review the period's balances, including days that fell below the threshold.
- Gold interest compounds daily and posts monthly as a separate `interest_credit` transaction.
- An active Green checking account paired with Gold savings provides a **+0.75 percentage-point** APY boost. Only the highest qualifying checking boost may be used; checking boosts never stack with one another.
- Credit-card bonuses also do not stack. Select only the highest bonus among active, eligible cards on the same profile. Card bonuses can stack with the selected checking boost and separately documented relationship bonuses.
- Gold Account card-bonus documentation lists Platinum Rewards at +0.15, Gold Rewards at +0.025, and EcoCard at +0.6 percentage points. Do not add all three.
- The Gold Rewards benefits material separately describes a +0.025 relationship bonus. Count a relationship component only when the account/card relationship is verified and it is documented as distinct from the selected card bonus. Do not rely on an internally inconsistent example total; add the stated components arithmetically.

## Required tools and safe sequence

The named account tools are discoverable agent tools. Before calling one, unlock it with `unlock_discoverable_agent_tool`, then invoke it with `call_discoverable_agent_tool`. Use the exact tool names below.

1. **Verify identity before discussing or changing account-specific information.** Ask the customer to confirm at least two of these four values: date of birth, email, phone number, and address. Compare the confirmations with the user record, obtain the current timestamp with `get_current_time`, and call `log_verification` only after two match. A supplied name is useful for lookup but is not one of the two required factors.
2. Identify the customer using a supplied email or name only as needed, then use the verified user ID.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Locate an active Gold **savings** account and all active checking accounts under that profile. Do not assume a card record proves that a savings account exists or is linked.
4. Unlock and call `get_bank_account_transactions_9173` with the Gold savings `account_id`. Find the relevant posted `interest_credit`, its date, and its amount. Establish the statement-cycle dates and obtain the daily balance history necessary to evaluate qualification and daily accrual.
5. Unlock and call `get_credit_card_accounts_by_user` if card status/type are not already safely established. Consider only active cards on the verified profile.
6. Determine the selected checking boost, selected card bonus, and any independently verified relationship/tier components. Use `scripts/interest_review.py` to make the max-selection and arithmetic auditable.
7. Calculate the expected interest using the bank-approved daily accrual convention and actual daily balances for the identified cycle. The helper will not silently invent a day count, balance history, actual APY, or daily-rate convention.
8. Only if an exact, positive discrepancy has been verified, unlock and call `apply_savings_account_credit_6831` **first** with the savings account ID, positive exact cents amount, and `credit_type` `interest_correction`.
9. After a successful credit, unlock and call `submit_interest_discrepancy_report_7294` with the savings account ID, verified user ID, expected APY, actual applied APY, and exact dollar difference. The report must follow the credit, never precede it.

## Decision rules and failure handling

Do **not** apply a credit or submit a report if any of the following are missing or unverified: identity/account ownership, Gold savings account ID, the relevant posted interest credit and cycle, actual applied APY, qualification/balance information, exact daily calculation inputs, or an exact positive difference.

In that situation, explain the known policy without presenting an estimate as a correction. State precisely what is needed next: identity verification if not complete; the Gold account ID; statement or transaction date/cycle for the interest credit; and cycle balance history or statement details. A customer-provided approximate balance and a monthly multiplication do not establish the amount owed because interest is accrued daily and balance eligibility may vary.

Correct factual claims courteously. In particular, do not accept an asserted 5.0% base rate, 1% Green boost, or a sum of every credit-card bonus when the documented Gold rate/pairing/card-selection policy says otherwise. Do not expose account details before verification, do not make a goodwill credit merely because calculation evidence is unavailable, and do not transfer solely to bypass missing verification or evidence.

When records support a correction, tell the customer the selected components, the credited amount, and that the backend report was submitted. When they do not, state that no correction/report was made and what record would allow a transaction-specific review.

## Helper usage

`python3 scripts/interest_review.py` reads one JSON object from stdin and emits one JSON object to stdout. It uses only supplied runtime facts.

Input schema:

- `base_apy` (number, required): verified base APY in percentage points.
- `checking_candidates` (array, optional): objects with `bonus_apy` (number), `active` (boolean), and `qualifies` (boolean); optional `account_id`/`label` are echoed only for audit.
- `card_candidates` (array, optional): objects with `bonus_apy` (number), `active` (boolean), and `qualifies` (boolean).
- `relationship_bonuses` (array of numbers or objects containing `bonus_apy`, optional): only independently verified additive components.
- `actual_apy` (number, optional): actual applied APY from account/statement evidence.
- `interest_credit` (object, optional): identified posted credit with numeric `amount`; `posted` should be true when known.
- `daily_balances` (array of numeric end-of-day eligible balances, optional), `days_in_year` (positive integer, optional), and `daily_rate_method` (either `nominal_divide_365` or `effective_apy_daily`) are required together for an exact modeled expected-interest amount.

A runnable schema check that does not manufacture account facts is:

```sh
printf '{}\n' | python3 scripts/interest_review.py
```

Interpretation:

- `selected_checking_bonus` and `selected_card_bonus` are maxima over active qualifying candidates, or zero.
- `expected_apy` is produced only when `base_apy` is supplied.
- `expected_interest`, `amount_difference`, and `action_ready` are produced only when the exact accrual inputs and a posted interest credit are supplied. `action_ready` additionally requires `actual_apy` and a positive rounded-to-cents difference.
- `errors` lists missing prerequisites. Resolve those through records; never replace them with assumptions.

The helper is a calculation aid, not an authorization or a bank action. Its output never automatically invokes banking tools.
