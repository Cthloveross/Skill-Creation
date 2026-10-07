---
name: banking-yield-combination-advisor
description: Compare a customer's eligible savings-account and credit-card combinations by estimated one-year deposit interest minus annual card fees, explain qualification assumptions, and safely progress to account opening only after required banking checks and customer authorization.
---

# Banking Yield Combination Advisor

Use this Skill when a customer wants to choose a savings account and/or credit card to maximize estimated deposit yield after annual card fees, possibly followed by opening a savings account. It supports conditional recommendations when credit, account-count, or other eligibility information is unavailable. It does not make credit decisions or assume that an application will be approved.

## Required inputs

Collect or obtain from the current task's approved sources:

- Amount intended for the savings account and intended holding period (default to one year only if the customer asks for a one-year comparison).
- Savings-account terms: APY or APY tiers, opening minimum, ongoing minimum, maintenance fee conditions, and documented bonuses.
- Credit-card terms: annual fee, minimum credit score if stated, subscription requirements, and savings APY bonus for each candidate savings account.
- Rules for stacking card bonuses, checking-account boosts, direct-deposit bonuses, relationship bonuses, or other bonuses.
- Existing checking account types and whether any documented pairing qualifies.
- For any requested opening: verified identity, authority, account ownership, eligibility, available balance, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Use only terms and products supported by the current task's supplied documentation. Treat missing terms, unknown eligibility, and conflicting documentation as unknown rather than inferring them.

## Method

1. **Identify eligible funding amount.** Compare the customer's intended deposit with each account's opening minimum and ongoing minimum. Exclude accounts whose required opening deposit or required ongoing balance cannot be met under the stated plan. If the documents only say benefits require an ongoing minimum, clearly distinguish an account that can be opened from one that can retain the advertised benefits.
2. **Identify applicable bonuses.** For each savings/card candidate, retain only bonuses documented for that savings product and linked under the same customer profile. Card bonuses do not stack with other card bonuses: use only the highest applicable active card bonus. Apply a checking boost only when the exact checking-and-savings pairing is documented. If several qualifying checking boosts exist, retain only the highest. Add only other bonuses explicitly documented as stackable and whose conditions are known to be met.
3. **Calculate consistently.** Use `scripts/compare_yield.py` for deterministic comparisons. For a one-year APY estimate, annual interest is `deposit × effective_apy / 100`; net value is annual interest minus the first-year card annual fee. This is an estimate based on a constant balance and APY, not a promise of actual interest. Do not mix APR with APY or count purchase rewards as savings interest unless the customer requests that separate analysis.
4. **Apply eligibility status.** A combination may be marked:
   - `eligible`: every supplied requirement is confirmed met;
   - `conditional`: one or more requirements are unknown but no known requirement fails;
   - `ineligible`: a known requirement fails.
   Rank eligible options first. If none are eligible, present the highest conditional option as an assumption-based scenario, name every unresolved requirement, and do not describe it as approved or available.
5. **Explain material differences.** Show the effective APY, estimated annual interest, annual fee, net one-year estimate, qualification requirements, and reasons alternatives are excluded. If differences are small, state the dollar comparison precisely using the supplied assumptions.
6. **Safely progress to opening only when permitted.** A customer request to proceed is authorization in principle, not a substitute for required checks. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Do not open an account or submit a credit-card application where any prerequisite is unknown or fails.

## Savings-opening workflow

Use this only when the current task documentation authorizes the relevant account-opening tool and all conditions are confirmed.

1. Verify the customer identity according to the available verification procedure and record it when the runtime provides a verification logging tool.
2. Confirm an active checking account, required checking tenure, fewer than the maximum allowed personal savings accounts, no collections or negative balances, and all account-specific opening requirements.
3. Confirm the exact official savings `account_class`, the opening deposit source and amount, all material terms, and the customer's authorization to open.
4. Call the documented bank-account-opening tool with the authenticated user ID, `account_type: "savings"`, and the exact official account class. Never ask the customer to invoke an internal tool.
5. If the customer authorizes an immediate opening deposit, verify source-account ownership, available balance, fees, limits, cutoffs, and destination account ID before calling the documented transfer tool. If funding is deferred, state the documented funding deadline and consequence.
6. Confirm the result and funding status. For a credit card, follow only a separately documented application workflow; never represent a recommendation as an approval.

If required data cannot be retrieved through allowed tools, ask the customer for it or provide a conditional comparison. Do not fabricate account counts, credit scores, balances, eligibility, product availability, or tool results.

## Calculator interface

Run `scripts/compare_yield.py` with JSON on standard input. It emits a JSON report on standard output.

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
      "annual_card_fee": 0,
      "other_apy_bonus": 0,
      "eligibility": {"requirement": "met|unknown|failed"},
      "notes": ["optional documented qualification note"]
    }
  ]
}
```

APY fields are percentage points (for example, `6.25`, not `0.0625`). `maintenance_fee_annual` must be the expected annual fee under the stated balance assumptions; use zero only where documentation supports it. Eligibility keys should describe every relevant prerequisite, such as a credit threshold, subscription, same-profile linkage, account-count limit, or checking requirement.

Example execution by the executor:

```sh
python3 scripts/compare_yield.py < comparison-input.json
```

Validate the result before using it: `deposit` and all money values must be nonnegative; APY components must be numeric; every option must include a savings account and base APY; the effective APY must equal the base plus the accepted bonus fields; `net_estimated_value` must equal estimated interest less stated fees. Review the returned `status` and `unresolved_requirements` before recommending or taking any action.
