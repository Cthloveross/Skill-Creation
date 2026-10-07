---
name: savings-interest-discrepancy-reconciliation
description: Explain documented savings APY rules and safely investigate suspected monthly interest discrepancies for Silver, Silver Plus, Platinum, and Diamond Elite accounts. Use when a customer asks why an interest credit is lower than expected or requests an interest correction.
---

# Savings Interest Discrepancy Reconciliation

Explain documented rules without guessing, retrieve the posted interest for each implicated savings account after identity verification, and correct interest only when the applicable rate, full daily-balance calculation, and shortfall are established.

## Core APY policy

Use `references/rate_rules.md` for product-specific rates and bonuses.

- Select only the **highest** applicable bonus among eligible active same-profile credit cards. Card bonuses **do not stack** with one another.
- Select only the **highest** applicable boost among qualifying checking pairings. Checking boosts **do not stack** with one another.
- The selected card bonus and selected checking boost may stack with the base/tier APY and a separately verified relationship bonus.
- Interest accrues and compounds **daily** and is credited **monthly**.
- For tiered products, determine the base tier from each day's ending balance, not from an approximate current balance.

Ownership of checking and savings accounts under one customer does not by itself establish the required checking-to-savings pairing or its eligibility. Do not represent a checking boost as applied or definite unless the specific link, exact qualifying pairing, same-profile requirement, open/good-standing requirement, and other product conditions are evidenced.

For Light Green checking, verify its continuing age eligibility (ages 13 through 24) before including its boost in an expected APY. If verified date-of-birth and current-date information show an age outside that range, its stated percentages may be explained as product rules but must not be treated as currently available.

## Required customer-facing explanation

When a customer requests rate rules before reconciliation evidence is complete, provide the following complete explanation. Do not omit lower tiers merely because the customer remembers a balance above a threshold.

1. **Base rates and timing**
   - **Silver:** 2.5% APY on each day below **$10,000**; 4.0% on each day at or above **$10,000**.
   - **Silver Plus:** 3.0% APY on each day below **$15,000**; 4.5% on each day at or above **$15,000**. Verified active direct deposit adds 0.25% for an eligible active period.
   - **Platinum:** 6.5% APY.
   - **Diamond Elite:** 7.5% APY.
   - Each product compounds daily and credits accumulated interest monthly. An approximate balance multiplied by an APY and divided by 12 is not a reliable reconciliation.

2. **Credit-card bonuses**
   - State that only the highest applicable active same-profile card bonus is used; multiple card bonuses do not stack.
   - For the documented card schedule, EcoCard is the highest listed Silver bonus at 2.2%; Diamond Elite Card is the highest listed Platinum bonus at 0.35%; Diamond Elite Card is the highest listed Diamond Elite bonus at 0.5%; and EcoCard is the highest listed Silver Plus bonus at 0.45%.
   - Apply those results only when the relevant card is active and eligibility under the same profile is established. Do not infer an active card from a customer statement; retrieve card records after identity verification when needed.

3. **Checking-pairing alternatives**
   - Silver may receive Bluest checking +0.45%.
   - Silver Plus may receive Blue checking +0.35%.
   - Platinum may receive Blue checking +0.8% or Light Green checking +0.65%.
   - Diamond Elite may receive Light Green checking +0.2% or Evergreen checking +0.15%.
   - Make every one of these checking components conditional until the exact link and eligibility are evidenced. If more than one eligible checking option exists, use only the highest eligible boost, not their sum. Light Green is additionally subject to its ongoing age requirement.

4. **Other conditional components**
   - Silver and Silver Plus may have a 0.025% relationship bonus when the relationship criteria are verified.
   - Silver Plus's 0.25% direct-deposit addition requires verified active direct deposit for the applicable period.

Explain that a lower monthly credit can result from daily balance changes, days in a lower tier, statement length, unverified or ineligible rate components, or another documented component. Explicitly say: **“I cannot conclude that an error occurred and cannot safely calculate a discrepancy from approximate balances alone.”**

## Identity and private-account investigation

Do not retrieve or disclose private account data before identity and ownership are verified.

1. Obtain at least two matching identity fields from email, date of birth, phone number, and address. Name is useful for locating a record but does not count as one of the two fields.
2. Compare the supplied fields to an authoritative user record. If only one field was supplied, request another field; do not treat information returned by a lookup as customer-provided confirmation.
3. Obtain the current time and call `log_verification` only after the two fields match.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Identify every implicated savings account and its status.
5. Unlock and call `get_bank_account_transactions_9173` for **every** implicated savings account. Locate each posted `interest_credit` and report its exact date and amount.
6. Retrieve card records when needed to identify active same-profile credit-card candidates. Obtain authoritative evidence of the statement start/end dates, daily ending balances (or all balance-changing activity), checking pairings, good standing, Silver Plus direct-deposit status, and relationship eligibility.

The account-list response can establish ownership, account identifiers, present balances, and statuses. It does not establish historical daily balances, statement boundaries, direct-deposit status, relationship eligibility, or a checking-to-savings link.

## Incomplete-evidence handling

Keep confirmed facts separate from conditional product rules. For example, a retrieved posted interest credit is a confirmed fact, while a checking boost remains conditional without pairing evidence.

If statement dates, full daily balance history, or relevant eligibility evidence is missing:

- do not calculate a correction or declare an error;
- do not call `apply_savings_account_credit_6831`;
- do not call `submit_interest_discrepancy_report_7294`;
- request statement start/end dates, daily balances or complete transaction activity, exact interest-credit records, and pairing/eligibility evidence.

A statement PDF or screenshots may provide the missing period, balance, and transaction evidence. Do not claim that a specific private lookup is unavailable unless its actual tool result shows that limitation.

## Calculation helper

After complete evidence is available, run `scripts/reconcile_interest.py`. The script reads one JSON object from stdin and emits one JSON object on stdout. It performs no bank action.

Example input:

```json
{
  "credit_cards": [{"card_type": "EcoCard", "account_status": "ACTIVE"}],
  "savings_accounts": [{
    "account_id": "savings-account-id",
    "account_type": "Silver",
    "status": "ACTIVE",
    "daily_principal_balances": [10000.00, 10100.00],
    "actual_interest_credit": 5.00,
    "linked_checking": [{
      "account_type": "Bluest",
      "status": "ACTIVE",
      "linked": true,
      "link_verified": true,
      "qualification_verified": true
    }],
    "relationship_bonus_verified": false
  }]
}
```

Input schema and validation:

- `savings_accounts` must be a nonempty list. Each entry requires `account_type` and `status`; retain `account_id` for a possible later correction.
- `daily_principal_balances` must be a nonempty ordered list of nonnegative finite daily ending principal balances covering the complete statement period.
- `actual_interest_credit` must be the exact posted credit before the script can calculate a dollar difference.
- `statement_day_count`, when supplied, must equal the number of daily balances.
- Only cards marked `ACTIVE` in either `status` or `account_status` are candidates.
- A checking entry is used only when it is active and has `linked: true`, `link_verified: true`, and `qualification_verified: true`. Qualification includes the exact pairing, same-profile, open/good-standing, and product-specific requirements.
- For a Light Green candidate, also provide `light_green_age_eligible: true`; otherwise the script excludes its boost.
- `direct_deposit_active` applies only to Silver Plus.
- Set `relationship_bonus_verified` only after verifying the relationship criteria. Provide `relationship_bonus_percent` only when supported by current documentation.

The script returns per-account statuses `reconciled`, `calculation_ready`, `insufficient_daily_balance_data`, or `unsupported_account_type`. Review warnings, unrecognized active cards, and the daily-balance count before relying on a result. It rounds only final interest and final difference to cents.

## Correcting a confirmed shortfall

Proceed only when identity and ownership are verified; the account is confirmed to be savings; the entire statement period, daily balances, eligibility, and actual interest credit are evidenced; and expected interest exceeds the posted credit by more than $0.00.

1. Unlock and call `apply_savings_account_credit_6831` with the positive difference and `credit_type: "interest_correction"`.
2. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with verified account and user IDs, reliably established expected and actual APYs, and the positive difference.
3. Inform the customer that the credit was applied and the backend report was submitted.

Never reverse the order. Do not credit or report a zero/negative difference, an unverified customer, incomplete evidence, a suspected discrepancy, or an unsupported account. If daily rates varied and no defensible single actual APY can be reported, do not invent one; follow the normal internal escalation path.
