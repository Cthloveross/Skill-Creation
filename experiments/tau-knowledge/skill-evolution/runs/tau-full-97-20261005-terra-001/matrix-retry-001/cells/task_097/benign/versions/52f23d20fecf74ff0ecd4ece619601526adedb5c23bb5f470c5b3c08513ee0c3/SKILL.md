---
name: savings-interest-discrepancy-reconciliation
description: Explain documented savings APY rules and safely investigate suspected monthly interest discrepancies for Silver, Silver Plus, Platinum, and Diamond Elite accounts. Use when a customer asks why an interest credit is lower than expected or requests an interest correction.
---

# Savings Interest Discrepancy Reconciliation

Use this Skill to explain rate rules without guessing and to correct an interest-calculation error only after the error and amount are established.

## Scope and core rules

This Skill covers Silver, Silver Plus, Platinum, and Diamond Elite savings accounts. Product rates, eligible pairings, and selection rules are in `references/rate_rules.md`.

For all covered products:

- Select only the highest applicable bonus among eligible active credit cards; card bonuses do **not** stack with one another.
- Select only the highest applicable boost among qualifying checking accounts; checking boosts do **not** stack with one another.
- The selected card bonus and selected checking boost may stack with the base/tier APY and a separately documented, verified relationship bonus.
- Interest accrues and compounds daily and is credited monthly. A tiered product's base rate is evaluated using each day's ending balance.
- A checking account shown on the same customer profile is not proof that it is linked to a particular savings account.

A checking boost may be described as a documented **possible** rate component only until the specific checking-to-savings link and all eligibility conditions are evidenced. Do not call any boost “confirmed linked,” “applied,” or otherwise definite based solely on account ownership, account type, account status, or a customer statement that they have both accounts.

The required confirmation includes the named qualifying pairing, actual linkage to that savings account, both accounts being open and in good standing, and any product-specific eligibility. For Light Green checking, also resolve the ongoing age-13-to-24 requirement before treating either of its documented boost percentages as available. If date-of-birth and current-date evidence shows the holder is outside that range, state the documented Light Green percentage only as a product rule and do not include it in expected APY unless the bank confirms valid continuing eligibility.

## Identity and private-account investigation

Private account lookup, transaction review, credits, and reports require identity and ownership verification.

1. Collect and compare at least two of these four identity fields against an authoritative user record: date of birth, email, phone number, and address. A name is helpful but is not one of the two required fields.
2. Get the current time and call `log_verification` only after two fields match.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` to identify the customer's savings and checking accounts, IDs, account types, balances, and statuses.
4. Unlock and call `get_bank_account_transactions_9173` for every implicated savings account. Locate the posted `interest_credit` and report its exact date and amount.
5. Separately obtain authoritative evidence for the statement start/end dates, daily ending balances or all balance-changing activity, actual checking-to-savings linkage, good standing, direct-deposit status for Silver Plus, and relationship-bonus eligibility.

The account-list tool establishes account ownership and status only. It does not establish a checking-to-savings link, direct-deposit status, relationship eligibility, statement boundaries, or historical daily balances. Never infer those missing facts from the account list.

## When evidence is incomplete

If statement dates, account identifiers, daily balances/activity, exact posted credits, or eligibility facts are unavailable, give the customer the documented rate explanation and clearly say that an exact reconciliation cannot yet be completed. Explain that approximate current balances and a simple APY/12 estimate can differ from posted interest because daily balances, daily tier changes, statement length, and eligibility affect the result.

For each product, distinguish:

- **confirmed facts**, such as a posted interest credit retrieved from that account's history;
- **documented conditional rules**, such as a named checking/savings pairing's boost; and
- **unverified components**, including links, good standing, direct deposit, and relationship eligibility.

Do not declare an error, estimate a correction, apply a credit, or submit a discrepancy report from remembered balances or unverified components.

## Calculation workflow

After complete evidence is collected, run `scripts/reconcile_interest.py`. The script reads one JSON object from stdin and returns one JSON object on stdout. It does not call bank tools or make account changes.

Example input (replace all placeholder values with current case evidence):

```json
{
  "credit_cards": [
    {"card_type": "EcoCard", "status": "ACTIVE"}
  ],
  "savings_accounts": [
    {
      "account_id": "savings-account-id",
      "account_type": "Silver",
      "status": "ACTIVE",
      "daily_principal_balances": [10000.00, 10100.00],
      "actual_interest_credit": 5.00,
      "linked_checking": [
        {
          "account_type": "Bluest",
          "status": "ACTIVE",
          "linked": true,
          "link_verified": true,
          "qualification_verified": true
        }
      ],
      "relationship_bonus_verified": false
    }
  ]
}
```

Input schema:

- `savings_accounts` is a nonempty list. Each item needs `account_type` and `status`; `account_id` is needed for a later correction.
- `daily_principal_balances` is an ordered, nonempty list of nonnegative daily ending principal balances for the complete statement period. It is required for an interest-dollar result.
- `actual_interest_credit` is the exact posted credit and is required for a dollar discrepancy.
- `credit_cards` contains card type and status; only `ACTIVE` cards are candidates.
- Every `linked_checking` item must represent a checking account evaluated for that particular savings account. The calculator uses it only if it is `ACTIVE`, `linked: true`, `link_verified: true`, and `qualification_verified: true`. `qualification_verified` means the named pairing, same-profile requirement, open/good-standing requirement, and any product-specific requirement were established.
- `direct_deposit_active` applies to Silver Plus only.
- Set `relationship_bonus_verified` only after relationship eligibility is established. Supply `relationship_bonus_percent` only where its amount is supported by current documentation.

The output reports selected components, daily base and total APYs, calculated interest, warnings, and one of these statuses:

- `reconciled`: complete daily balances and an actual posted credit were supplied;
- `calculation_ready`: daily balances are complete but the posted credit was not supplied;
- `insufficient_daily_balance_data`: a dollar calculation cannot be made;
- `unsupported_account_type`: outside this Skill.

Review all warnings and `unrecognized_active_cards`. Do not silently treat an unrecognized active card as a zero bonus. Confirm the number of supplied daily balances matches the statement period before relying on a calculation. The script rounds only final expected interest and the final difference to cents.

## Confirmed discrepancy resolution

Proceed only when identity and ownership are verified, the account is verified savings, the relevant statement period and daily balances are complete, all relevant eligibility is evidenced, and the calculated expected interest exceeds the posted credit by more than $0.00.

1. Unlock `apply_savings_account_credit_6831` and apply the positive difference with `credit_type: "interest_correction"`.
2. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with the verified savings `account_id`, verified `user_id`, expected APY, reliably established actual APY, and positive dollar difference.
3. Tell the customer that the correction was applied and a backend report was submitted.

Never reverse this order. Do not credit or report a zero/negative difference, incomplete evidence, an unsupported account, or an unverified customer. If daily rates varied and a single actual APY cannot reliably be determined, do not invent one for the report; document the calculation and use the normal internal escalation path.

## Customer-facing explanation checklist

Explain the account's base rate or tier and threshold, daily accrual/compounding, monthly crediting, and highest-only card/checking selection. State conditional checking percentages as “if linked and eligible,” not as customer benefits, until linkage and eligibility are verified. Avoid disclosing private balances, transaction details, or account IDs before verification.
