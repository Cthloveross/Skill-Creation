---
name: banking-yield-combination-advisor
description: Compare documented savings-account and credit-card combinations for a customer's stated deposit and term, estimate deposit interest less annual card fees, give assumption-based recommendations when eligibility is unresolved, and prevent banking actions until every required prerequisite is verified.
---

# Banking Yield Combination Advisor

Use this Skill when a customer asks which savings account, credit card, or documented combination best maximizes one-year (or other stated-term) deposit value after annual card fees. It is appropriate both for an informational comparison and for a customer who may later want to open products.

A recommendation is not a credit decision, account approval, or authorization to act. Use only product terms and tools supplied for the current task.

## Required information

Gather from approved current-task documents, observations, and customer statements:

- Intended savings balance and comparison period.
- Savings APY, tier conditions, opening and ongoing balance requirements, maintenance fees, withdrawal limits, and documented bonuses.
- Candidate card annual fees, score/subscription requirements, and savings APY bonuses.
- Applicable bonus stacking and exact checking/savings pairing rules.
- Known facts and unknowns for account-opening and card-application eligibility.

Do not infer an undocumented APY, fee, pairing boost, account count, credit score, approval, balance, or tool result. If documents conflict, call out the conflict and avoid a definitive ranking until it is resolved.

## Comparison procedure

1. **Screen each savings product.** Compare the planned deposit against documented opening and ongoing minimums. Distinguish inability to open an account from inability to retain its advertised benefits.
2. **Determine documented bonuses.** Include a card bonus only when it is documented for that particular savings product and the relevant linkage condition can be met. Apply exact checking-pairing boosts only when the customer has a documented qualifying pairing. Never invent a boost for an unlisted pairing.
3. **Apply stacking rules.** If card bonuses do not stack, include only the highest applicable card bonus, not the sum of cards. Add other bonus categories only if their documentation explicitly permits stacking and their conditions are satisfied or clearly labeled as assumptions.
4. **Calculate each option.** Use `scripts/compare_yield.py`. For a constant one-year balance, estimated interest is `deposit × effective APY / 100`. Net estimated value is estimated interest less documented annual card and assumed maintenance fees. This is an APY-based estimate, not guaranteed interest, and does not include card purchase rewards, APR costs, taxes, balance changes, or undisclosed fees.
5. **Classify eligibility.**
   - `eligible`: all relevant supplied requirements are confirmed met.
   - `conditional`: no known requirement fails, but one or more material requirements remain unknown.
   - `ineligible`: a known requirement fails, including a balance requirement that the plan cannot meet.
6. **Rank and explain.** Rank eligible options first, then conditional options, then ineligible options. If no option is confirmed eligible and the customer asks what is best *assuming* requirements are met, provide the highest documented conditional option rather than refusing or transferring solely because verification is incomplete.

## Mandatory response content

For the leading option, state plainly:

- the official savings and card names;
- base APY, each included bonus, and effective APY;
- estimated interest and net one-period value on the customer's stated balance;
- annual card fee and any assumed maintenance fee;
- whether the planned balance satisfies the documented balance requirement;
- whether the documented withdrawal limit fits the customer's stated activity;
- whether the customer's existing checking account receives a documented pairing boost or does not have a documented qualifying pairing;
- every unresolved or failed eligibility prerequisite; and
- an explicit status such as **conditional**, **assuming the requirements are met**, or **not yet verified**.

Use transparent language such as: “Assuming you meet the remaining eligibility requirements, the leading documented combination is …” Do not describe a conditional option as approved, confirmed eligible, or already opened.

When material customer information is unavailable, answer the requested assumption-based comparison first. Then identify exactly what must be confirmed before any application or account opening can proceed. Do not transfer merely because a conditional comparison is possible from available documentation.

## Safe handling of openings and applications

A request to proceed after a recommendation is authorization in principle only. Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a savings opening, also confirm every documented opening prerequisite, including the active checking-account requirement and tenure, permitted personal-savings-account count, account standing, exact official account class, and opening-deposit arrangement. For a card, use only a separately documented application workflow and do not submit an application until its prerequisites and required consent are confirmed.

If a score threshold, savings-account count, identity verification, account status, required subscription, funding details, or any other mandatory condition is unknown or fails:

- do not open an account;
- do not submit a card application;
- do not transfer funds or arrange funding; and
- provide the conditional comparison and explain the missing confirmation instead.

Use normal banking tools only when the applicable documentation authorizes them. Never ask the customer to invoke internal agent tools.

## Calculator interface

Run `scripts/compare_yield.py` with one JSON object on standard input. It writes one JSON report to standard output.

Input schema:

```json
{
  "deposit": 30000,
  "term_years": 1,
  "options": [
    {
      "savings_account": "Official savings account name",
      "base_apy": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "maintenance_fee_annual": 0,
      "card": "Official card name or null",
      "card_apy_bonus": 0,
      "other_apy_bonus": 0,
      "annual_card_fee": 0,
      "eligibility": {
        "minimum credit score": "met|unknown|failed",
        "savings-account count": "met|unknown|failed"
      },
      "notes": ["Documented facts or stated assumptions"]
    }
  ]
}
```

All APY inputs are percentage points, so `6.35` means 6.35%, not 0.0635. Include each material prerequisite in `eligibility`; the helper additionally marks an option ineligible when the planned deposit is below its opening or ongoing minimum.

Example executor call:

```sh
python3 scripts/compare_yield.py < comparison-input.json
```

Before relying on the output, verify that the input uses documented terms, all monetary values are nonnegative, bonuses obey the relevant stacking policy, and `effective_apy` equals the included APY components. Read `status`, `unresolved_requirements`, and `failed_requirements` aloud in the customer-facing conclusion where relevant.
