---
name: savings-interest-discrepancy-investigation
description: Investigate a claimed savings-interest shortfall by verifying the customer, reviewing account inventory and product terms, selecting the highest non-stacking checking and card APY components, explaining the applicable boosts, and taking corrective action only when daily accrual evidence verifies a discrepancy.
---

# Savings Interest Discrepancy Investigation

Use this Skill when a customer questions savings interest, APY, a linked-checking boost, or a credit-card APY bonus.

## Core policy

Determine APY components separately for each affected savings account and for the relevant accrual period.

1. Establish the savings product's documented base APY for that period.
2. Build a list of qualifying, active linked-checking candidates from the customer's verified account inventory and the documented checking--savings pairings.
3. Select **only the highest eligible checking boost**. Checking boosts do not stack with one another.
4. Build a list of documented card-bonus candidates for active cards held by the customer during the period.
5. Select **only the highest eligible card bonus**. Card bonuses do not stack with one another.
6. The selected checking component and the selected card component may stack with each other and with a documented base APY. Add a tier, relationship, or other component only when its terms and period-specific qualification are established.

Do not assume that a checking account applies to every savings product. Product pairing documentation controls eligibility, not the fact that accounts are under the same profile.

## Authentication and account review

Before disclosing account-specific transaction details, applying a credit, or submitting a report:

1. Locate the customer using an identifier supplied by the customer or otherwise available in the active case.
2. Confirm at least two of date of birth, email, phone number, and address against the retrieved customer record.
3. Obtain the current timestamp and call `log_verification` with every required record field and that timestamp.
4. If the confirmation cannot be completed, do not disclose account-specific information or make account changes.

After verification, use the normal banking-tool workflow:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Identify the affected savings account IDs and all relevant checking accounts, including account status and linkage information available from the inventory.
2. Review active credit cards using the available normal banking tool and retain only cards whose product bonus is documented for the affected savings product.
3. Unlock and call `get_bank_account_transactions_9173` for each affected savings account. Locate the posted monthly interest credit and obtain the actual accrual/statement period, daily balance-affecting activity, and any statement-disclosed APY.
4. Read the supplied product and policy documentation to determine the eligible candidates and their percentages. Do not say that product terms or eligibility are unavailable when the verified inventory, customer confirmation, and supplied documentation establish them.

## Required customer explanation

When a verified customer asks which accounts or boosts are being used, give the component answer even if a precise dollar-interest review cannot yet be completed.

For **each** savings account, clearly state:

- the qualifying checking account selected and its APY boost;
- the qualifying card selected and its APY bonus, if any;
- that all other eligible checking candidates are not added because only the highest checking boost applies;
- that all other eligible card candidates are not added because only the highest card bonus applies; and
- that the one selected checking boost and one selected card bonus can stack.

Use account names and exact percentages drawn from the runtime inventory and supplied terms. Make it unambiguous which component belongs to which savings account. Do not replace this explanation with a generic request for a statement merely because the exact dollar calculation is not yet possible.

A concise structure is:

> For [savings account], the selected checking component is [checking account] at [+rate], and the selected card component is [card] at [+rate]. Those two selected components can combine with the account's base APY. Other checking boosts and other card bonuses are each non-stacking, so they are not added.

Then distinguish component eligibility from monetary verification: daily compounding requires the actual accrual dates and daily eligible balances to validate a posted interest amount.

## Determining whether a correction is justified

Approximate balances, a recollection of "last month," and a posted interest transaction alone do not establish an exact shortfall. Do not promise or apply a precise corrective credit unless all required evidence is available:

- the actual statement/accrual start and end dates;
- the historical base rate and applicable documented components for that period;
- verified active/linkage status during that period;
- daily eligible balances or sufficient transaction and opening-balance evidence to derive them;
- the posted interest credit; and
- the bank's applicable APY/rate convention or a statement-provided actual APY where required for the comparison.

If any of these are missing, explain the selected APY components, explain the limitation, and request the statement or balance history. Do not infer an actual APY, an exact monthly interest amount, or a correction from approximate balances.

## Calculation and remediation workflow

Once the evidence is complete:

1. Assemble daily closing eligible balances in chronological order, excluding the interest credit being reviewed from principal movements.
2. Run `scripts/calculate_interest.py` using the schema below. Review its selected candidates, date coverage, APY composition, and rounded difference against the source records.
3. If the posted credit is consistent, explain the result and the non-stacking selections.
4. If a positive discrepancy is verified, unlock and call `apply_savings_account_credit_6831` with the exposed required schema. Confirm its success.
5. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference` from verified evidence and the applicable tool schema.
6. Never claim that a credit or report succeeded unless its tool result confirms it. A report does not replace the required customer credit.

## Calculator

`scripts/calculate_interest.py` reads one JSON object from standard input and emits one JSON object on standard output. It makes no network or banking-tool calls. Percent fields use percentage units: `3.25` means `3.25%`.

### Input schema

```json
{
  "rate_convention": "effective_apy",
  "savings": [
    {
      "account_id": "string",
      "base_apy_pct": 0,
      "checking_candidates": [
        {"source_account_id": "string", "eligible": true, "boost_apy_pct": 0}
      ],
      "card_candidates": [
        {"source_account_id": "string", "eligible": true, "bonus_apy_pct": 0}
      ],
      "other_bonus_apy_pct": 0,
      "daily_balances": [
        {"date": "YYYY-MM-DD", "balance": 0}
      ],
      "actual_interest": 0,
      "actual_apy_pct": 0
    }
  ]
}
```

`rate_convention` must be either:

- `effective_apy`: treat the composed APY as an annual effective yield and derive its daily equivalent; or
- `nominal_annual_rate`: divide the composed annual percentage rate by 365.

Supply exactly one nonnegative closing eligible balance for every calendar day in the accrued period, in ascending consecutive date order. `actual_interest` and `actual_apy_pct` are optional, but both are needed for the calculator's `report_ready` flag.

The runtime can invoke it as:

```text
run_skill_script(relative_path="scripts/calculate_interest.py", input_json=<verified investigation JSON>)
```

The result contains selected candidates, APY components, period coverage, expected interest, and—when an actual credit was supplied—the rounded difference and whether a credit is indicated. The script rejects incomplete dates, duplicate dates, invalid amounts, invalid candidate records, unsupported conventions, and nonpositive composed APY.

### Validate before action

- Confirm the input candidates reflect product documentation, account status, and period-specific linkage.
- Confirm each candidate category selected a maximum rather than a sum.
- Confirm the daily-balance dates and posted-interest input match source evidence.
- Confirm the chosen rate convention is supported by the applicable disclosure or bank process.
- Use a positive rounded output difference only after independently reviewing the source evidence. Do not submit a report based solely on an estimate.

## Escalation and failures

If a required banking tool fails, do not continue to a dependent action and do not claim it completed. If the customer requests a human agent, use the normal transfer workflow and select the applicable transfer reason from the knowledge base before calling the transfer tool. A terminal platform transfer marker represents the handoff; do not treat the absence of a later visible assistant message as a failed transfer.
