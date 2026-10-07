---
name: constrained-savings-card-comparison
version: 1.3.0
description: Compare documented savings-account and credit-card combinations against a customer's deposit, statement-delivery, credit-profile, credit-inquiry, and known-fee requirements; calculate supported one-year results and safely handle any later opening, funding, application, or human-handoff request.
---

# Constrained Savings and Credit-Card Comparison

Use this Skill when a customer wants to choose a savings account and credit card to maximize savings interest or net known first-year value, especially where they specify a deposit amount, physical statements, an approximate credit score, a real credit inquiry, or an existing checking account.

A product comparison is informational. It is not an account opening, a funding transfer, or a credit-card application. Once the supplied product terms support a comparison, provide it directly; do **not** substitute a human transfer for the comparison.

## Information required

Collect or identify, without requesting facts already supplied:

- intended deposit, time horizon, and ranking objective;
- hard requirements, including paper/mailed statements;
- approximate credit score and any requested credit-check or credit-pull preference;
- existing checking account and any claimed relationship status;
- savings-account opening deposit, ongoing minimum, statement policy, statement fee, APY tiers, thresholds, and applicable fees;
- card score minimum, required credit inquiry, annual fee, additional eligibility requirements, and savings-account-specific APY bonus; and
- documented linked-checking and optional direct-deposit or relationship bonuses.

If a material fact is absent, say it is undocumented rather than assuming a favorable rate, fee, bonus, statement option, or eligibility result.

## Comparison method

1. **Apply hard filters first.** Exclude an account that requires paperless statements if physical statements are mandatory. Exclude an account when the planned balance cannot meet its documented opening or ongoing requirements. Exclude a card when its disclosed score minimum exceeds the stated approximate score, a known required subscription is absent, or it is not documented to use the requested credit check.
2. **Choose the applicable APY tier.** Select the highest documented tier whose minimum balance does not exceed the planned deposit.
3. **Apply only documented bonuses.** A card bonus must be documented for the selected savings account. Credit-card APY bonuses do not stack; use only the highest applicable eligible card bonus. Add a checking boost only when the customer's exact checking/savings pair is listed and its amount is documented. Do not apply optional direct-deposit or relationship bonuses unless eligibility is confirmed.
4. **Calculate transparently.** Since APY is an annual yield, estimate one-year interest as `deposit × effective APY / 100`. For a net-known-fee comparison, subtract only documented annual card fees and documented account or statement fees that apply to the stated plan. Clearly label the result as an estimate.
5. **Treat card fit as preliminary.** Meeting a disclosed score minimum is apparent eligibility only. Approval remains subject to underwriting. A preference for a credit check is not consent to submit an application.
6. **Name material exclusions.** Explain attractive alternatives that fail a hard requirement, such as paperless-only accounts, cards above the stated score range, accounts whose ongoing balance is unaffordable, or products without a documented credit pull.

Use `scripts/evaluate_combinations.py` for repeated filtering and arithmetic after transcribing only documented facts. Its result is advisory and must be checked against the supplied product terms.

## Required customer-facing response

When the available terms are sufficient, respond in this order:

1. **Recommendation:** name the official savings account and eligible credit card. If cards tie on the requested savings-yield and known-fee measure, disclose every tied option. A response may lead with one selected tied card only when it does not claim that it earns more than the other.
2. **Calculation:** state the selected tier and show `base/tier APY + documented card bonus + confirmed bonuses = effective APY`, followed by the approximate one-year interest on the stated deposit. State which optional bonuses were excluded because they were not confirmed.
3. **Fit:** confirm physical-statement availability and its documented fee; state the card's score minimum, credit-check/credit-pull consent requirement, annual fee, and underwriting caveat.
4. **Exclusions:** identify material alternatives and their documented conflicts.
5. **Account constraints and next step:** give the recommended account's opening-deposit and ongoing-balance requirements. Ask for an explicit product selection and explicit consent before beginning any account opening, funding, or card application.

Also state whether the customer's exact existing checking account has a documented linked-checking APY boost for the recommended savings account. An unlisted pairing receives no boost.

## Calculator

The calculator reads one JSON object from standard input and writes one JSON object to standard output.

```json
{
  "deposit": 8000,
  "requirements": {
    "paper_statements_required": true,
    "credit_check_required": true,
    "approximate_credit_score": 700,
    "ranking_mode": "net_known_fees"
  },
  "savings_products": [
    {
      "name": "Official Account Name",
      "opening_deposit": 0,
      "ongoing_minimum": 0,
      "statement_delivery": "paper_allowed",
      "paper_statement_monthly_fee": 0,
      "tiers": [{"minimum_balance": 0, "apy": 0}],
      "confirmed_bonus_apy": 0
    }
  ],
  "credit_cards": [
    {
      "name": "Official Card Name",
      "minimum_credit_score": 0,
      "credit_check_required": true,
      "other_eligibility_met": true,
      "annual_fee": 0,
      "apy_bonus_by_savings": {"Official Account Name": 0}
    }
  ],
  "checking_boosts": [
    {
      "checking_name": "Official Checking Name",
      "savings_name": "Official Account Name",
      "documented_applicable": true,
      "apy_bonus": 0
    }
  ]
}
```

`statement_delivery` must be `paper_allowed`, `paperless_required`, or `unknown`. Do not provide a zero fee, an eligibility flag, or a bonus unless that value is documented. `other_eligibility_met` represents checked non-score card requirements; use `false` when a known requirement is unmet. Omit a card's savings mapping when no account-specific bonus is documented.

Review `ranked_supported_options`, `tied_best_options`, `excluded_options`, and `uncompared_card_pairings` before drafting the response. The first ranked item is not uniquely best if `tied_best_options` contains multiple entries.

## Banking-action boundary

Only begin an opening, funding, or card-application workflow after the customer explicitly selects the named product and asks to proceed. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a personal savings opening, verify identity, active checking status and tenure, savings-account-count limit, account standing, selected official account class, opening-funding plan, and final consent. Use an opening tool only when it is actually available and all documented checks pass. Transfer funds only after explicit authorization of the source account and amount. If funding is deferred, explain the documented funding deadline and consequence.

For a credit-card application, disclose score and subscription requirements, annual fee, and credit-check consent requirement. Obtain explicit consent to submit. Do not imply an application was submitted, approved, or assigned a credit limit unless an observable supported action result establishes it.

## Requested operational handoff

If, after receiving the comparison, the customer explicitly asks for a human agent to perform an operational step that cannot be completed with available supported tools, a human handoff may follow the comparison. Do not use a handoff to avoid giving the comparison.

Before transfer, preserve the customer's instructions in the handoff summary. Include:

- the selected official savings account and, if applicable, selected card;
- the requested opening action;
- the authorized funding amount;
- the customer-named checking source account (for example, the stated checking account) when they authorized that source; and
- that ownership, available funds, eligibility, account-status, and final transfer prerequisites still require verification.

Do not invent an account identifier, claim the opening or transfer completed, or describe a stated checking account as verified merely because the customer named it. Use a customer-requested-human reason when that is the applicable supported transfer reason, and report the handoff only after an observable successful transfer result.
