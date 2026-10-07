---
name: investigate-savings-interest-discrepancy
version: 1.1.0
description: Investigate verified customers' suspected savings-interest underpayments, calculate only documented and supportable discrepancies, apply authorized interest-correction credits, submit the required backend discrepancy report after each successful correction, and transfer unresolved statement-interest disputes to a specialist when requested.
---

# Investigate Savings Interest Discrepancies

Use this Skill when a customer reports a missing or incorrect interest payment on a savings account. It supports interest corrections only; it does not authorize speculative credits, fee refunds, or goodwill credits.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, the applicable prerequisites mean:

- Verify identity by matching **two of four** fields (date of birth, email, phone number, address) against the customer record, then call `log_verification` with the complete returned record and the current timestamp. A name or user ID alone is not sufficient.
- Verify the requester is the verified customer and each target account returned by `get_all_user_accounts_by_user_id_3847` belongs to that customer's `user_id`.
- Verify each target is an open/eligible savings account before investigating or crediting it.
- Verify the relevant posted `interest_credit` transaction, its amount, and its statement period from `get_bank_account_transactions_9173`.
- Verify every APY component and its eligibility for the affected period. Do not treat approximate customer estimates, a current balance, or a card/account merely existing today as proof of a historical rate or eligibility.
- Establish the exact positive dollar difference before applying a credit. The credit amount must be greater than zero.

## Tool sequence

1. **Identify and authenticate.** Locate the customer using a supplied name or email if necessary. Ask for and confirm two identity fields. Call `get_current_time` and then `log_verification` only after two fields match.
2. **Find accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with `{"user_id":"..."}`. Identify every savings account under that verified user. Do not rely on an account number or balance supplied conversationally when the account lookup disagrees.
3. **Review activity.** Unlock and call `get_bank_account_transactions_9173` separately for each candidate `account_id`. Locate posted `interest_credit` entries. Review posted and pending activity needed to establish the interest period's daily ending balances and the actual credited interest. Transaction amounts are positive for credits and negative for debits.
4. **Establish the period and rate facts.** Determine the interest-credit date, statement/cycle start and end, daily ending balances (or a reliable equivalent), account tier by each day, qualifying direct deposit where relevant, eligible same-profile active credit cards, eligible linked checking accounts, and any documented relationship-bonus eligibility. Use the product rules in `references/savings_interest_rules.md` only as the documented rate catalog; account and eligibility facts must come from runtime records.
5. **Calculate the expected interest and difference.** Use `scripts/interest_math.py` as described below. Retain the component selection and calculation inputs in the case notes. Compare rounded expected interest with the posted interest credit. A correction is authorized only if the resulting difference is positive and supported by the evidence.
6. **Apply before reporting.** Unlock `apply_savings_account_credit_6831` and call it with:
   ```json
   {"account_id":"<savings account id>","amount":<positive exact difference>,"credit_type":"interest_correction"}
   ```
   Do this separately for each eligible affected savings account. Do not call it if any prerequisite is unresolved or if the difference is zero or negative.
7. **Report after successful credit.** After each successful interest-correction credit, unlock `submit_interest_discrepancy_report_7294` and submit:
   ```json
   {"account_id":"<savings account id>","user_id":"<verified user id>","expected_apy":<percent>,"actual_apy":<percent>,"amount_difference":<positive dollar difference>}
   ```
   The report follows—not precedes—the successful credit. The expected and actual APYs must be supportable for the same affected period.
8. **Escalate unresolved statement disputes on request.** If exact correction prerequisites remain unavailable and the customer explicitly asks for a human transfer, call `transfer_to_human_agents` immediately. This is a Tier-1 `complex_billing_dispute`, not a generic frustration or knowledge-gap transfer. Supply a concise factual summary: the verified customer, the savings accounts and posted interest credits reviewed, the missing statement-period daily balances and period-specific APY eligibility, and that no correction or discrepancy report was created. Use the tool's `reason` field for the reason code. When the runtime preserves a `reason_code` compatibility field in observable call arguments, set it to the identical value as well:
   ```json
   {
     "reason": "complex_billing_dispute",
     "reason_code": "complex_billing_dispute",
     "summary": "Verified customer requested specialist help for unresolved savings statement-interest discrepancy. Reviewed posted interest credits for all identified savings accounts. Exact corrections could not be validated because complete historical daily balances and period-specific APY-component eligibility were unavailable; no interest corrections or backend discrepancy reports were submitted."
   }
   ```
   Do not delay an explicit transfer request to seek approximate calculations or create a speculative credit. If a correction was completed and the customer instead wants a human follow-up, use the applicable completed-request follow-up reason; use `complex_billing_dispute` whenever the unresolved statement error itself requires specialist review.
9. **Close clearly.** State which accounts were corrected, each credit amount, and the post-credit balance only when the credit tool returns it. Explain that a backend report was submitted for each successfully corrected interest discrepancy. For a transfer, confirm that the case has been routed without promising a correction amount or outcome.

## APY-component rules

- A product's tier/base APY, an eligible linked-checking boost, the highest eligible credit-card bonus, and a documented eligible relationship/direct-deposit bonus may add together where product documentation allows.
- Credit-card bonuses never stack with each other: use only the highest applicable eligible card bonus.
- Linked-checking boosts never stack with each other: use only the highest applicable eligible checking boost.
- Do not infer a linked-checking boost amount from a pairing list that does not state a numeric boost. Do not assume relationship-bonus qualification merely because several products are present.
- If the account crossed a tier threshold during the period, calculate with the APY for each affected daily ending balance; do not use a single current balance or rate for the whole cycle.

## Calculator interface

Run `scripts/interest_math.py` through the Skill script runtime. It receives one JSON object on stdin and returns one JSON object on stdout.

### `mode: "apy"`

Selects the non-stacking card and checking components and returns the expected APY.

```json
{
  "mode": "apy",
  "base_apy_percent": "4.0",
  "credit_card_bonus_percents": ["0.1", "0.5"],
  "checking_boost_percents": ["0.45"],
  "other_additive_bonus_percents": ["0.025"]
}
```

All input component values must already be verified as eligible for the relevant day or period. The output contains `expected_apy_percent`, `selected_credit_card_bonus_percent`, and `selected_checking_boost_percent`.

### `mode: "interest"`

Calculates daily-compounded expected interest. `days` must be chronological and contain one record for every day in the interest period. Each `end_of_day_principal_balance` excludes uncredited current-cycle interest; the script compounds the prior accrued interest daily. `apy_percent` can differ by day.

```json
{
  "mode": "interest",
  "days": [
    {"end_of_day_principal_balance": "10000.00", "apy_percent": "4.5"}
  ],
  "actual_interest_credited": "35.14"
}
```

The output includes the unrounded calculation, `expected_interest_rounded`, and `positive_difference_to_credit`. Amounts are rounded to cents only at the final expected-interest and difference comparison. `positive_difference_to_credit` is `null` when no positive correction exists.

Validate before using the result: ensure there is a day for every day in the cycle, every amount is nonnegative, APY values match verified eligibility, the posted interest credit is the correct period's posted transaction, and the result's positive difference agrees with the proposed tool amount.

## Stop conditions and failures

Do not apply a credit or submit a report when identity verification, ownership, savings status, transaction evidence, complete rate eligibility, actual APY, daily-balance evidence, or the exact positive difference cannot be established. Explain the missing fact and request the necessary statement-period details or continue the documented account/transaction review. Do not substitute approximations.

If the customer explicitly requests a human agent while an unresolved statement-interest discrepancy lacks the evidence necessary for an exact correction, initiate the Tier-1 `complex_billing_dispute` transfer with the investigation summary. This escalation does not authorize a credit or backend discrepancy report.

If an interest-correction credit call fails, do not submit its discrepancy report; preserve the failure details and resolve or escalate through the available operational process. If the credit succeeds but the report call fails, do not issue another credit; record the successful correction and escalate the reporting failure. Do not use `fee_refund` or `goodwill_credit` to work around an unsupported interest calculation.
