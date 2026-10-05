---
name: silver-interest-discrepancy-review
description: Investigate a verified customer's suspected Silver savings-account interest underpayment, calculate documented APY components and daily accruals, and, when all prerequisites are established, apply an interest-correction credit before filing the required backend discrepancy report.
---

# Silver savings interest discrepancy review

Use this skill when a customer reports that a monthly Silver Account interest credit seems incorrect. It supports a review and a correction workflow; it must not be used to guess an APY, debit an account, or issue a goodwill credit in place of a documented interest correction.

## Required evidence and controls

Before any account lookup beyond candidate identification, credit, or report:

1. Verify the claimant's identity by matching two of date of birth, email, phone number, and address against the customer record. Do not reveal profile values while asking for them.
2. Log the completed verification with `log_verification`, using a current timestamp from `get_current_time`.
3. Confirm the Silver savings account is owned by the verified customer, is a savings account, and is active/in good standing as required for the benefit under review.
4. Before a monetary action, confirm the exact account, product eligibility, linked-product eligibility, posted interest transaction, statement-cycle dates, calculation inputs, correction amount, and all report fields. Follow any confirmation requirement exposed by the banking tools or applicable operating policy.

A name, an account-type assertion, a prior read-only lookup, or a candidate user ID is not identity verification. Treat prior observations as leads only and re-check their applicability after verification.

## Banking workflow

### 1. Identify and verify the customer

Use a customer-provided identifier to find a candidate customer record. If more than one record matches, ask for a distinguishing identifier rather than choosing one. Ask the claimant to provide two identity fields, compare them to the record, then obtain the current time and call `log_verification` with all required record fields.

If verification fails or cannot be completed, do not retrieve account history, apply a credit, or submit a report.

### 2. Retrieve and confirm relevant products

After verification, unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Identify the active Silver savings account from returned account type/class information, not solely from the customer's description.

Also retrieve the customer's card accounts with `get_credit_card_accounts_by_user`. Review all active checking accounts and active card accounts that are actually linked/eligible under the same profile. Do not treat an account as linked merely because it has a similar name.

For the Silver Account, use these documented APY rules:

- The base APY is **2.5%** on each day whose ending balance is below $10,000 and **4.0%** on each day whose ending balance is at least $10,000.
- A Green checking account paired with a Silver savings account supplies a **+0.25%** checking boost when the pairing is eligible.
- Checking boosts do not stack: use only the highest eligible, documented checking boost.
- The highest eligible card bonus applies; card bonuses do not stack. Known Silver card bonuses are Bronze Rewards +0%, Silver Rewards +0.1%, Gold Rewards +0.5%, EcoCard +2.2%, Green Rewards +0%, Crypto-Cash Back +0.5%, Platinum Rewards +0.2%, and Diamond Elite +0.25%.
- A **+0.025%** relationship bonus may be added only when eligibility is established. A linked Platinum Rewards Card and Silver Account under the same profile is a documented qualifying arrangement.
- The selected checking boost, selected card bonus, and established relationship bonus can stack with the daily tier APY.

The qualifying-pairing list alone does not supply every pairing's numerical boost. If an account has a potentially qualifying pairing whose exact boost is not documented in available authoritative product material, do not assume a value or silently omit it; obtain the product terms or stop the automated calculation.

### 3. Establish the interest-credit cycle and actual result

Unlock and call `get_bank_account_transactions_9173` for the confirmed savings account. Transactions are reverse chronological, and positive posted `interest_credit` records are the relevant credits.

Identify the interest credit being reviewed and establish its complete statement-cycle boundaries. Reconstruct or otherwise obtain every cycle-day ending balance and exclude pending transactions unless the authoritative balance source says otherwise. A current balance and a single interest-credit amount alone are insufficient to reconstruct an exact historical daily-balance calculation.

Record:

- target posted interest-credit transaction ID, date, and amount;
- the immediately relevant cycle start and end dates;
- every daily ending balance in that cycle;
- the actual APY applied, if an authoritative system record provides it; and
- evidence for each expected APY component.

The transaction-history schema does not itself guarantee an applied APY. Do not label an inferred rate as the actual rate for the discrepancy-report field unless the institution's approved review process permits that derivation.

### 4. Calculate and validate

Use `scripts/calculate_silver_interest.py` after preparing verified daily balances and documented bonus inputs. The script selects daily tiers, applies only the highest supplied checking and card bonuses, calculates expected accrual, and produces a cent-rounded underpayment candidate.

Run it with a real JSON review file:

```sh
python3 scripts/calculate_silver_interest.py < review-input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Its schema is documented in the script and summarized below:

- `daily_balances`: required chronological, contiguous objects with `date` (`YYYY-MM-DD`) and nonnegative `balance`.
- `checking_bonuses`: optional array of already verified eligible checking boost percentages. Supply only documented boosts; the script takes the maximum.
- `active_card_types`: optional array of already verified active eligible card product names. The script selects the highest documented bonus.
- `relationship_eligible`: required boolean supported by product/linkage evidence.
- `daily_rate_method`: required, either `effective_apy` or `apy_divided_by_day_count`, selected only after confirming the institution's applicable daily-periodic-rate convention.
- `day_count`: optional positive integer, default 365, only when supported by the applicable convention.
- `actual_interest`: optional posted interest-credit amount.
- `actual_apy`: optional authoritative APY actually applied.

The output is valid for correction consideration only when it has no `errors`, contains a positive `credit_amount`, and all calculation assumptions match the account's authoritative cycle and rate convention. `report_expected_apy` is populated only if the expected APY was constant throughout the cycle; the report tool accepts one APY number, so a variable-rate cycle requires an approved report convention before filing.

Do not invent daily rounding, statement-cycle boundaries, an APY-to-daily-rate conversion, the actual applied APY, or relationship eligibility. The script intentionally requires the daily-rate method because the supplied product terms state that a daily periodic rate is calculated from APY but do not define the conversion formula.

### 5. Correct and report, in the required order

Proceed only when all required report inputs are known: account ID, user ID, constant/reportable expected APY, authoritative actual APY, and exact positive underpayment amount.

1. Unlock `apply_savings_account_credit_6831` and apply the exact positive cent amount to the confirmed Silver savings account with `credit_type` set to `interest_correction`.
2. Confirm the credit tool succeeded. Do not claim a new balance unless the tool returned one.
3. Unlock `submit_interest_discrepancy_report_7294` and submit the report with the same account and user IDs, the validated expected and actual APYs, and the dollar difference.
4. Tell the customer that the correction was applied and that the underlying calculation was reported for investigation.

The credit must be applied **before** the discrepancy report. Never submit the report first and never use a report recommendation as a substitute for the actual banking action.

## Stop conditions and unsupported cases

- **No discrepancy:** Explain the reviewed interest result and do not credit or report.
- **Expected amount is lower than posted amount:** Do not use the positive-only credit tool to reverse or offset the payment. This skill does not authorize debits or reversals; seek the appropriate internal handling.
- **Expected APY or actual APY unavailable, variable cycle with no approved one-number convention, missing daily balances, unknown boost amount, or unknown linkage/relationship eligibility:** do not guess and do not start a correction/report sequence. Obtain the missing authoritative information.
- **No posted interest credit or no determinable completed cycle:** ask which credit/cycle the customer wants reviewed or wait for the posting.
- **Account is not an eligible active Silver savings account, ownership is not established, or identity is unverified:** do not proceed with account action.
- **Credit tool failure:** do not file the report as though the credit had been applied. Preserve the failure details and use the institution's supported escalation path.

## Script-output validation

Before passing an amount to a banking tool, verify all of the following in script output:

- `errors` is empty;
- `days` equals the complete number of cycle days;
- daily dates are contiguous and correspond to the identified cycle;
- component fields match the account/product evidence;
- `expected_interest_rounded`, `actual_interest`, and `difference_rounded` were reviewed;
- `credit_amount` is a positive, two-decimal currency value; and
- both report APY fields are available and authorized for the report's one-number fields.

The helper is calculation-only. It never performs banking actions; the execution agent must make verified tool calls in the sequence above.
