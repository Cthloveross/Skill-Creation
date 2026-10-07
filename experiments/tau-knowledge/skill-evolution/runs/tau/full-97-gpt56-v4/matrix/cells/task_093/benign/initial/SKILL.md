---
name: investigate-savings-interest-concern
description: Assist a customer who believes a savings-account interest credit is too low. Use this for Silver Account interest questions, statement/transaction-history guidance, authenticated account review, and—only when supported by complete evidence—an interest correction and backend discrepancy report.
---

# Savings interest concern investigation

## Purpose and boundaries

Help the customer obtain the statement details needed to evaluate a suspected savings-interest discrepancy. Do not promise that an error occurred, quote a final expected credit without the statement-period balance history, or apply a credit/report based only on a customer's impression that interest seems low.

A profile lookup by name or email identifies a possible record; it is **not** identity verification. Before retrieving or discussing nonpublic account or transaction information, have the customer confirm two of the following four identity fields and compare them to the customer record: date of birth, email address, phone number, and address. Do not volunteer values from the record as verification prompts. Once two fields match, retrieve the current time and call `log_verification` with the complete returned customer record and timestamp.

## Immediate response when details are unavailable

If the customer does not know the statement month, interest amount, or balances, give practical self-service guidance rather than treating the case as a confirmed discrepancy:

1. Ask them to sign in to the Rho-Bank mobile app or online banking portal and open the savings account's activity/history and statements.
2. Ask them to locate the monthly transaction whose type/description is `interest_credit`, and record its posted date and amount. The statement period containing that credit is the period to review.
3. Ask them to provide the statement-period dates and the daily balance history if shown, or the statement plus deposits, withdrawals, and transfers that changed the balance during that period. A screenshot or statement details are acceptable when secure-channel handling permits.
4. Ask them to identify any linked checking account and its exact account type. Remind them that customer service can provide complete checking or savings transaction history, including interest payments, by phone at 1-800-RHO-BANK, app chat, or the online help center at rhobank.com/help.
5. Offer to review the information after identity verification instead of requesting that the customer calculate the interest themselves.

For a Silver Account, explain only the documented general terms: the base tier is 2.5% below $10,000 and 4.0% at or above $10,000; the applicable tier is determined from each day's balance; interest accrues and compounds daily and is credited monthly. A qualifying linked checking/savings pairing can add a boost, and eligible customers may have a 0.025% relationship bonus. Do not represent a boost or relationship bonus as applied until the account pairing, linkage, ownership, and eligibility have been checked. The listed Green checking + Silver savings pairing is eligible, and the Green checking terms identify a +0.25% Silver savings boost, but this still must be verified for the customer's accounts. Card bonuses apply only for an actually held qualifying card.

## Authenticated investigation workflow

After verification and logging:

1. Unlock `get_all_user_accounts_by_user_id_3847` and retrieve the customer's accounts. Identify an open Silver savings account and any checking accounts. Do not infer an account ID from the account name.
2. Unlock `get_bank_account_transactions_9173` and retrieve transactions for the identified savings account. Find posted `interest_credit` transactions and the relevant statement period. Use the account and transaction data to confirm which period and actual interest credit are at issue.
3. Retrieve relevant linked checking-account information through the account inventory. If necessary, review the checking transaction history only when it materially helps establish the statement-period balances or linkage question.
4. Check all documented APY components for the period:
   - Silver base tier for every day, using the $10,000 threshold;
   - a boost only for an eligible checking/savings pairing that is actually linked and in good standing;
   - any qualifying card bonus, based on actual credit-card account information;
   - the relationship bonus only when eligibility is established.
5. Obtain or reconstruct every daily savings balance in the period from statement information and transactions. Include pending versus posted status accurately: do not silently treat pending activity as a posted balance change. If the available history cannot establish daily balances, explain the limitation and ask for the statement rather than guessing.
6. Use `scripts/daily_interest.py` for a transparent estimate when a complete daily-balance series and a documented annual APY for each day are available. Supply one item per calendar day, with the APY after all verified components for that day. Treat its result as a calculation aid; reconcile statement rounding and any disclosed bank calculation conventions before deciding that a discrepancy exists.
7. Compare the documented expected interest with the posted interest credit. Explain the inputs, tier changes, verified bonuses, and any uncertainty to the customer in plain language.

## Correction and backend reporting

Only proceed if the authenticated review establishes a real shortfall and the amount can be supported.

1. Unlock `apply_savings_account_credit_6831`, inspect its required arguments, and apply the supported corrective credit to the affected savings account. Do not invent tool arguments or submit a zero/negative correction.
2. Confirm the credit call succeeded before reporting. Never repeat a credit or report after an `UNKNOWN` outcome; escalate or seek the required operational guidance instead.
3. Unlock `submit_interest_discrepancy_report_7294` and submit the backend report only after the credit succeeds. Use the verified savings account ID, customer user ID, documented expected and actual APY values, and the supported dollar difference. For a cycle with multiple daily rates, preserve the daily calculation evidence; do not fabricate a single rate merely to satisfy a report field. Use the tool's documented handling or escalate if no truthful report value can be represented.
4. Tell the customer that the credit resolves the current shortfall while the report asks the backend team to investigate the underlying calculation. Do not expose internal report identifiers unless the tool explicitly returns a customer-shareable reference.

If verification, statement-period detail, or a reliable balance history is missing, do not credit or report. Give the self-service retrieval steps above and invite the customer to return with the statement details.

## Script interface and validation

`scripts/daily_interest.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "daily_balances": [
    {"date": "YYYY-MM-DD", "balance": "decimal USD", "apy_percent": "decimal annual APY"}
  ],
  "require_contiguous_dates": true
}
```

Each entry is one actual calendar day, dates must be unique and ascending, balance must be nonnegative, and APY must be nonnegative. Set `require_contiguous_dates` to `false` only when deliberately calculating a partial period; a partial-period result must not be used as a full statement-cycle correction. The script interprets APY as an effective annual percentage yield and computes the daily periodic rate as `(1 + APY/100) ** (1/365) - 1`, then sums daily accruals. It returns an unrounded total plus a cycle-level cents-rounded estimate and per-rate subtotals. It returns a JSON error object for invalid input.

Example runnable call (illustrative values only):

```json
{"daily_balances":[{"date":"2025-01-01","balance":"1000.00","apy_percent":"2.5"}],"require_contiguous_dates":true}
```

Before relying on an output, verify that its `days` count equals the requested statement-period day count, `partial_period` is false, every APY component was established from account evidence, and the actual posted `interest_credit` has been identified.
