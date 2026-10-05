---
name: banking-yield-combination-advisor
description: Compare documented savings-account and credit-card combinations for a stated balance and term, calculate estimated deposit interest less annual card fees, provide a clearly conditional recommendation when eligibility is unresolved, and prevent banking actions until all prerequisites are verified.
---

# Banking Yield Combination Advisor

Use this Skill for a customer seeking the best documented savings account, credit card, or account-card combination for deposit yield net of annual card fees. It supports informational comparisons and customers who may later ask to open products.

A recommendation is not an approval, credit decision, account opening, application, or authorization to move money. Use only current-task product documentation, supplied observations, and customer statements.

## Collect and distinguish facts

Collect the stated deposit, intended term, expected withdrawals, current linked products, and customer priorities. From current documentation, identify:

- Savings APY, tiers, opening and ongoing balance requirements, maintenance fees, and withdrawal limits.
- Card annual fees, card eligibility requirements, and account-specific APY bonuses.
- Linkage requirements, stacking policies, and qualifying checking/savings pairings.
- Savings-opening and card-application prerequisites.

Keep these categories separate:

- **Documented product term:** a rate, fee, limit, or requirement stated in the supplied documents.
- **Customer-confirmed fact:** information explicitly supplied by the customer or verified through an authorized observation.
- **Unknown requirement:** a required fact not confirmed by either source.
- **Assumption:** a condition the customer asks to assume; it permits a conditional comparison only, never an action.

Never invent a rate, bonus, account count, score, approval, pairing boost, balance, or tool result. An unlisted checking/savings pairing must not be treated as qualifying. If documents genuinely conflict on a material term, disclose the conflict and do not make a definitive ranking based on it.

## Comparison method

1. Screen each candidate against the planned balance. State separately whether it meets an opening minimum and whether it meets an ongoing balance requirement.
2. Add only bonuses documented for that particular savings product. Include a linked-card bonus only under its stated same-profile or linkage conditions.
3. Apply stacking rules exactly. If cards do not stack, use only the highest applicable card bonus. Add checking or relationship bonuses only where the exact documented pairing and terms support them.
4. Calculate a constant-balance estimate with `scripts/compare_yield.py`. For a one-year comparison, estimated interest is `balance × effective_apy / 100`; deduct documented annual card fees and only maintenance fees that are actually expected under the stated assumptions.
5. Label each option:
   - **eligible**: every relevant requirement is confirmed met;
   - **conditional**: no requirement is known to fail, but a material condition is unknown or explicitly assumed;
   - **ineligible**: a known requirement fails.
6. Rank eligible options before conditional options before ineligible options. Within a class, rank by estimated net value.

The estimate is APY-based and assumes the stated balance remains constant. It does not include taxes, purchase rewards, card interest, balance changes, undisclosed charges, or benefits not requested by the customer.

## Required customer-facing conclusion

When the customer asks which option is best **assuming** unresolved requirements can be met, answer the conditional comparison in the same response. Do not withhold the recommendation or transfer merely because final eligibility cannot yet be verified.

Before sending, make sure the conclusion contains all applicable items below:

1. The leading savings-account and card names.
2. The base APY, each included bonus, and effective APY arithmetic.
3. Estimated interest and net value for the requested term and balance, including the annual card fee and any maintenance-fee assumption.
4. Whether the proposed balance meets the documented opening and ongoing balance requirements.
5. Whether the documented withdrawal limit accommodates the customer's stated withdrawal frequency.
6. Whether the existing checking account has an exact documented qualifying pairing or no documented pairing boost.
7. The recommendation's status: **conditional**, **assuming requirements are met**, or **not yet verified**.
8. Every unresolved or failed opening/application prerequisite relevant to the leading option, including score, account-count, subscription, identity, account standing, checking tenure, or other documented conditions.
9. A clear statement that no account is being opened, card application submitted, or funds transferred yet.

Use direct language such as: “Assuming the remaining requirements are met, the leading documented combination is …” Do not characterize a conditional result as approved, eligible, available to the customer, or already opened.

If no choice is confirmed eligible, still provide the best documented conditional choice when the customer requested an assumption-based answer. Explain precisely what verification remains necessary. Do not make a transfer to a human agent solely because a comparison can be completed from the available documents.

## Safety boundary for openings, applications, and funding

A customer saying they would like to proceed later is only authorization in principle. Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Before opening a savings account, verify every documented opening condition, including identity, active checking account and required tenure, personal-savings-account count, account standing, exact selected official account class, and funding arrangement. Before submitting a card application, verify every documented card prerequisite and obtain any required consent under the documented workflow.

If any mandatory condition is unknown or fails, including score eligibility, savings-account count, identity verification, standing, subscription, or funding details:

- do not open an account;
- do not submit a card application;
- do not transfer or arrange funds; and
- give the informational conditional comparison and the missing requirements instead.

Use normal banking tools only when the applicable workflow authorizes the action. Never ask a customer to invoke an internal agent tool.

## Calculator

Run `scripts/compare_yield.py` by sending one JSON object on standard input; it returns one JSON object on standard output. The helper performs deterministic arithmetic and status labeling. The executor remains responsible for supplying only documented product terms and for explaining the result to the customer.

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
      "eligibility": {
        "requirement name": "met|unknown|failed"
      },
      "notes": ["documented term or explicit assumption"]
    }
  ]
}
```

APY fields are percentage points: for example, `4.5` represents 4.5%, not 0.045. The helper automatically adds failed balance requirements when the planned deposit is below an opening or ongoing minimum.

Example call:

```sh
python3 scripts/compare_yield.py < comparison-input.json
```

Validate the result before use: confirm all numeric inputs are documented, that bonus stacking has already been resolved, that `effective_apy` equals the included components, and that every material prerequisite appears in `eligibility`. Include the resulting status, unresolved requirements, and failed requirements in the customer-facing conclusion.
