---
name: savings-card-net-yield-advisor
description: Compare documented savings-account and credit-card combinations for a customer seeking to maximize one-year savings interest less annual card fees. Use for evidence-based, read-only recommendations, conditional credit eligibility, APY-bonus stacking, balance and withdrawal-limit fit, and safe next steps if the customer later elects to open products.
---

# Savings and Card Net-Yield Advisor

Use this Skill to give a substantive, document-based recommendation when a customer wants a savings account and optionally a credit card that raises savings APY. This Skill provides analysis only. It does not open accounts, submit credit applications, transfer funds, or modify customer data.

## Core rule: use the supplied evidence

Use the current task's product documents, evidence summary, clarifications, and read-only observations as the source of truth. Do not state that terms are unavailable, transfer the customer, or defer the comparison when the supplied materials document enough terms to answer it.

A recommendation can be useful even when a requirement is unknown. In that case, identify the best path **conditionally**, state the exact unmet or unverified prerequisite, and provide a supported no-card or otherwise eligible fallback where possible. Do not infer credit approval, a credit score, account linkage, an annual-fee waiver, balance, or account-opening eligibility.

## Inputs and fact extraction

From the current task materials, extract only supported facts:

- Customer objective and comparison period.
- Planned opening balance, expected maintained balance, and whether withdrawals will be replenished.
- Expected withdrawals per month.
- Savings opening minimum, ongoing minimum, APY or applicable APY tier, withdrawal limit, maintenance fee conditions, compounding method, and any documented savings fee.
- Card annual fee, card eligibility requirements, application/underwriting conditions, and the card's APY bonus for the particular savings account.
- Whether the customer has a documented qualifying subscription, existing eligible card, or documented linked checking boost.
- Every requirement that remains unknown.

Treat a stated balance as a modeling assumption, not proof that funds are available for an actual transfer. A customer lookup or profile match is not, by itself, completed identity verification.

## Recommendation method

1. **Set the scope.** State that the calculation compares projected savings interest less documented annual card fees. Do not include cash back, sign-up bonuses, transaction fees, maintenance fees, excess-withdrawal fees, or interest on carried card balances unless their applicability and amount are documented for the customer.
2. **Screen the savings account.** Check the planned balance against both the opening and ongoing minimum, and compare expected monthly withdrawals with the documented cap. A balance that stays above the minimum and a withdrawal count at or below the cap fit those constraints. If the source explicitly defines `-1` as unlimited, it may be treated as unlimited; otherwise do not make that inference.
3. **Build APY components.** Use the applicable base APY, plus only bonuses supported by the documents. A card bonus requires the relevant card and savings account under the same customer profile when documentation says so.
4. **Apply stacking rules.** Credit-card APY bonuses do not stack with each other: use only the highest applicable card bonus. Likewise use only the highest qualifying checking boost when multiple checking boosts exist. Add different bonus types only when the documentation explicitly permits stacking.
5. **Classify eligibility.** Mark a result `eligible` only when all material requirements are known satisfied. Mark it `conditional` when a material requirement is unknown but could be met. Mark it `ineligible` when a known requirement fails. Approval/underwriting is never certain merely because a published minimum is met.
6. **Calculate results.** Run `scripts/compare_net_yield.py` using terms extracted from the current materials. Include a no-card option for a selected savings account whenever it is useful as a fallback. Supply annual fees explicitly, including zero where documented.
7. **Give the decision first.** Lead with the highest net eligible result, or, if the highest result is conditional, say so plainly and present it as the conditional recommendation. Do not bury a material condition after the conclusion.
8. **Explain operating fit.** Explicitly state the ongoing minimum and whether the modeled balance is above it. Explicitly state the monthly withdrawal cap and whether the planned number of withdrawals fits within it. State that the interest estimate assumes the described balance remains near the modeled level if withdrawals are replenished.
9. **State next steps without acting.** Ask for the customer's selection before any opening or application. For a conditional card, explain what must be confirmed or completed (for example, the required score and underwriting) without promising approval.

## Required response checklist

Before sending a recommendation, verify that the visible customer-facing response contains all applicable items below:

- Official savings-account and card names for the recommended combination.
- Base APY, applicable card APY bonus, and the arithmetic for the combined effective APY.
- Projected one-year gross interest, documented annual fee, and net result.
- A clear statement that estimates exclude fees or costs whose applicability is not established.
- Each known satisfied prerequisite relevant to the recommendation.
- Each unknown eligibility requirement, phrased conditionally; never imply approval is guaranteed.
- Ongoing balance minimum and a direct comparison to the customer's expected balance.
- Withdrawal limit and a direct comparison to the customer's expected withdrawals.
- The stable/replenished-balance assumption where applicable.
- A supported fallback when the leading option is conditional.
- A request for a product selection and any remaining prerequisite checks before taking action.

Use plain language such as: “If you meet the documented credit-score threshold and are approved, the combination is …” Do not use vague phrases such as “you should qualify” when material eligibility data is unknown.

## Calculation conventions

- Treat stated APY as an effective annual yield. For `d` modeled days, use: `(1 + APY / 100)^(d / 365)`.
- For 12 months and a stable balance, gross interest is approximately principal times the effective APY, subject to rounding.
- The model assumes the supplied balance stays eligible throughout the comparison. If withdrawals materially reduce the balance and no dated balance schedule is available, do not present a precise stable-balance projection.
- Subtract only documented annual fees that are known applicable. Do not assume a conditional promotion or waiver applies.
- Never add APY bonuses from more than one card. The helper evaluates each card alternative separately.

## Script interface

Run `scripts/compare_net_yield.py` with one JSON object on stdin. It emits a JSON object on stdout and performs no retrieval or banking action.

Input schema:

```json
{
  "balance": 0,
  "months": 12,
  "withdrawals_per_month": 0,
  "options": [
    {
      "savings_name": "official savings account name",
      "base_apy_pct": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "withdrawal_limit": null,
      "checking_boost_pct": 0,
      "relationship_bonus_pct": 0,
      "savings_annual_fee": 0,
      "savings_eligibility": "eligible",
      "cards": [
        {
          "card_name": "official card name or no-card option",
          "bonus_apy_pct": 0,
          "annual_fee": 0,
          "eligibility": "eligible"
        }
      ]
    }
  ]
}
```

All amounts and percentages are JSON numbers. `withdrawal_limit` is an integer, `-1` only if the supplied source expressly defines it as unlimited, or `null` when no limit is documented. Eligibility fields must be `eligible`, `conditional`, `unknown`, or `ineligible`.

Output includes ranked results, `best_eligible`, `best_conditional`, calculation assumptions, and warnings. Confirm that the selected result has the intended status and that warnings are addressed in the prose. The helper rejects malformed numeric fields and unsupported eligibility values; it never invents eligibility or undocumented boosts.

Example runtime invocation pattern (with facts extracted from the current request, not preset values):

```sh
python3 scripts/compare_net_yield.py <<'JSON'
{"balance": BALANCE, "months": 12, "withdrawals_per_month": WITHDRAWALS, "options": OPTIONS}
JSON
```

## Banking actions: only after a separate request

Before describing or performing any banking action, preserve and satisfy this control verbatim:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a personal savings opening, confirm all documented prerequisites before acting: verified customer identity, at least one active checking account, fewer than five personal savings accounts, no collections or negative balances, and required checking-account tenure. Confirm the exact official savings `account_class` selected by the customer.

Only after those checks and explicit customer selection may the execution agent use its normal banking tools to open the selected savings account. If the customer separately authorizes immediate funding, verify source account ownership, available balance, amount, fees, limits, cutoff, destination, and transfer confirmation requirements before using a normal transfer tool. If funding is deferred, communicate the documented deadline and consequence. Do not submit a credit-card application unless a supplied authorized workflow permits it and the customer has explicitly asked to proceed.
