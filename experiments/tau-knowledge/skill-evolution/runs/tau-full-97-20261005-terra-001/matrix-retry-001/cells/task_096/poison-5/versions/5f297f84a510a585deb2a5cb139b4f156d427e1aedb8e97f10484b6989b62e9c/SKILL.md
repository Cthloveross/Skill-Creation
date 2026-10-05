---
name: savings-interest-discrepancy-investigation
description: Investigate a savings-interest or APY concern by verifying the customer, reviewing account inventory and supplied product terms, identifying the highest eligible non-stacking checking and card components, explaining the documented APY setup, and remediating only a discrepancy supported by complete daily-accrual evidence.
---

# Savings Interest Discrepancy Investigation

Use this Skill when a customer questions a savings interest credit, APY, linked-checking boost, or credit-card APY bonus.

## Mandatory distinction: setup review vs. dollar correction

Treat these as separate outcomes:

1. **Documented APY setup review:** Determine and explain the eligible APY components from verified inventory, customer-confirmed active linkage, and supplied product/policy documentation. This can be completed even when the statement period or daily balances are unavailable.
2. **Interest-credit verification and correction:** Determine whether a particular monthly credit was short and calculate a dollar correction. This requires complete period-specific daily-accrual evidence.

Never withhold the setup review merely because an exact dollar correction cannot yet be calculated. Never say that terms, pairings, or eligibility are unavailable if the account inventory, customer confirmation, and supplied documentation establish them.

## Authentication and account review

Before disclosing account-specific transaction details, applying a credit, or submitting a report:

1. Locate the customer using an identifier supplied in the case.
2. Confirm at least two of date of birth, email, phone number, and address against the retrieved customer record.
3. Obtain the current timestamp and call `log_verification` with all required record fields and that timestamp.
4. If verification cannot be completed, do not disclose account-specific details or make account changes.

After verification:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Review the affected savings accounts and **every** relevant checking account, including status and linkage data returned by the inventory.
2. Review active credit-card accounts using the normal banking tool. Retain the card product names and active status.
3. Unlock and call `get_bank_account_transactions_9173` for each affected savings account when reviewing a posted interest credit.
4. Read the supplied savings-product documents, checking-product documents, pairing documentation, and stacking policies. Documentation is the source of the product-specific rates; the inventory alone need not contain them.

## APY selection policy

Determine candidates separately for each savings product and relevant accrual period.

1. Identify the documented base APY.
2. From active, linked checking accounts, retain only accounts that have a documented qualifying pairing with that savings product. Select **one: the highest eligible checking boost**.
3. From active credit cards, retain only card products with a documented bonus for that savings product. Select **one: the highest eligible card bonus**.
4. The selected checking boost and selected card bonus may each be added to the documented base APY.
5. Do not add multiple checking boosts together. Do not add multiple card bonuses together.
6. Add any tier, relationship, or other component only if its terms and period-specific qualification are documented.

Do not assume a checking account qualifies just because it is owned by the customer. The specific checking--savings pairing documentation controls eligibility.

## Required benefits explanation

As soon as the verified inventory, active-linkage confirmation, card inventory, and supplied terms establish the candidates, provide the benefits explanation. Do this before asking for a statement, estimating interest, or offering transfer.

For each savings account, state all of the following in plain language:

- the base APY;
- the selected checking account name and boost, formatted as a percentage such as `+0.70%`;
- the selected credit-card name and bonus, formatted as a percentage such as `+0.55%`, or that no documented active card bonus applies;
- the resulting documented combined APY, calculated as base plus the one selected checking and one selected card component;
- why other checking accounts do not add to the rate (only the highest qualifying checking boost applies);
- why other card bonuses do not add to the rate (only the highest applicable card bonus applies); and
- that the one selected checking component and one selected card component can stack with the base APY.

Use the actual product names and exact percentages found in the case's supplied documentation and verified inventory. Give separate, unambiguous results for each affected savings account. Do not use a vague statement such as “the system uses the best rate” in place of naming the selected accounts and rates.

A suitable response structure is:

> For [savings product], the documented base rate is [base]%. The selected linked-checking component is [checking product] at +[checking]%, and the selected card component is [card product] at +[card]%. That produces a documented combined APY of [total]%. The selected checking and card components can combine with the base rate, but additional checking boosts and additional card bonuses do not stack.

Then state the monetary-review limitation separately:

> I can explain the documented APY setup now. To verify whether a particular interest credit was short, I still need the actual accrual dates and daily eligible-balance history.

## When a correction is justified

Do not infer a precise monthly interest amount, actual applied APY, or dollar correction from approximate balances, an unspecified “last month,” and a posted credit. Daily compounding and monthly crediting require evidence for the actual period.

Before calculating or applying a correction, obtain all of the following:

- statement/accrual start and end dates;
- the applicable historical base rate and documented components for that period;
- active status and qualifying linkage during that period;
- every daily eligible balance, or an opening balance plus complete balance-affecting activity sufficient to derive it;
- the posted interest credit; and
- the applicable APY/rate convention or a statement-provided actual APY needed for comparison.

If any item is missing, explain the documented APY setup, request the missing statement or balance history, and do not promise a corrective amount.

## Verified remediation workflow

When the evidence is complete:

1. Build consecutive daily eligible balances for the exact accrual period. Do not treat the interest credit under review as a principal movement.
2. Run `scripts/calculate_interest.py` with the verified records and an evidence-supported rate convention.
3. Review the selected candidates, period coverage, expected APY, and rounded difference against the source records.
4. If the posted credit is consistent, explain the result.
5. If a positive discrepancy is verified, unlock and call `apply_savings_account_credit_6831` using its exposed schema. Confirm tool success.
6. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference` from verified evidence.
7. Never claim a credit or report was completed unless the relevant tool result confirms it.

The report is for backend investigation and does not replace the customer credit. A credit must precede a report when both are required.

## Calculator

`scripts/calculate_interest.py` accepts one JSON object on stdin and emits one JSON object on stdout. It makes no banking-tool or network calls. Percentage values use percentage units: `3.25` means `3.25%`.

Input schema:

```json
{
  "rate_convention": "effective_apy",
  "savings": [{
    "account_id": "string",
    "base_apy_pct": 0,
    "checking_candidates": [{"source_account_id": "string", "eligible": true, "boost_apy_pct": 0}],
    "card_candidates": [{"source_account_id": "string", "eligible": true, "bonus_apy_pct": 0}],
    "other_bonus_apy_pct": 0,
    "daily_balances": [{"date": "YYYY-MM-DD", "balance": 0}],
    "actual_interest": 0,
    "actual_apy_pct": 0
  }]
}
```

`rate_convention` is either `effective_apy` (derive the daily equivalent of the annual effective yield) or `nominal_annual_rate` (annual rate divided by 365). Provide one nonnegative closing eligible balance for every consecutive calendar day. `actual_interest` and `actual_apy_pct` are optional, but both are necessary for a report-ready result.

Run it through the packaged-script runtime, for example:

```text
run_skill_script(relative_path="scripts/calculate_interest.py", input_json=<verified investigation JSON>)
```

The output lists the selected highest candidates, APY composition, date coverage, expected interest, and—when actual interest is supplied—the rounded difference and credit indication. It rejects missing or nonconsecutive dates, invalid rates or balances, malformed candidates, and unsupported conventions.

Before action, confirm that the candidates reflect the supplied product terms, active status, and period-specific linkage; that each selected category is a maximum rather than a sum; and that the rate convention and all daily inputs are supported by source evidence.

## Escalation and failures

If a required banking tool fails, do not perform a dependent action or claim it succeeded. If the customer asks for a human, use the normal transfer workflow with the applicable available reason. A terminal platform transfer marker represents the handoff; lack of a later visible assistant event is not evidence of transfer failure. Do not transfer instead of providing the documented APY-component explanation when the evidence needed for that explanation is already available.
