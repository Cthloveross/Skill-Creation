---
name: savings-interest-discrepancy-investigation
description: Investigate a savings-interest, APY, linked-checking boost, or card-bonus concern by reviewing verified account inventory and product terms, explaining the highest eligible non-stacking APY components, and correcting interest only when complete daily-accrual evidence proves a shortfall.
---

# Savings Interest Discrepancy Investigation

Use this Skill for a customer who questions savings interest, an APY, a checking-linked boost, or a credit-card APY bonus.

## Two distinct outcomes

Keep the following work separate:

1. **APY setup review:** identify and explain documented base APY, qualifying checking boost, and qualifying card bonus. This is possible without a statement period or daily balances when account ownership, active linkage, and product terms are known.
2. **Interest-credit correction:** determine whether a particular monthly interest posting was short and calculate a dollar credit. This requires complete, period-specific daily-accrual evidence.

Do not withhold a documented setup review because an exact correction cannot be calculated. Conversely, do not infer an actual applied APY, a monthly shortage, or a dollar correction from an approximate balance and a single monthly interest posting.

## Verify and review account evidence

Before disclosing transaction details, crediting an account, or filing a report:

1. Locate the customer from an identifier they provided.
2. Confirm at least two of email, phone number, address, and date of birth against the retrieved record.
3. Obtain the current timestamp and call `log_verification` with the retrieved record fields and timestamp.
4. If verification is incomplete, do not disclose account-specific information or make account changes.

After verification:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user ID. Review every affected savings account and every potentially relevant checking account.
2. Use `get_credit_card_accounts_by_user` to identify active card products.
3. For a posted-interest investigation, unlock and call `get_bank_account_transactions_9173` for each affected savings account.
4. Read the supplied savings-product, checking-product, qualifying-pairing, and stacking-policy documentation. Product terms are authoritative for rates and pairings; inventory records need not repeat the terms.
5. Use customer confirmation of active linkage for the relevant period when inventory linkage details are not otherwise available. If linkage is disputed or unknown, explain only the conditional documented result and request confirmation.

## Mandatory APY-component selection

For **each** affected savings product, make a separate candidate list from the verified inventory and supplied documentation:

1. Record the documented base APY.
2. Keep a checking account only if it is active/linked for the relevant period **and** its specific checking--savings pairing is documented as qualifying. Select exactly one: the highest eligible checking boost.
3. Keep a credit card only if it is active and the savings product documents a bonus for that card product. Select exactly one: the highest eligible card bonus.
4. Add the base APY, the one selected checking boost, and the one selected card bonus. Add another tier or relationship component only when its terms and period-specific qualification are documented.

The policy categories are independent:

- Multiple checking boosts never stack; choose the highest qualifying checking component.
- Multiple card bonuses never stack; choose the highest applicable card component.
- The selected checking component and selected card component may stack with each other and with the base APY when the supplied policy says they do.

Do not assume a checking product qualifies merely because the customer owns it. The specific pairing document controls. Do not say product terms or eligibility are unavailable when supplied documentation, verified inventory, and active-linkage confirmation establish the candidates.

## Required customer response once candidates are known

Provide the benefits explanation immediately after the evidence establishes it—before requesting statements, calculating interest, or offering escalation. Give a separate, explicit result for every savings account:

- savings product and documented base APY;
- selected checking product and its boost;
- selected card product and its bonus;
- combined documented APY;
- that other qualifying checking boosts do not add because only the highest checking boost applies;
- that other card bonuses do not add because only the highest card bonus applies; and
- that the selected checking and card components can stack with the base APY.

Use the actual product names and source rates from the case documentation. Preserve the source's meaningful decimal precision in the customer-facing response. For example, if a source says `0.7%`, say `+0.7%` rather than changing it solely to `+0.70%`. This makes the explanation readily auditable against the supplied terms.

Use this structure, filling it solely with verified, case-specific information:

> For [savings product], the documented base APY is [base]%. [selected checking] supplies the highest eligible linked-checking boost, +[checking]%, and [selected card] supplies the highest applicable card bonus, +[card]%. Together, the documented APY is [total]%. Other checking boosts do not stack with the selected checking boost, and other card bonuses do not stack with the selected card bonus; the one selected checking boost and one selected card bonus do stack with the base APY.

Run `scripts/select_apy_components.py` after screening candidates if a deterministic selection and response-ready summary is useful. Its output supports the explanation but does not establish active status, pairing eligibility, or linkage; those facts must be established from the investigation first.

Then state the monetary limitation separately:

> I can explain the documented APY setup now. To verify whether a particular interest credit was short, I need the actual accrual dates and daily eligible-balance history.

## Exact interest verification and remediation

Daily compounding and monthly crediting mean that approximate balances, an unspecified “last month,” and a posted interest amount do not establish an exact expected credit. Before calculating or applying a correction, obtain:

- statement/accrual start and end dates;
- applicable historical base rate and all documented qualifying components for that period;
- active status and qualifying linkage throughout that period;
- every daily eligible balance, or sufficient complete balance activity to derive every daily balance;
- the posted interest credit; and
- an evidence-supported annual-rate convention and actual APY where needed for a report.

If any item is missing, request the missing statement or balance history and do not promise an amount, credit, or report.

When all evidence is present:

1. Build consecutive daily eligible balances for the exact period; do not treat the interest credit under review as principal movement.
2. Run `scripts/calculate_interest.py` with the verified data and supported rate convention.
3. Confirm the selected candidates are category maxima, all dates are covered, and the output agrees with source records.
4. If the posting is consistent, explain that result.
5. If a positive shortfall is verified, unlock and call `apply_savings_account_credit_6831` using its exposed schema, then confirm tool success.
6. Only after a successful credit, unlock and call `submit_interest_discrepancy_report_7294` with the documented `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`.
7. Never claim that a credit or report was completed without its successful tool result.

A report does not replace the customer credit; when both are justified, the credit precedes the report.

## Script interfaces

All packaged scripts read one JSON object from stdin and emit one JSON object to stdout. They make no banking or network calls.

### Component selector

`scripts/select_apy_components.py` takes percentage values in percentage units (`3.25` means `3.25%`):

```json
{
  "savings": [{
    "savings_name": "string",
    "base_apy_pct": 0,
    "checking_candidates": [{"source_name": "string", "eligible": true, "boost_apy_pct": 0}],
    "card_candidates": [{"source_name": "string", "eligible": true, "bonus_apy_pct": 0}],
    "other_bonus_apy_pct": 0
  }]
}
```

It returns the selected maximum candidate in each category, APY composition, and a response-ready summary. Feed it only candidates already screened against verified active status, documented pairings, and relevant-period linkage.

### Daily-interest calculator

`scripts/calculate_interest.py` accepts:

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

`rate_convention` is `effective_apy` or `nominal_annual_rate`. Daily balances must be nonnegative and consecutive. `actual_interest` and `actual_apy_pct` are optional, but both are needed for a report-ready result. The calculator rejects incomplete or malformed data rather than estimating it.

For either script, use the packaged-script runtime, for example:

```text
run_skill_script(relative_path="scripts/select_apy_components.py", input_json=<screened component JSON>)
```

## Failures and escalation

If a banking tool fails, do not perform a dependent action or claim success. If the customer requests a human, use the normal transfer workflow and an applicable available reason. A terminal platform transfer marker is evidence of handoff; absence of a later assistant event is not evidence that transfer failed. Do not transfer instead of giving the documented APY-component explanation when the evidence for that explanation is already available.
