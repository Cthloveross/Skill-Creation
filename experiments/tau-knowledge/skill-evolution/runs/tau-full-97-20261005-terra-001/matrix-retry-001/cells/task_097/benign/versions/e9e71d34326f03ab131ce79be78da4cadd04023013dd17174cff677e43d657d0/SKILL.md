---
name: savings-interest-discrepancy-reconciliation
description: Explain documented savings APY rules and safely investigate suspected monthly interest discrepancies for Silver, Silver Plus, Platinum, and Diamond Elite accounts. Use when a customer asks why an interest credit is lower than expected or requests an interest correction.
---

# Savings Interest Discrepancy Reconciliation

Explain the documented rules without guessing. Correct interest only after the applicable rate, daily-balance calculation, and shortfall are established.

## Core policy

Use `references/rate_rules.md` for the product rules. For every covered product:

- Only the **highest** applicable bonus among eligible active credit cards applies; card bonuses **do not stack** with one another.
- Only the **highest** applicable boost among qualifying linked checking accounts applies; checking boosts **do not stack** with one another.
- The selected card bonus and checking boost can stack with the base/tier APY and a separately verified relationship bonus.
- Interest accrues and compounds **daily** and is credited **monthly**.
- For tiered products, evaluate the base tier from each day's ending balance.

An account list showing a customer owns both checking and savings accounts is not proof that either is linked to the other. Until the specific link, required pairing, open/good-standing status, and other eligibility are evidenced, describe a checking boost only as conditional. Never call it “confirmed linked,” “applied,” or otherwise definite based only on shared ownership, account type, or active status.

For Light Green, additionally verify ongoing age eligibility (13–24) before including its boost in an expected APY. If verified date-of-birth and current-date evidence places the holder outside that range, describe its percentages only as documented product rules, not as benefits currently available to the customer.

## Required customer-facing rate explanation

When the customer asks for applicable rules but historical evidence is incomplete, provide this complete explanation before requesting further records. Do not omit the lower tiers merely because the customer reported an approximate balance above the threshold.

- **Silver:** 2.5% APY for each day the ending balance is below **$10,000**, and 4.0% for each day it is at or above **$10,000**.
- **Silver Plus:** 3.0% APY for each day below **$15,000**, and 4.5% for each day at or above **$15,000**. A 0.25% direct-deposit addition requires verified active direct deposit.
- **Platinum:** 6.5% APY.
- **Diamond Elite:** 7.5% APY.
- All four accrue/compound daily and pay the accumulated interest monthly. Therefore an approximate current balance divided by 12 is not a reliable reconciliation of a statement-period credit.
- The documented examples of possible card and checking components include Silver’s 2.2% EcoCard card bonus and 0.45% Bluest-to-Silver checking boost; Silver Plus’s 0.45% EcoCard card bonus and 0.35% Blue-to-Silver Plus checking boost; Platinum’s highest listed card bonus of 0.35% for Diamond Elite Card; and Diamond Elite’s 0.5% Diamond Elite Card bonus. Apply only the highest applicable card bonus and the highest applicable checking boost: bonuses within each category do not stack.
- State all checking, direct-deposit, and relationship components as “if verified eligible” until evidence is obtained. State the 0.025% Silver and Silver Plus relationship bonuses only as conditional unless the criteria are verified.

Explain that a lower posted amount may result from daily balance changes, days below a tier threshold, statement length, missing/unverified eligibility, or other rate components—not necessarily an error. Clearly say that you **cannot conclude that an error occurred** and **cannot safely calculate a discrepancy** from approximate balances alone.

## Identity and private-account investigation

Do not disclose private account details or retrieve private bank data until identity and ownership are verified.

1. Obtain at least two of email, date of birth, phone number, and address, and compare them with an authoritative user record. Name is helpful but does not count as one of the two fields.
2. Obtain the current time and call `log_verification` only after the two fields match.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Identify every implicated savings account and its status.
4. Unlock and call `get_bank_account_transactions_9173` for **every** implicated savings account. Find the posted `interest_credit`; report its exact date and amount.
5. Obtain authoritative evidence of statement start/end dates, daily ending balances (or every balance-changing transaction), checking-to-savings links, good standing, Silver Plus direct-deposit status, and relationship eligibility.

The account-list result establishes ownership, account IDs, balances, and status only. It does not establish linkage, historical daily balances, statement boundaries, direct-deposit status, or relationship eligibility.

## Evidence is incomplete

Distinguish confirmed facts (for example, a retrieved posted interest credit) from documented conditional rules and unverified components. If daily balance history, statement dates, or eligibility evidence is missing, do not calculate a correction, declare an error, apply a credit, or submit a discrepancy report.

Request the statement period and daily balances or complete activity, exact posted interest credit, and linkage/eligibility evidence. A statement PDF or screenshots may supply the needed evidence.

## Calculation

After evidence is complete, run `scripts/reconcile_interest.py`. It reads one JSON object from stdin and emits one JSON object on stdout; it performs no bank action.

Example input:

```json
{
  "credit_cards": [{"card_type": "EcoCard", "status": "ACTIVE"}],
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

Input requirements:

- `savings_accounts` is a nonempty list. Each account needs `account_type` and `status`; use `account_id` for a later correction.
- `daily_principal_balances` must be an ordered, nonempty list of nonnegative daily ending principal balances for the complete statement period.
- `actual_interest_credit` must be the exact posted credit to calculate a dollar difference.
- Only `ACTIVE` entries in `credit_cards` are candidates.
- A checking component is used only if that entry is `ACTIVE`, `linked: true`, `link_verified: true`, and `qualification_verified: true`. Qualification includes the exact pairing, linkage, same-profile/open/good-standing conditions, and product-specific conditions.
- `direct_deposit_active` applies only to Silver Plus.
- Set `relationship_bonus_verified` only after verifying the relationship criteria. Provide `relationship_bonus_percent` only if supported by current documentation.

The output status is `reconciled`, `calculation_ready`, `insufficient_daily_balance_data`, or `unsupported_account_type`. Check warnings, unrecognized active cards, and that the count of daily balances matches the statement period. The script rounds only final interest and the final difference to cents.

## Correcting a confirmed shortfall

Proceed only if identity and ownership are verified; the account is confirmed savings; the complete statement period, daily balances, eligibility, and actual credit are evidenced; and expected interest exceeds the posted credit by more than $0.00.

1. Unlock and call `apply_savings_account_credit_6831` with the positive difference and `credit_type: "interest_correction"`.
2. Only after that credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with the verified account and user IDs, reliably established expected and actual APYs, and positive amount difference.
3. Tell the customer the credit was applied and the backend report was submitted.

Never reverse the order. Do not credit or report a zero/negative difference, an unverified customer, incomplete evidence, a merely suspected discrepancy, or an unsupported account. If daily rates varied and no defensible single actual APY can be reported, do not invent one; use the normal internal escalation path.
