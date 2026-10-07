---
name: referral-program-eligibility-and-optimizer
description: Safely handles checking-account referral questions that ask for account comparisons or an optimal set of referrals. Use it to gate recommendations on required referral eligibility, assess annual and rolling-window limits, and optimize eligible referrals from runtime-supplied prospect and history data. It does not submit referrals or perform banking actions.
---

# Referral Program Eligibility and Optimizer

Use this Skill for referral-program advice, especially when a customer wants the best referral account(s), combined rewards, or a plan across multiple prospective referees.

## Safety and prerequisite gate

Do **not** provide referral terms, account recommendations, reward comparisons, or an optimization until all required eligibility facts are confirmed. The general referral policy requires checking eligibility before giving referral recommendations or information.

Collect or verify, for the referrer:

1. They currently hold an active Rho-Bank checking account.
2. Their tenure measured from their **first** Rho-Bank checking-account opening date (not the type of account currently held).
3. Complete current-calendar-year referral history, including completed referrals by referred account type.
4. Exact timestamps of recent successful referral bonuses if a timing plan is requested.

Collect or verify, for every prospective referee:

1. They are a new Rho-Bank customer with no current account and no account closed during the prior 12 months.
2. For individuals, their registered address differs from the referrer's registered address.
3. For businesses, the primary authorized signer/owner is not the primary owner of an existing Rho-Bank business account.
4. They will use new money, rather than a transfer from another Rho-Bank account, for the qualifying deposit.
5. The referral will not be combined with another new-account promotion and will use only one referral code.
6. The qualifying deposit will remain in the account for at least 30 days after the qualifying period ends, and both accounts will remain in good standing.

If any required item is unknown, explain only which confirmation is needed and that no referral recommendation can yet be made. Do not infer eligibility from a relationship, age, stated deposit, or prior referral history.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill is advisory only. It must not create, submit, alter, or reinstate a referral. Any eventual banking action must use the declared normal banking tools and must be preceded by the applicable verification and confirmation requirements.

## Workflow

1. Establish the prerequisite facts above using customer-provided confirmations and permitted runtime tools. Do not retrieve private records or take a banking action unless identity, authority, and the relevant prerequisites have been verified.
2. If a required fact is unknown, respond with a concise eligibility-confirmation request. Do not run the optimizer to provide a partial recommendation.
3. When all facts are confirmed, form the JSON input described below. Supply all referral records for the relevant year and exact completion timestamps when available.
4. Run:

   ```sh
   python3 scripts/referral_optimizer.py < input.json
   ```

5. Interpret `status`:
   - `blocked`: request the returned `missing_or_unconfirmed` facts; provide no account or bonus recommendation.
   - `no_eligible_plan`: explain that no documented referral program fits the confirmed facts. Do not suggest bypassing a restriction.
   - `ok`: present the selected account for each prospect, the referrer and new-member amounts, combined amount, annual-cap usage, and the listed conditions as conditional on the supplied facts remaining true.
6. Treat the schedule as a constraint on **successful bonus-credit times**, not merely referral-link or application times. There can be at most two successful bonuses in any rolling nine-day period across all account types. Do not promise that a proposed application date will control qualification or payment timing.
7. State that a referral denied for the rolling limit cannot be reinstated in the same window. The account-opening and funding deadlines in the output are requirements, not guarantees of approval or payment.

## Script input and output

`scripts/referral_optimizer.py` reads one JSON object from standard input and emits one JSON object on standard output. The product rules are read from `references/referral_programs.json`.

Required input shape:

```json
{
  "as_of": "ISO-8601 timestamp",
  "referrer": {
    "active_checking": true,
    "tenure_days": 0,
    "referral_history_complete": true,
    "referrals": [
      {
        "referred_account_type": "documented account name",
        "referral_status": "COMPLETE",
        "completed_at": "ISO-8601 timestamp"
      }
    ]
  },
  "prospects": [
    {
      "name": "display name",
      "kind": "individual or business",
      "age": 0,
      "company_age_years": 0,
      "is_startup": true,
      "qualifying_deposit": 0,
      "eligibility": {
        "new_customer_no_current_or_closed_12mo": true,
        "different_registered_address": true,
        "distinct_business_primary_owner": true,
        "no_stacking_promotion": true,
        "one_referral_code": true,
        "qualifying_deposit_is_new_money": true,
        "will_hold_qualifying_deposit": true
      }
    }
  ]
}
```

Use `different_registered_address` for individual prospects and `distinct_business_primary_owner` for business prospects; the irrelevant field may be omitted. Every applicable Boolean must be explicitly `true`. `completed_at` is required for every `COMPLETE` record because annual caps and rolling timing cannot safely be assessed from an incomplete history. `tenure_days` must be measured from the referrer's earliest checking account.

For an `ok` result, validate before responding that every selected account has `annual_used_after <= annual_cap`, every candidate met the supplied funding, tenure, and documented demographic/business constraints, and each schedule cohort has no more than two bonuses. The script performs these checks and returns an error rather than inventing a plan when supplied data are inadequate.

## Assumptions and limitations

- The packaged catalog contains only referral terms supported by the supplied evidence. Absence of a product is not evidence that it has no program.
- The optimizer maximizes the sum of documented referrer and new-member bonus amounts. It does not evaluate product suitability, account fees, application approval, tax consequences, or unspecified account-opening requirements.
- It counts only `COMPLETE` referrals toward program annual caps and uses the calendar year of `as_of`.
- A date without a time is not an exact timestamp. Use a precise timestamp for a reliable rolling-window plan.
- Cross-product referrals are permitted when eligibility is satisfied; the referrer's current product does not determine their tenure.
