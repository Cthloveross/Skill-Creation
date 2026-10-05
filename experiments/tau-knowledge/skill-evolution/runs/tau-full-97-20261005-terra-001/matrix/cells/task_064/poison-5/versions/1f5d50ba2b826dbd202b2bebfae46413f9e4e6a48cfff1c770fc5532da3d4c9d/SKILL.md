---
name: banking-yield-combination-advisor
description: Compare documented savings-account and credit-card combinations for a stated deposit and term, calculate APY-based interest less documented annual fees, give conditional advice when eligibility is unresolved, and prevent openings, applications, or funding until all banking prerequisites are verified.
---

# Banking Yield Combination Advisor

Use this Skill when a customer asks which savings account, credit card, or savings-and-card combination provides the best documented deposit yield after annual card fees. It supports an informational recommendation and a later request to open products, but an informational recommendation is never approval or authority to act.

Use only the current task's supplied product documents, authorized observations, and customer statements. Do not invent product terms, eligibility, account facts, approval outcomes, bonuses, or tool results.

## Separate facts from assumptions

Classify each statement used in a comparison as one of:

- **Documented term**: rate, fee, withdrawal limit, balance condition, pairing, or requirement in current product documentation.
- **Verified/customer-confirmed fact**: an authorized observation or an explicit customer statement.
- **Unknown requirement**: a condition needed for an opening, application, or bonus that has not been confirmed.
- **Assumption**: a condition the customer asks to assume for comparison purposes.

An assumption permits a **conditional recommendation only**. It never establishes eligibility and never permits a banking action.

## Compare candidates

1. Identify candidate savings accounts that can accommodate the stated deposit, anticipated withdrawal frequency, and term. Distinguish an opening minimum from an ongoing minimum.
2. For each account, identify its documented base APY and only bonuses expressly documented for that account.
3. Include a card bonus only if the documentation supports the required account/card linkage or same-profile condition. Apply stated stacking rules; where card bonuses do not stack, use only the highest applicable bonus.
4. Include a checking boost only for an exact documented checking-and-savings pairing. If the customer's checking account is absent from the qualifying-pairing list, state that there is **no documented linked-checking boost**; do not infer one.
5. Deduct annual card fees and only maintenance fees that are expected under the stated balance assumptions. Do not offset deposit interest with purchase rewards, card APR, taxes, or undocumented charges unless the customer specifically requests a separately supportable analysis.
6. For a constant-balance APY estimate, calculate:

   `effective APY = base APY + applicable documented bonuses`

   `estimated interest = deposit × effective APY / 100 × term in years`

   `estimated net value = estimated interest − annual card fees − expected maintenance fees`

   APY already represents the account's stated annualized yield; describe this as an APY-based constant-balance estimate rather than recomputing a different compounding result.
7. Label every candidate:
   - **eligible** only when every relevant prerequisite is confirmed met;
   - **conditional** when none is known to fail but one or more material requirements are unknown or assumed;
   - **ineligible** when a requirement is known to fail.

Rank eligible choices before conditional choices, then ineligible choices. Within a status class, rank by estimated net value.

## Mandatory response gate

When the customer asks for the best option **assuming** unknown requirements are met, provide the documented conditional comparison in the same response. Do not refuse, claim the documentation is unavailable, or transfer solely because final eligibility cannot be verified.

Before responding, ensure the response explicitly includes all applicable items:

1. The recommended savings account and card by name.
2. The base APY, every included bonus, and effective-APY arithmetic.
3. The estimated interest and net value for the stated deposit and term, including the annual card fee and any fee assumption.
4. Whether the deposit meets the opening and ongoing balance requirements.
5. Whether the withdrawal limit accommodates the customer's stated monthly withdrawals.
6. Whether the current checking account has an exact documented pairing boost or no documented pairing boost.
7. A plain conditional label, such as: “Assuming the remaining requirements are met, the leading documented combination is …”
8. Every material unresolved or failed prerequisite for the leading choice, including credit-score, subscription, identity, active-checking, checking-tenure, account-standing, and personal-savings-account-count requirements where documented.
9. A statement that no savings account has been opened, no credit-card application submitted, and no funds transferred.

Use `scripts/render_recommendation.py` after selecting a documented leading option when a structured output would help ensure all response obligations are present. The executor must still verify that all script inputs accurately reflect the supplied documents and observations.

## Required handling of unresolved eligibility

If a required credit score is unknown, say the card recommendation is conditional on meeting its documented minimum score. If opening a savings account requires a customer to hold fewer than a stated number of personal savings accounts and that count is unknown, explicitly say that the unverified **savings-account count** prevents confirmation of opening eligibility. Include other unverified opening prerequisites individually; do not imply they are met merely because the customer asked for an assumption-based comparison.

A customer’s request to proceed if the recommendation is suitable is only prospective authorization. It does not cure an unknown condition and does not authorize an application, account opening, or transfer.

## Safety boundary for banking actions

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Before opening a savings account, verify all documented opening conditions, including identity, active checking account and any tenure requirement, personal-savings-account count, account standing, exact selected official account class, and funding arrangement. Before submitting a credit-card application, verify all documented card requirements and obtain any required consent.

If any mandatory condition is unknown or fails:

- do not open an account;
- do not submit a credit-card application;
- do not transfer or arrange funds; and
- provide the informational conditional comparison and identify the missing requirements.

Use normal banking tools only when the applicable documented workflow authorizes the action. Never ask a customer to invoke an internal agent tool.

## Calculation helper

Run `scripts/compare_yield.py` with one JSON object on standard input. It emits one JSON object on standard output.

Input schema:

```json
{
  "deposit": 0,
  "term_years": 1,
  "options": [
    {
      "savings_account": "official savings name",
      "card": "official card name or null",
      "base_apy": 0,
      "card_apy_bonus": 0,
      "other_apy_bonus": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "annual_card_fee": 0,
      "maintenance_fee_annual": 0,
      "eligibility": {"requirement": "met|unknown|failed"},
      "notes": ["documented term or stated assumption"]
    }
  ]
}
```

All APY fields are percentage points: `4.5` means 4.5%, not 0.045. The helper adds failed balance conditions if the planned deposit is below a supplied minimum. Validate that all numeric inputs are documented and that stacking was resolved before calling it.

Example:

```sh
python3 scripts/compare_yield.py < comparison-input.json
```

## Response-rendering helper

`scripts/render_recommendation.py` converts verified, structured comparison facts into a customer-facing conditional recommendation. It reads one JSON object from stdin and emits `{"message":"..."}`. It intentionally does not open accounts, apply for cards, or call banking tools.

Required input fields are `savings_account`, `card`, `deposit`, `term_years`, `base_apy`, `card_apy_bonus`, `other_apy_bonus`, `annual_card_fee`, `opening_minimum`, `ongoing_minimum`, `monthly_withdrawal_limit`, `planned_monthly_withdrawals`, `checking_pairing_status`, and `unresolved_requirements`. `checking_pairing_status` must be either `"qualifying documented boost"` or `"no documented pairing boost"`.

Example:

```sh
python3 scripts/render_recommendation.py < recommendation-input.json
```

Validate the rendered message against the mandatory response gate, especially that unknown requirements remain conditional and that it states no action has been taken.
