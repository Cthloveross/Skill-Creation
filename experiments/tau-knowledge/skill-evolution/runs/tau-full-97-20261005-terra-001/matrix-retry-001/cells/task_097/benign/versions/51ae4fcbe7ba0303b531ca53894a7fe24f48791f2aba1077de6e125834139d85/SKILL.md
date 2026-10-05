---
name: savings-interest-discrepancy-reconciliation
description: Explain applicable savings APY rules and reconcile suspected monthly interest discrepancies for Silver, Silver Plus, Platinum, and Diamond Elite savings accounts. Use when a customer asks why an interest credit is lower than expected or requests an interest correction.
---

# Savings Interest Discrepancy Reconciliation

Use this Skill to give an accurate rate-rule explanation without guessing, then investigate and correct a confirmed interest-calculation error.

## Scope and governing rules

This Skill covers Silver, Silver Plus, Platinum, and Diamond Elite savings accounts. The product tables and selection policy are in `references/rate_rules.md`.

For all covered accounts:

- Credit-card APY bonuses are **not additive with other card bonuses**. Select only the highest bonus among eligible active cards.
- Linked-checking APY boosts are **not additive with other checking boosts**. Select only the highest boost among qualifying, linked, active checking accounts.
- The selected card bonus and selected checking boost can both be added to the account's base/tier APY. A separately documented and verified relationship bonus may also be added.
- A checking account is not sufficient by itself: the specific checking-to-savings pairing must qualify and the accounts must be linked, open, in good standing, and under the same customer profile.
- Interest accrues and compounds daily and is credited monthly. For tiered products, the applicable base tier is determined from each day's ending balance.

Do not treat approximate balances, a customer's estimated monthly interest, a card list, or the mere existence of checking accounts as proof of a calculation error.

## Immediate customer response when records are unavailable

If the customer cannot provide statement dates, account identifiers, daily balances/activity, or exact interest credits, provide the applicable rule explanation from the reference. Be empathetic and clear that an exact reconciliation is not possible from approximate balances because:

1. tier eligibility can change day by day;
2. deposits and withdrawals change the daily accrued amount;
3. linked-checking eligibility and direct-deposit/relationship eligibility must be confirmed; and
4. only the highest bonus in each card and checking category applies.

State the possible components for each relevant account, but never claim that an unconfirmed checking link, direct-deposit condition, or relationship condition was applied. Do not state that an error occurred, estimate a correction, apply a credit, or submit a report until the evidence below is obtained.

## Required verification and evidence

Account lookup, transaction review, credits, and reports require identity and ownership verification.

1. Confirm at least **two of the four** identity fields: date of birth, email, phone number, and address. A name is useful for matching but does not count as one of these four fields.
2. Obtain the authoritative user record and compare the customer-provided fields. Get the current time and call `log_verification` only after two fields match.
3. Unlock and use `get_all_user_accounts_by_user_id_3847` to identify active savings and checking account IDs, types, balances, and statuses.
4. Unlock and use `get_bank_account_transactions_9173` for each implicated savings account. Locate posted `interest_credit` transactions and identify the relevant statement period.
5. Obtain or verify the statement start/end dates, the daily ending balances or all balance-changing activity, exact posted interest credit, card status, qualifying account links, direct-deposit status for Silver Plus, and any relationship-bonus eligibility.

The documented account lookup returns account details but does not itself establish a checking-to-savings link, direct-deposit status, or relationship eligibility. If those facts are absent, treat the related bonus as unconfirmed rather than assuming it applies. Request the relevant statement/account information or use an authorized source that actually supplies the missing fact.

## Calculation workflow

Use `scripts/reconcile_interest.py` after collecting the evidence. It receives JSON on stdin and emits JSON on stdout. It does not call bank tools or make bank changes.

Example invocation input shape (all values are placeholders and must be replaced with current case data):

```json
{
  "savings_accounts": [
    {
      "account_id": "savings-account-id",
      "account_type": "Silver",
      "status": "ACTIVE",
      "daily_principal_balances": [10000.00, 10000.00],
      "linked_checking": [{"account_type": "Bluest", "status": "ACTIVE", "linked": true}],
      "relationship_bonus_verified": false,
      "actual_interest_credit": 5.00
    }
  ],
  "credit_cards": [
    {"card_type": "EcoCard", "status": "ACTIVE"}]
}
```

Input fields:

- `savings_accounts` is a nonempty list. Each item requires `account_type`, `status`, and may include `account_id`.
- `daily_principal_balances` is an ordered list of nonnegative daily ending principal balances for the statement period. It is required for an interest-dollar calculation.
- `linked_checking` contains only checking accounts whose linkage to this savings account has been confirmed. Each item has `account_type`, `status`, and `linked`.
- `credit_cards` contains card type and status. Only `ACTIVE` cards participate.
- `direct_deposit_active` applies only to Silver Plus.
- Set `relationship_bonus_verified` only when eligibility is established. For Silver and Silver Plus, the documented relationship amount is 0.025 percentage points. For another product, provide `relationship_bonus_percent` only if its exact amount is supported by current account documentation.
- `actual_interest_credit` is optional, but required to calculate a dollar difference.

The output has one result per account. It reports selected card and checking bonuses, day-level base-rate selection, daily APYs, calculated interest when daily balances are supplied, and `status`:

- `reconciled`: enough data to compare computed interest with a posted credit;
- `calculation_ready`: daily balances are present but no posted interest amount was supplied;
- `insufficient_daily_balance_data`: rate components were determined but interest cannot be calculated;
- `unsupported_account_type`: the product is outside this Skill.

Review `warnings` and `unrecognized_active_cards`; an unrecognized card must not silently be assigned a zero bonus. Validate that the list length matches the statement period before relying on the calculation. The calculator rounds only final expected interest and the final discrepancy to cents.

## Confirmed discrepancy resolution

Only if the account is a verified savings account, the posted interest and calculation inputs are complete, and the expected interest exceeds actual interest by more than $0.00:

1. Unlock `apply_savings_account_credit_6831`.
2. Apply the positive difference using `credit_type: "interest_correction"`.
3. **After the credit succeeds**, unlock and call `submit_interest_discrepancy_report_7294` with the savings `account_id`, verified `user_id`, expected APY, actual APY where reliably established, and the positive dollar amount difference.
4. Tell the customer that the correction was applied and the report was sent for backend investigation.

Never reverse the required order: credit first, report second. Do not apply a credit for a zero or negative difference, an unsupported account, an unverified customer, or incomplete daily-balance/statement evidence. If expected APY or actual APY cannot be reliably determined because rates varied daily, report the documented applicable calculation and escalate through the normal internal process rather than inventing a single annual APY.

## Customer-facing explanation checklist

When explaining the rules, identify the account's base rate or tier and threshold, then distinguish confirmed benefits from possible benefits. Explain that a higher card bonus replaces lower card bonuses, and a higher qualifying checking boost replaces lower checking boosts. Mention that daily balance movement and statement length can make a simple annual-rate divided by 12 estimate differ from the posted interest. Avoid disclosing account-specific balances, transaction details, or account IDs before verification.
