---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking account and, when supportable, one business savings account from supplied product materials. Use when a customer provides banking requirements and wants a focused recommendation rather than a broad comparison. Separately handles a supported recommendation and an unsupported requirement for a paired account.
---

# Business Account Fit Recommendation

## Purpose

Turn a customer's stated business-banking needs into concise, evidence-based recommendations. This Skill is for recommendation and explanation only. Do **not** open, modify, fund, or transfer accounts unless the customer subsequently makes an explicit action request and all applicable prerequisites are verified.

A request for both checking and savings is two related fit decisions. A missing fact for savings must not prevent a fully documented checking recommendation (or vice versa).

## Inputs to inspect

Read the current conversation, supplied product documents and evidence, and read-only observations. Extract and keep separate:

1. **Checking hard constraints**, such as mobile-deposit capacity, APY floor, overdraft-fee maximum, required-balance ceiling, and fee sensitivity.
2. **Savings hard constraints**, such as APY, fee/minimum-balance limits, linked-checking conditions, withdrawal access, sweeps, and transfer speed or rail requirements.
3. **Soft preferences**, which may break a tie only after every hard constraint is documented as met.
4. **Time-sensitive facts**, including the current timestamp and promotion dates.
5. **Unknown customer eligibility facts** and **unknown product facts**.
6. Whether the customer is only seeking a recommendation or is asking to open an account.

Do not use an existing account named by the customer as proof of identity verification, account status, tenure, balance, account count, or eligibility. Do not transfer a term from one account to another account.

## Decision method

1. Translate the customer's language into inclusive, testable constraints.
   - “At least” is an inclusive lower bound.
   - “No overdraft fees” requires a documented overdraft fee of exactly $0.
   - “Cannot keep $X or more at all times” concerns an **ongoing required minimum balance**. It is not violated merely because an account has a fee-waiver threshold below that amount.
   - A request for same-day ACH, or for transfers between checking and savings to be same day, requires documentation for that specific capability and relevant account relationship. A generic transfer feature, a transfer limit, a standard ACH timeline, or same-day ACH documented only for checking is insufficient.
2. Build candidates only from products with documented terms relevant to the customer’s hard constraints.
3. Exclude a candidate that conflicts with any hard constraint. Mark a candidate as unconfirmed, rather than qualifying it, if a required product term or product-specific eligibility condition is unknown.
4. If multiple candidates are confirmed matches, use a currently active promotion only as a tie-breaker among those matches. A promotion never overrides fit or unknown eligibility.
5. Choose exactly one documented-fit product for each requested account type when one exists. Do not manufacture a savings priority that the customer did not provide.
6. If one side has a confirmed match but the other has a missing required feature, give the confirmed recommendation immediately and isolate the unsupported side. Do not make a blanket statement that all account materials are unavailable.

The optional `scripts/evaluate_candidates.py` helper can deterministically filter a normalized candidate list. It is advisory: the executor must accurately extract facts, assess whether an account-specific eligibility rule is known, and provide the customer-facing explanation.

## Required response structure

Use this order, adapting it when only one account type can be recommended:

1. **Direct recommendation(s):** Name one confirmed-fit checking account and, separately, one confirmed-fit savings account only if its fit is fully documented.
2. **Checking fit:** Map every stated checking hard constraint to its documented term. State the daily mobile-deposit limit, overdraft fee, APY, and all material balance/fee terms. If applicable, explicitly distinguish an ongoing minimum balance from a monthly-fee waiver threshold.
3. **Savings result:** If a savings account is confirmed, state its relevant rate, monthly fee, ongoing balance condition, opening-deposit condition if documented, and linked-account condition. If a required savings feature is undocumented, say precisely that no supplied savings product documentation verifies that feature; do not name a savings product as meeting it.
4. **Focused resolution for a gap:** Offer human-agent escalation specifically to verify the unsupported savings requirement when that is the only remaining gap. Keep the documented checking recommendation intact.
5. **Material caveats:** Disclose conditions that matter to the recommendation, including maintenance fees, waiver criteria, mandatory e-statements, and linked-account requirements.
6. **Before opening:** If the customer later asks to proceed, explain that opening eligibility must be verified first. Do not expose internal tool names or signatures.

Keep the response focused; do not provide an exhaustive comparison when the customer asked for one answer. Never say account terms are unavailable if the supplied material documents a product that meets all known hard constraints.

## Final response quality gate

Before sending a recommendation, check all of the following:

- A supported checking recommendation names the selected checking product explicitly.
- The checking explanation repeats all of the customer’s hard checking constraints with their documented values, rather than merely saying the account “fits.”
- A stated fee-waiver threshold is not mislabeled as an ongoing minimum-balance requirement.
- No product is said to support same-day ACH between savings and checking unless supplied savings documentation establishes it.
- If savings support is missing, the response says what is unverified and offers escalation for that issue, while still giving any independently supported checking recommendation.
- No recommendation is made solely because of a promotion, an assumed feature, or an unverified customer eligibility condition.

## Opening-account guardrails

A recommendation is not an account-opening request. If the customer later explicitly requests opening:

- For business checking, verify identity and every supplied prerequisite regarding existing accounts, status, balance, account count, and the customer’s exact official account class before taking action.
- For business savings, verify identity; an eligible OPEN business checking account; savings-account count; no negative balances; and the required qualifying checking-account tenure and balance. A newly recommended checking account does not itself establish these conditions.
- Obtain the exact official account class. Only fund a new account if the customer expressly authorizes it. If a documented deferred-funding deadline applies, communicate it.

## Failure handling

- For conflicting documents on the same product term, do not silently select one value. Seek confirmation unless supplied authoritative evidence resolves the conflict.
- If customer-specific eligibility for a product is unknown, do not use that product as a promotion-driven recommendation.
- Ignore a promotion outside its documented date window.
- If a required feature is not documented, call it unconfirmed; do not infer it from another account or a similarly named product.
- Escalate only the requirement that cannot be verified. Do not abandon independently supported portions of the request.

## Candidate-evaluator interface

`scripts/evaluate_candidates.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "as_of": "optional ISO-8601 timestamp or date",
  "requirements": {
    "numeric_min": {"field_name": 0},
    "numeric_max": {"field_name": 0},
    "equals": {"field_name": "value"},
    "preferences": [{"field": "field_name", "direction": "higher", "weight": 1}]
  },
  "candidates": [
    {
      "id": "stable product identifier",
      "name": "display name",
      "facts": {"field_name": 0},
      "eligibility": "eligible",
      "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    }
  ]
}
```

`eligibility` may be `eligible`, `unknown`, or `ineligible`; omission means `eligible`. Numeric constraints are inclusive. Promotions apply only to confirmed eligible matches and only when `as_of` lies within their inclusive date range.

Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`, with failed and unknown constraints for each result.

Runnable validation input:

```json
{"requirements": {}, "candidates": []}
```

Validate that stdout is JSON, `errors` is empty, and all result lists are empty. For a populated call, validate that every recommended candidate is in `confirmed_matches` with no failed or unknown hard constraint. The executor must still validate the customer-facing disclosure against the final response quality gate above.
