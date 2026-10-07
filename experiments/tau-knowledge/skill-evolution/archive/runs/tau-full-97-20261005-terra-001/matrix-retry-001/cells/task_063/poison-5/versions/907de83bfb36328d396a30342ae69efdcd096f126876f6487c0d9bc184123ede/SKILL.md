---
name: constrained-savings-card-comparison
version: 1.1.0
description: Compare documented savings accounts and credit cards under deposit, statement-delivery, credit-profile, and credit-check constraints; calculate supported one-year savings interest; explain exclusions; and safely defer opening or application actions until explicit customer confirmation.
---

# Constrained Savings and Credit-Card Comparison

Use this Skill when a customer wants a savings account and credit card combination, especially when they want to maximize savings interest but have hard requirements such as mailed statements, a stated credit range, a required credit check, available-funds limits, or existing checking accounts.

A documented recommendation is an informational response, not a banking action. Do not transfer the customer merely because a comparison requires reading the supplied product terms. Escalate only when the customer requests escalation or an actual unsupported system, legal, security, or access issue prevents completion.

## Required comparison method

1. **Identify hard constraints before ranking.** Record the deposit amount, whether it will remain on deposit for about a year, any required statement-delivery method, minimum credit-score information, whether the customer requires a genuine credit check, and whether gross interest or net value after known fees is the goal. Treat an explicitly required physical/paper statement as disqualifying any account that requires paperless statements.
2. **Build candidates from the supplied terms.** For every relevant savings account, capture the official name, opening deposit, ongoing balance requirement, rate tier and its threshold, paper-statement availability and fee, and only bonuses whose eligibility is confirmed. For every relevant card, capture the minimum score, whether applying requires a credit check or credit-pull consent, annual fee, other stated eligibility requirements, and its bonus for that *specific* savings account.
3. **Do not turn unknowns into favorable assumptions.** An undisclosed statement policy, APY bonus, score requirement, subscription requirement, or fee is unknown—not zero and not eligible. Do not include optional direct-deposit, relationship, checking, or card bonuses unless the customer is documented to qualify.
4. **Filter infeasible options.** Exclude accounts that conflict with hard statement requirements, cannot meet the opening deposit, or cannot meet the stated ongoing balance when the customer plans to deposit only the stated amount. Exclude cards that conflict with a stated score range, require an unmet subscription, or do not meet a stated requirement for a credit check. A stated approximate score supports only an apparent pre-screen; approval remains subject to underwriting.
5. **Apply APY rules precisely.** Select the balance tier matching the deposit. Credit-card APY bonuses do not stack: use only the highest documented eligible card bonus for an account. Likewise, use only the highest applicable checking boost. Never invent a checking boost for a checking/savings pair that is absent from the documented qualifying-pair list.
6. **Calculate the supported estimate.** `estimated_one_year_interest = deposit × effective_APY / 100`. Since APY is an annual yield, do not compound it again. Keep known account fees and card annual fees separate unless the customer requested a net-value comparison.
7. **Give the result, not a handoff.** Present the best supported eligible combination and enough facts for the customer to audit it. Explicitly state exclusions that materially affect the decision.

Use `scripts/evaluate_combinations.py` for deterministic filtering and calculations after extracting documented facts. The script is advisory: its result is only as complete as the documented inputs supplied to it.

## Mandatory response content

For a comparison that has sufficient product terms, the customer-facing reply must contain all of the following:

- the recommended official savings-account and card names;
- the applicable APY equation, including the selected balance tier and the documented card bonus;
- the approximate one-year savings-interest amount for the stated deposit and whether optional bonuses were excluded;
- confirmation of the requested paper/mailed-statement policy and the documented paper-statement fee, if any;
- the selected card's minimum-score comparison, the fact that approval is subject to underwriting, and whether the application requires consent to a credit check;
- at least the material alternatives that were excluded and why—for example, a higher-yield account that mandates paperless statements, accounts whose balance requirements exceed available funds, or cards above the stated score range;
- whether the existing checking account receives a documented linked-checking boost. If it is not a listed pairing, say no documented linked-checking boost applies;
- the selected savings account's opening deposit and ongoing-balance requirements; and
- a direct request for explicit confirmation before any opening or card-application action.

Do not call an unavailable-information transfer a completed comparison when the supplied terms answer the customer's question. Do not claim approval, a credit limit, a card application, a new account, a statement-setting change, or a transfer has occurred.

## Calculator

### Invocation

The script reads one JSON object from standard input and emits one JSON object on standard output.

```json
{"relative_path":"scripts/evaluate_combinations.py","input_json":{"deposit":8000,"requirements":{"paper_statements_required":true,"credit_check_required":true,"approximate_credit_score":700,"ranking_mode":"gross_interest"},"savings_products":[...],"credit_cards":[...],"checking_boosts":[...]}}
```

### Input schema

```json
{
  "deposit": 0,
  "requirements": {
    "paper_statements_required": false,
    "credit_check_required": false,
    "approximate_credit_score": null,
    "ranking_mode": "gross_interest"
  },
  "savings_products": [
    {
      "name": "Official Account name",
      "opening_deposit": 0,
      "ongoing_minimum": 0,
      "statement_delivery": "paper_allowed",
      "paper_statement_monthly_fee": 0,
      "tiers": [{"minimum_balance": 0, "apy": 0}],
      "base_apy": 0,
      "confirmed_bonus_apy": 0,
      "below_minimum_monthly_fee": 0,
      "notes": []
    }
  ],
  "credit_cards": [
    {
      "name": "Official card name",
      "minimum_credit_score": 0,
      "credit_check_required": true,
      "other_eligibility_met": true,
      "annual_fee": 0,
      "apy_bonus_by_savings": {"Official Account name": 0}
    }
  ],
  "checking_boosts": [
    {
      "checking_name": "Official checking name",
      "savings_name": "Official Account name",
      "documented_applicable": true,
      "apy_bonus": 0
    }
  ]
}
```

`statement_delivery` must be one of `paper_allowed`, `paperless_required`, or `unknown`. Supply an explicit zero in a card's `apy_bonus_by_savings` only when the terms document that the card has no APY bonus for that account. Omit pairings with unknown bonuses; the script will report them as not compared rather than assume zero. `confirmed_bonus_apy` may contain only confirmed non-card, non-checking bonuses.

### Output interpretation and validation

The output contains `ranked_supported_options`, `excluded_options`, and `uncompared_card_pairings`. Before using `best_option`, verify that:

- each candidate's tier, delivery policy, and balances came from current supplied terms;
- the selected card bonus is documented for the selected account;
- every hard customer requirement was represented in `requirements`; and
- no optional bonus was entered as confirmed without supporting eligibility.

If `best_option` is null, explain the documented blocking constraint and discuss only alternatives whose missing facts can be resolved from available terms. Do not manufacture an offer or transfer solely to avoid giving the available comparison.

## Banking action boundary

Only begin this workflow after the customer explicitly chooses the named account and asks to proceed. Before any banking action, verify identity and authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a savings opening, confirm: verified identity; active checking account; required checking tenure; fewer than the allowed number of savings accounts; no collections or negative balances; product requirements; the exact official savings `account_class`; opening-deposit funding plan; and final consent. Use an account-opening tool only when it is actually available in the runtime and all checks pass. Transfer funds only after explicit authorization of the source account and amount. If funding is deferred, state the documented funding deadline and consequence.

For a card application, distinguish apparent eligibility from approval. Before an application, disclose applicable score and subscription requirements, annual fee, and credit-check consent requirement, then obtain explicit consent. If no supported application tool exists, explain the documented application route; do not imply submission or approval.
