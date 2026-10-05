---
name: savings-interest-discrepancy
version: 1.0.0
description: Investigate a claimed savings-interest underpayment, calculate the documented APY and exact cycle difference, then—only after required verification—apply an interest-correction credit before filing the required backend discrepancy report. Use for savings APY, rate-tier, linked-checking, card-bonus, or relationship-bonus disputes.
---

# Savings Interest Discrepancy Investigation

Use this workflow when a customer claims that interest on a savings account was calculated incorrectly. It supports calculation only from verified account data, posted transaction data, applicable product documentation, and a complete interest-cycle balance record. It must not be used to estimate a credit from a current or approximate balance.

## Safety and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow specifically:

1. Verify identity by matching **two of four** customer-provided fields (date of birth, email, phone number, address) to the profile. A name or a previously retrieved profile by itself is not identity verification.
2. After two fields match, obtain the current timestamp and call `log_verification` with the complete profile fields and timestamp.
3. Treat a user ID, an approximate balance, a claimed rate, or an account name as insufficient proof of account ownership. Retrieve the user’s bank accounts and confirm that the selected active savings account belongs to the verified user.
4. Do not disclose full account numbers, profile data, or unverified account details in customer-facing text.
5. Do not make a credit, file a report, or claim an exact shortfall until the relevant posted interest credit, exact cycle balance data, actual applied APY, and documented eligibility during the cycle are available.

If the customer cannot supply two verification fields, request them. If cycle data is unavailable after account and transaction review, explain that an exact correction cannot yet be calculated and request the statement period and daily balance history (or the institution’s equivalent authoritative balance record). Do not substitute a current balance or divide annual APY by 12.

## Required runtime tools

The following named tools are discoverable agent tools. Unlock each tool before calling it:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831`
- `submit_interest_discrepancy_report_7294`

Use `call_discoverable_agent_tool` after unlock. The account lookup requires `user_id`; transaction lookup requires the selected `account_id`. The credit and report tools are write actions and must only be called at the final steps below.

## Investigation procedure

### 1. Establish identity, authority, and account ownership

1. Locate the customer profile using information the customer provided.
2. Ask for, and compare, two identity fields against the profile. Do not prompt the customer to repeat fields that were not actually supplied.
3. Call `get_current_time`, then `log_verification` only after successful two-field verification.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user.
5. Select exactly one active savings account matching the product in question. Confirm its account type/class, status, and ownership from the returned account record.
6. If no matching account is returned, the account is inactive, ownership cannot be established, or more than one candidate remains, stop and obtain clarification. Never choose an account merely because its balance seems similar to the customer’s recollection.

### 2. Review the actual interest payment and cycle data

1. Unlock and call `get_bank_account_transactions_9173` using the verified savings `account_id`.
2. Identify the relevant transaction with `type: interest_credit` and `status: posted`. Record its amount and posting date.
3. Obtain the statement start/end date, actual APY applied (or an authoritative source for it), and complete daily balances for that same interest cycle. The documented transaction response does not itself provide a daily-balance ledger or applied APY.
4. Ensure all eligibility facts were true during the affected cycle, not just today: savings product/tier, qualifying checking account(s), card status, and relationship-bonus conditions.
5. If the balance history, cycle boundary, posting, or actual APY is unknown, do not infer it from one interest payment. Request authoritative statement details or use an available approved balance-history source if one is supplied by the runtime.

### 3. Determine the documented expected APY

Read the applicable savings, checking, card, tier, and relationship documentation. Build the APY only from documented, cycle-applicable components.

For a Gold savings investigation, the supplied documentation establishes these rules:

- Gold Savings has a 5.5% documented base APY and compounds daily with monthly interest crediting.
- A qualifying Green checking and Gold savings pairing is eligible for the documented Green-to-Gold boost; use the documented boost value rather than a customer-stated value.
- When multiple qualifying checking accounts exist, use only the single highest applicable checking boost.
- Card APY bonuses do not stack with one another; use only the highest eligible bonus among active cards under the same customer profile.
- The selected card bonus can stack with a qualifying checking boost and a documented relationship bonus.
- A documented Gold Rewards relationship bonus is additive if its conditions were met. Do not rely on the documentation’s internally inconsistent illustrative total; add the stated components arithmetically.

For other products, do not extrapolate Gold-specific values. Find product documentation that identifies the base rate, tier rule, eligible pairing, boost amount, card-policy treatment, relationship treatment, and timing. If any component is undocumented or eligibility is uncertain, omit it only when documentation clearly says it does not apply; otherwise stop for clarification rather than guessing.

Use `scripts/interest_math.py` to select the highest non-stacking checking and card components and to calculate a reproducible cycle amount. The caller supplies only components that have already been verified as applicable.

### 4. Calculate and validate the discrepancy

Construct a JSON input for the helper from verified facts. `daily_balances` must contain one authoritative balance for every accrual day in the statement cycle, in chronological order. The helper treats APY as an effective annual percentage and uses a daily rate of `(1 + APY / 100)^(1 / days_per_year) - 1`, compounding unrounded accrued interest daily and rounding the total once at cycle end.

Before relying on its result, confirm that this convention, the day-count convention (365 or 366), balance timing, and rounding convention match the account’s authoritative calculation rules. If they do not, use the documented account calculation method instead. Reconcile the `actual_interest` input to the posted `interest_credit` transaction.

The helper emits:

- `expected_apy`: documented APY selected from approved components;
- `expected_interest`: calculated interest for the complete cycle;
- `amount_difference`: expected interest minus the posted interest, rounded to cents;
- `report_ready`: true only when a positive difference and the actual applied APY were supplied.

A zero difference means no interest correction or discrepancy report is warranted. A negative difference indicates an apparent over-credit or another unsupported condition; do not use an interest-correction credit to reverse it and do not bypass the credit-first rule. Escalate through the institution’s approved exception process if investigation is still needed.

### 5. Perform write actions in mandatory order

Only when all prerequisites are satisfied, the computed difference is positive, and any applicable confirmation requirement has been met:

1. Unlock and call `apply_savings_account_credit_6831` with the verified savings `account_id`, the exact positive cent amount, and `credit_type: "interest_correction"`.
2. Confirm the credit succeeded. If it fails or is not confirmed, do **not** submit the discrepancy report.
3. Unlock and call `submit_interest_discrepancy_report_7294` only after the credit succeeded, with:
   - `account_id`: verified savings account ID
   - `user_id`: verified customer ID
   - `expected_apy`: documented expected APY from the calculation
   - `actual_apy`: authoritative APY actually applied for the affected cycle
   - `amount_difference`: the exact positive credited difference
4. Record/report the tool outcomes according to the runtime’s normal audit process, then inform the customer that the correction was applied and that the backend investigation was submitted. Do not promise an investigation outcome or a new balance unless returned by a tool.

The ordering is strict: **credit first, report second**. The report investigates the underlying system issue; it is not a substitute for the customer correction.

## Helper interface

Run the helper with JSON on standard input and consume its JSON standard output:

```text
python3 scripts/interest_math.py < calculation_input.json
```

Input schema:

```json
{
  "base_apy": "number",
  "checking_boosts": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "card_bonuses": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "additive_components": [{"name": "string", "apy": "number", "applicable": "boolean"}],
  "period": {
    "daily_balances": ["number"],
    "actual_interest": "number",
    "actual_apy": "number",
    "days_per_year": "optional integer, 365 or 366"
  }
}
```

`checking_boosts` and `card_bonuses` are each reduced to their single highest applicable value. `additive_components` is for individually documented components that may stack, such as an approved relationship or tier component; do not place alternatives in this list. Omit `period` to calculate only expected APY. The output has `ok: false` and an `errors` list when supplied facts are incomplete or invalid; this is a stop condition, not permission to estimate missing facts.
