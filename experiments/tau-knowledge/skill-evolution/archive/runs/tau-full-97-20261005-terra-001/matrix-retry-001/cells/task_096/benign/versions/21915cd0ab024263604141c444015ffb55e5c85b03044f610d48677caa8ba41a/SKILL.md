---
name: savings-interest-discrepancy-investigation
description: Investigate a suspected incorrect monthly interest credit on a Bronze or Gold Plus savings account, determine documented APY components, calculate an evidence-supported correction, and complete the required correction-credit and backend-report workflow.
---

# Savings interest discrepancy investigation

Use this Skill when a customer says a savings interest credit appears wrong. It covers Bronze and Gold Plus savings products using the supplied product documentation. It does **not** authorize estimates, debits, or a correction when the statement period, target interest credit, or balance history cannot be established.

## Required controls

1. Verify the customer owns the account before discussing nonpublic account data or taking action. Confirm two of the four identity fields (date of birth, email, phone, address) from the customer against the customer record, get the current time, and call `log_verification`. A name alone is not one of the two required fields. Values the customer has already explicitly supplied in the active conversation may count if they match.
2. Use only active accounts under that verified user profile. A checking boost or card bonus applies only when the associated account is active and belongs to the same profile.
3. Do not infer an interest period from approximate balances or from a customer’s recollection. Inspect posted `interest_credit` transactions and establish the relevant crediting period and daily balance record.
4. Do not apply a savings credit unless the account is a savings account, the expected interest and posted interest have been calculated from evidence, and the positive correction amount is exact to cents.
5. Apply a warranted interest-correction credit **before** filing the discrepancy report. Never use this workflow to debit an apparent overpayment.

## Investigation workflow

### 1. Identify and verify

* Resolve a user identifier using the supplied customer identifier and an appropriate user lookup tool.
* Confirm two identity fields with the customer, then call `get_current_time` and `log_verification` with the complete retrieved record and timestamp.
* Unlock `get_all_user_accounts_by_user_id_3847`, then call it for the verified user. Identify active Bronze and/or Gold Plus savings accounts and all active checking accounts.
* Unlock `get_bank_account_transactions_9173` and retrieve transactions for **each** investigated savings account. Locate posted transactions whose type is `interest_credit`. Record the target transaction ID, posting date, amount, and any statement-period information in its description. Do not treat an unlabeled amount as interest.

### 2. Establish APY components

Use the highest bonus within each category; categories add together.

| Savings product | Base APY | Documented checking boosts | Documented card bonuses |
|---|---:|---|---|
| Bronze Account | 2.00% | Bluest Account: 0.70%; Green Fee-Free Account: 0.40% | Bronze Rewards: 0.10%; Silver Rewards: 0.00%; Gold Rewards: 0.25%; EcoCard: 0.00%; Green Rewards: 0.20%; Crypto-Cash Back: 0.30%; Platinum Rewards: 0.55%; Diamond Elite: 0.15% |
| Gold Plus Account | 6.00% | Gold Years Account: 0.50%; Green Fee-Free Account: 0.35% | Bronze Rewards: 0.15%; Silver Rewards: 0.10%; Gold Rewards: 0.35%; Platinum Rewards: 0.20%; Diamond Elite: 0.25%; EcoCard: 0.10%; Green Rewards: 0.05%; Crypto-Cash Back: 0.30% |

Only qualifying checking/savings pairings receive a checking boost. The documented qualifying-pairing list includes Bluest–Bronze, Green Fee-Free–Bronze, Gold Years–Gold Plus, and Green Fee-Free–Gold Plus. Check the pairing documentation before using any other checking account. If a pairing is qualifying but its rate is not available in the supplied documentation, stop and obtain the applicable product documentation rather than calculating an incomplete expected APY.

For a supported product, compute:

`expected APY = base APY + highest qualifying checking boost + highest applicable active-card bonus`

Credit-card bonuses do not stack with one another. Checking boosts do not stack with one another. The selected checking boost and selected card bonus do stack with the base rate and with each other.

### 3. Obtain an exact balance basis

Interest compounds daily and is credited monthly. Obtain daily eligible end-of-day principal balances for every day in the target crediting period. They may be obtained from a reliable statement/balance history, or reconstructed from a complete ledger only if the opening balance, exact period bounds, transaction dates, and transaction posting convention are known.

Use `scripts/calculate_interest_discrepancy.py` to select supported bonuses and calculate the expected compounded interest, an equivalent actual APY from the posted interest, and a cents-rounded correction.

The script accepts JSON from stdin and returns JSON on stdout. Run it as:

`python3 scripts/calculate_interest_discrepancy.py < investigation.json`

Input schema:

* `savings_type` (string): `Bronze Account` or `Gold Plus Account`.
* `checking_accounts` (array): each object has `account_type` and optional `status`; only `ACTIVE` is used.
* `credit_cards` (array): each object has `card_type` and optional `status`; only `ACTIVE` is used.
* `daily_balances` (array of positive or zero numbers): one eligible principal balance per calendar day, in chronological order. Do not include the target monthly interest credit in these balances.
* `actual_interest_credit` (number): amount of the identified posted target `interest_credit`.
* Optional `qualifying_checkings_without_documented_rate` (array of strings): qualifying checking types whose rate is not in the supplied evidence. If nonempty, the script deliberately returns an incomplete result.

The script validates required fields and refuses a calculation with no daily balances, unsupported product, unsupported qualifying rate, or a negative posted interest credit. Its calculation models daily compounding with an APY-derived daily rate and period-end rounding. Treat a result as review-ready only when the period and each balance are evidence-supported.

### 4. Correct and report only when warranted

If the script returns `status: "ready_for_review"`, independently confirm that its target posted credit and balance schedule correspond to the account and period. If `correction_amount` is greater than zero:

1. Unlock and call `apply_savings_account_credit_6831` with the savings `account_id`, the positive `correction_amount`, and `credit_type: "interest_correction"`.
2. After the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with that savings account ID, the verified user ID, `expected_apy_percent`, `actual_apy_percent`, and `correction_amount` as `amount_difference`.
3. Tell the customer the reviewed period, the relevant APY components, the correction credit, and that the underlying calculation was reported for investigation.

If the correction is zero, explain that the reviewed interest matches the evidence-supported calculation; do not credit or report a missing-interest discrepancy. If the correction is negative, do not debit the savings account. Preserve the evidence and seek backend review if a system discrepancy still needs investigation.

If the script returns `insufficient_evidence`, do not apply a credit or submit a numeric discrepancy report. Explain that posted transaction and exact daily-balance/period data are required to calculate a correction, then obtain those records or ask the customer for the statement.

## Customer explanation for multiple qualifying relationships

After reviewing accounts and transactions, give an account-by-account explanation. State the actual posted interest-credit amount and date if available. Do not claim that the selected APY was actually applied unless the statement or system record establishes that fact.

Where the customer has the documented active relationships represented in this Skill, clearly explain the selection separately for each account. Use these complete statements (with the selected products adjusted only when the retrieved active accounts differ):

* **Bronze Savings:** “Bronze Savings: the base is 2.00%. Bluest checking qualifies for the 0.70% checking boost, and only the highest checking boost applies. Platinum Rewards provides the highest Bronze card bonus at 0.55%; other card bonuses do not add on top. That produces an expected 3.25% APY if all relationships were applied for the reviewed period.”
* **Gold Plus Savings:** “Gold Plus Savings: the base is 6.00%. Gold Years checking qualifies for the 0.50% boost, and only the highest checking boost applies. Gold Rewards Card provides the highest Gold Plus card bonus at 0.35%; other card bonuses do not add on top. That produces an expected 6.85% APY if all relationships were applied for the reviewed period.”

The two “only the highest checking boost applies” statements are deliberately account-specific: do not collapse them into a single general statement when explaining both accounts. Explain that the highest checking boost and highest card bonus may add to each other and the base APY, but boosts within either category do not stack.

### Insufficient-evidence response

When the customer lacks exact period dates, a complete daily balance record, and the statement APY, explicitly say that the issue cannot be settled from approximate balances and isolated interest credits. Include this meaning directly in the final response:

> “Without the statement-period boundaries and a complete daily balance ledger, I cannot confirm whether the credited amounts reflect all eligible benefits or apply a correction. I cannot issue a credit based only on approximate balances or an estimated monthly amount.”

Ask the customer to provide the statement or official daily-balance history for the identified period. Once available, calculate the daily-compounded expected interest, compare it with the posted interest credit, and only then determine whether an exact positive correction is due.

## Output validation checklist

Before an action, verify all of the following:

* Verification was logged after two customer-confirmed identity fields.
* Savings account, checking accounts, and cards were retrieved for the same user and active status was checked.
* The transaction is posted and typed `interest_credit`.
* The highest supported checking boost and highest supported card bonus, rather than sums within either category, were used.
* Daily balance count equals the exact number of days in the identified crediting period.
* The planned credit equals the positive cents-rounded expected-minus-posted interest result.
* The savings credit completed before the backend report is submitted.
* If evidence is insufficient, no credit or report was submitted and the final response identifies the missing period boundaries and complete daily balance ledger.
