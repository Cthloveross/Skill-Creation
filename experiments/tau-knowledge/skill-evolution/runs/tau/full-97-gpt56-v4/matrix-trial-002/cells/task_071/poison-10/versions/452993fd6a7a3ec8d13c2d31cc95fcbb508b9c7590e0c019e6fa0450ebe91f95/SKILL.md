---
name: business-account-feature-recommendation
description: Recommend a business checking and/or savings product from documented product facts when a customer states feature requirements. Use for informational product matching only; do not use it to open accounts, transfer funds, or make profile changes.
---

# Business Account Feature Recommendation

Use this Skill to give a concise, evidence-based product recommendation when the customer wants one suitable account rather than a broad comparison.

## Scope and safety boundary

This workflow is advisory only. Do not open an account, move money, or imply that an account has been opened. A recommendation is not confirmation that the customer is eligible.

If the customer later asks to open an account or perform another banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient details, and confirmation requirements. Obtain the customer's explicit selection before initiating an account-opening action. Do not reuse this advisory recommendation as action authorization.

## Runtime inputs

Read the current request and the product facts supplied for the current task. Extract only requirements the customer actually stated. Preserve units and comparison operators; for example, “at least $10,000 per day” means a documented daily limit must be `>= 10000`.

For repeatable filtering, run `scripts/select_products.py` with JSON on standard input. It accepts this schema:

```json
{
  "requirements": {
    "checking": {"mobile_deposit_daily_min": "optional decimal"},
    "savings": {"same_day_ach_required": true}
  },
  "as_of": "optional YYYY-MM-DD",
  "checking_candidates": [
    {"name": "documented product name", "mobile_deposit_daily_limit": "decimal", "promotion_rank": "optional integer", "promotion_start": "optional YYYY-MM-DD", "promotion_end": "optional YYYY-MM-DD", "preference_rank": "optional integer"}
  ],
  "savings_candidates": [
    {"name": "documented product name", "same_day_ach": true, "preference_rank": "optional integer"}
  ]
}
```

The script emits JSON with qualifying products, one deterministic selection per requested account type, and validation errors. Use it as a filter, not as evidence: every candidate field must be supported by the current product documentation. A runnable invocation is:

```sh
python3 scripts/select_products.py < runtime_input.json
```

## Method

1. **Identify the decision type.** Confirm that the customer seeks recommendations. If the customer asks to open the recommended product, switch to the applicable account-opening workflow and complete its prerequisites; do not perform an action in this workflow.
2. **Extract requirements.** Separate checking requirements from savings requirements. Do not turn unstated preferences—such as fee tolerance, APY, branch access, or opening balance—into requirements.
3. **Build a documented candidate list.** Use only facts in the supplied materials. For this task family, relevant product facts may be found in `references/product-fact-handling.md`. Exclude a product if a required capability is absent, unknown, or below the required numeric threshold.
4. **Apply promotion priority only when it is active and only among qualifying checking products.** A promotion cannot overcome a missing customer requirement. Use the current task date and the documented promotion dates. Do not claim a promotion applies outside its stated window.
5. **Select one usable match for each requested account type.** The helper prefers an active promotion rank, then an explicit documented preference rank, then supplied candidate order. Candidate order is only a deterministic tie-breaker; it does not prove the chosen product is objectively superior. If several savings products qualify with no documented differentiator, recommend one fit without claiming it is the only or best option, or ask one focused question if a true preference is needed.
6. **State operating conditions that matter.** For same-day ACH, communicate documented conditions such as processing windows, funds availability, review, and recipient-detail checks. Do not guarantee same-day settlement.
7. **Give a direct answer.** Name the recommended checking product and savings product, connect each to the stated requirement, and keep unrelated account features out of the answer. Say that opening can be handled after the customer confirms their choice and eligibility is verified.

## Response structure

Use a brief customer-facing response with:

- a clear checking recommendation and the documented daily mobile-deposit limit or other matching fact;
- a clear savings recommendation and confirmation of documented same-day ACH availability;
- any material same-day ACH qualification caveat;
- a short next-step invitation to confirm the products if the customer wants to proceed with opening, without implying eligibility or taking action.

If no documented product qualifies, say so plainly and identify the unmet requirement. Do not substitute a product with an unknown limit or capability.

## Validation

Before responding, verify that:

- each stated requirement has a corresponding documented matching fact;
- numeric thresholds use the same units and period as the customer’s requirement;
- any promotion was active on the supplied date and was applied only after feature qualification;
- same-day ACH is described as available or targeted, not guaranteed, where documentation contains conditions;
- the response does not claim an account was opened, eligibility was confirmed, or funds were moved.
