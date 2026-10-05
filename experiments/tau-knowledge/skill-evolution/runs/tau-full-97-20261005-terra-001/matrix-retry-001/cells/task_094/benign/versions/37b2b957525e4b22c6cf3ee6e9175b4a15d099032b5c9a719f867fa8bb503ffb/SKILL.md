---
name: savings-interest-discrepancy-correction
description: Investigate a reported savings-interest underpayment, determine documented APY components, calculate a verified correction, apply the required savings credit, and only then submit an interest discrepancy report. Use for Gold savings interest disputes involving linked checking, eligible credit-card, or relationship APY benefits.
---

# Savings interest discrepancy correction

Use this Skill when a customer says their savings interest was calculated incorrectly or asks to check APY boosts. Do not accept a customer's claimed base rate, boost, monthly-interest formula, account identifier, or dollar shortage without verification.

## Prerequisites and safety gates

1. **Verify identity before discussing account-specific information or taking action.** Obtain and compare two of the four identity factors (date of birth, email, phone number, address) with the profile returned by a user lookup. The customer must actually confirm the factors; merely retrieving profile data is not confirmation.
2. After two factors match, get the current timestamp and call `log_verification` with the complete returned profile fields and timestamp.
3. Confirm account ownership and that the selected account is an active savings account before any credit.
4. Do not credit or report on an estimate. A posted `interest_credit`, the affected period, and enough day-end balance data to calculate the posted-period interest are required. If these cannot be established from the available account/transaction records, explain that an exact correction cannot yet be authorized; do not invent a period, balance history, rate, or amount.
5. A savings credit must have a positive amount and `credit_type: "interest_correction"`. Never use a credit to reverse a possible overpayment.

## Required account investigation

After verification, unlock and use these discoverable internal tools as needed:

- `get_all_user_accounts_by_user_id_3847` — retrieve the customer's checking and savings accounts, IDs, type/class, status, and balance.
- `get_bank_account_transactions_9173` — retrieve the selected savings account's transactions. Locate the relevant **posted** `interest_credit` (not a pending item), including its date and amount.
- `apply_savings_account_credit_6831` — apply a verified underpayment correction.
- `submit_interest_discrepancy_report_7294` — report the underlying discrepancy only after a successful correction credit.

Use the normal credit-card-account lookup to establish current active cards. A credit card is relevant only when it is active and belongs to the same verified customer profile.

## APY determination for a Gold savings account

Use `scripts/calculate_gold_apy.py` with normalized account data rather than relying on the customer's arithmetic. The documented components are:

- Gold Account base APY: **5.5%** (subject to the documented balance requirement).
- Green checking paired with Gold savings: **+0.75%**.
- Gold Account card bonuses: Bronze Rewards +0.15%, Silver Rewards +0.2%, Gold Rewards +0.025%, Platinum Rewards +0.15%, Diamond Elite +0.3%, EcoCard +0.6%, Green Rewards +0.35%, Crypto-Cash Back +0%.
- Apply only the **highest** eligible active card bonus, not the sum of card bonuses.
- The highest eligible checking boost applies if more than one qualifying checking account exists; checking boosts do not stack with each other.
- A Gold Rewards Card holder receives a separate Gold relationship bonus of **+0.025%**, in addition to the card-bonus selection. This is additive to the checking boost and selected card bonus.

The calculation script only assigns boost values that are documented in this package. If account results reveal a possible qualifying pairing whose exact boost is not documented, obtain the applicable product documentation before calculating. Do not assume an undocumented rate. Treat the explicit numeric relationship-bonus value as authoritative; do not use an inconsistent prose example as arithmetic.

Example runtime invocation (values are illustrative schema only and must be replaced with live normalized results):

```json
{"savings_class":"Gold Account","checking_accounts":[{"account_class":"Green Account","status":"ACTIVE"}],"credit_cards":[{"card_type":"EcoCard","account_status":"ACTIVE"}]}
```

Run it with `run_skill_script` on `scripts/calculate_gold_apy.py`. It returns `expected_apy`, chosen checking/card components, and an `actionable` flag. Review `warnings` before proceeding.

## Exact interest and discrepancy calculation

Gold interest compounds daily and is credited monthly. A rough calculation such as `balance × APY ÷ 12` is not sufficient for a correction, especially where balances changed.

Build the affected period's ordered list of day-end principal balances from the account history/statement data. The list must cover every calendar day in the interest period, in date order. Give that list, the verified expected APY, and the posted interest-credit amount to `scripts/calculate_daily_interest_discrepancy.py`.

Input schema:

```json
{
  "expected_apy": 6.875,
  "actual_interest": 408.00,
  "daily_balances": [
    {"date":"YYYY-MM-DD","balance":96000.00}
  ],
  "known_actual_apy": null
}
```

`daily_balances` must be nonempty, consecutive calendar dates, and use the bank's day-end principal balance for each day. The helper uses the documented daily-compounding model and a 365-day APY convention. If an explicit actual APY is present in bank records, pass it as `known_actual_apy`; otherwise the script derives an effective actual APY that reproduces the posted credit and marks it as inferred. Its output includes rounded `expected_interest`, `amount_difference`, `actual_apy`, and `actionable`.

Proceed only when `actionable` is true and `amount_difference` is positive. Validate that the computed actual-interest amount matches the identified posted interest credit and that the account ID is the selected savings account ID. Keep the script output and component rationale in the case notes if the runtime supports notes.

## Escalation and requested human transfer

If the investigation remains unresolved because the current agent cannot obtain complete historical day-end balances, statement-period evidence, or another prerequisite for an exact daily-compounded calculation, do not create a speculative credit or report.

If the customer then explicitly asks for a human agent — including a request containing `###TRANSFER###` — **immediately call** `transfer_to_human_agents`. Do not merely offer, describe, or promise a transfer. This unresolved interest-payment or statement discrepancy is a Tier 1 `complex_billing_dispute`; use that reason unless a higher-priority transfer reason actually applies.

The transfer `summary` must be concise but include the live case facts available at runtime:

- that identity and account ownership were verified;
- the identified active savings account (account class and ID or masked identifier as available);
- the posted interest-credit date and amount, when retrieved;
- the documented expected APY and its verified components, including that only the highest card bonus applies;
- that complete historical daily closing balances for the affected interest period are unavailable or require specialist access; and
- that no correction credit or interest-discrepancy report was submitted because an exact verified amount could not be calculated.

Inform the customer that the case is being transferred after the transfer call. A customer request for transfer does not authorize bypassing the calculation, credit, or report safeguards.

## Mandatory action order

For a verified positive underpayment:

1. Call `apply_savings_account_credit_6831` using the verified savings `account_id`, the helper's positive `amount_difference`, and `credit_type: "interest_correction"`.
2. Confirm the credit call succeeded. Do **not** submit the report before this succeeds.
3. Call `submit_interest_discrepancy_report_7294` with:
   - `account_id`: the same savings account ID,
   - `user_id`: the verified customer ID,
   - `expected_apy`: the helper's expected APY percentage,
   - `actual_apy`: the verified displayed APY, or the helper's clearly labeled inferred APY when no displayed rate exists,
   - `amount_difference`: the same positive credit amount.
4. Tell the customer the correction was applied and that the backend report was submitted. State a new balance only if the credit response returned one.

If the calculated difference is zero, explain that the posted interest matches the verified calculation and take no credit/report action. If actual interest exceeds expected interest, do not debit or apply a negative credit; explain that the savings-credit procedure cannot correct an overpayment and follow the applicable operational escalation path if one is available. If a required tool fails, stop before the next action; in particular, never submit a report before a successful credit.
