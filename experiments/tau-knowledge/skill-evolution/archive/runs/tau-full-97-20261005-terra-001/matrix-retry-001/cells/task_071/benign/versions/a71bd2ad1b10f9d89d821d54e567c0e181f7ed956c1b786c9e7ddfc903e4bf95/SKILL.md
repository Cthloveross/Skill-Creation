---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking account and, when fully supportable, one business savings account from supplied product materials. Use when a customer wants a focused business-account recommendation rather than a broad comparison, including when one account type has an unsupported requirement.
---

# Business Account Fit Recommendation

## Purpose

Turn stated business-banking needs into concise, evidence-based account recommendations. This Skill is for recommendation and explanation only. Do **not** open, modify, fund, or transfer accounts unless the customer later makes an explicit action request and all applicable prerequisites are verified.

Treat checking and savings as separate fit decisions. A missing fact for savings must not prevent a documented checking recommendation, and vice versa.

## Inputs to inspect

Read the complete current conversation, supplied product documents and evidence, and read-only observations. Keep separate:

1. **Checking hard constraints:** mobile-deposit capacity, APY floor, overdraft-fee maximum, ongoing-balance ceiling, and fee sensitivity.
2. **Savings hard constraints:** APY, fees/minimum balances, linked-checking conditions, withdrawal access, sweeps, and specific transfer rail or speed requirements.
3. **Soft preferences:** factors that may break a tie only after every hard constraint is documented as met.
4. **Time-sensitive facts:** current timestamp and promotion dates.
5. **Unknown customer eligibility facts** and **unknown product facts**.
6. Whether the customer seeks a recommendation only or requests account opening.

Do not treat an existing account named by the customer as proof of identity verification, account status, tenure, balance, account count, or eligibility. Never transfer a term from one product to another.

## Decision method

1. Translate customer language into inclusive, testable constraints.
   - “At least” is an inclusive lower bound.
   - “No overdraft fees” requires a documented overdraft fee of exactly $0.
   - “Cannot keep $X or more at all times” concerns an **ongoing required minimum balance**. A monthly-fee waiver threshold is not an ongoing minimum balance requirement.
   - If documents call a balance amount a fee-waiver threshold, do not relabel it as a required minimum balance or reject the candidate on that basis. Disclose the monthly fee and waiver condition accurately.
   - Same-day ACH, including same-day movement between a checking and savings account, requires documentation for that exact capability and relevant account relationship. Generic transfer availability, transfer limits, standard ACH timing, sweeps, or same-day ACH documented only for checking is insufficient.
2. Build candidates only from products with terms relevant to the hard constraints.
3. Exclude candidates that conflict with a hard constraint. If a required product term or product-specific eligibility condition is unknown, mark that candidate unconfirmed rather than qualifying it.
4. If multiple candidates are confirmed matches, use a currently active promotion only as a tie-breaker among those matches. A promotion never overrides a constraint or unknown eligibility.
5. Choose exactly one documented-fit product for each requested account type when one exists. Do not invent an unexpressed savings priority.
6. When a later message introduces an unsupported requirement for only one account type, immediately preserve and state the independently supported recommendation for the other type. Never escalate the entire request merely because one side has a gap.
7. Do not claim that terms or account materials are unavailable when supplied materials document a qualifying candidate.

The optional `scripts/evaluate_candidates.py` helper deterministically filters a normalized candidate list. It is advisory: the executor must extract facts faithfully, assess account-specific eligibility, and produce the customer-facing explanation.

## Required response structure

Once sufficient requirements are known, answer directly rather than requesting unrelated clarification. Use this order, adapting it when only one account type can be recommended:

1. **Direct recommendation:** Explicitly name one confirmed-fit checking account and separately name one savings account only if its fit is fully documented.
2. **Checking fit:** Map every checking hard constraint to documented terms. State the daily mobile-deposit limit, overdraft fee, APY, monthly maintenance fee, and every relevant balance condition. Clearly distinguish an ongoing minimum from a fee-waiver threshold.
3. **Savings result:** If a savings account is confirmed, state its relevant rate, monthly fee, ongoing-balance condition, opening-deposit condition if documented, and linked-account condition. If a required feature is undocumented, say precisely that no supplied savings product documentation verifies that feature. Do not name a savings product as satisfying it.
4. **Focused resolution for a gap:** Offer human-agent escalation specifically to verify the unsupported savings requirement when that is the only unresolved issue. Keep the checking recommendation in the same response.
5. **Material caveats:** Disclose material conditions such as maintenance fees, waiver criteria, mandatory e-statements, and linked-account requirements.
6. **Before opening:** If the customer later asks to proceed, explain that opening eligibility must be verified first. Do not expose internal tool names or signatures.

Keep the response focused. Do not give an exhaustive comparison when the customer asked for one answer.

## Final-response quality gate

Before sending a response, verify all of the following:

- Every independently supported account type receives its explicit recommendation even if the paired type cannot be resolved.
- A supported checking recommendation explicitly names the selected product.
- The checking explanation gives documented values for all customer hard constraints, not merely “it fits.”
- The response states material monthly-fee and fee-waiver terms and does not mislabel a waiver threshold as an ongoing minimum.
- No savings product is represented as supporting same-day ACH between savings and checking unless supplied savings documentation establishes that exact capability.
- If savings support is missing, the response identifies the unverified savings feature and offers escalation for that issue while retaining the supported checking recommendation.
- No recommendation depends solely on a promotion, assumed capability, or unverified product-specific eligibility.

## Opening-account guardrails

A recommendation is not an account-opening request. If the customer later explicitly asks to open an account:

- For business checking, verify identity and every supplied prerequisite regarding existing accounts, status, balance, account count, and the exact official account class before taking action.
- For business savings, verify identity; an eligible OPEN business checking account; savings-account count; no negative balances; and the required qualifying checking-account tenure and balance. A newly recommended checking account does not establish these conditions.
- Obtain the exact official account class. Only fund a new account if the customer expressly authorizes it. If a documented deferred-funding deadline applies, communicate it.

## Failure handling

- For conflicting documents on the same product term, do not silently choose a value; seek confirmation unless supplied authoritative evidence resolves the conflict.
- If customer-specific eligibility for a product is unknown, do not use that product as a promotion-driven recommendation.
- Ignore promotions outside their documented date window.
- If a required feature is not documented, call it unconfirmed; do not infer it from a different product, a similarly named product, or a general process document.
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

`eligibility` may be `eligible`, `unknown`, or `ineligible`; omission means `eligible`. Numeric constraints are inclusive. Promotions apply only to confirmed eligible matches and only when `as_of` falls within their inclusive date range.

Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`, with failed and unknown constraints for each result.

Runnable validation input:

```json
{"requirements": {}, "candidates": []}
```

Validate that stdout is JSON, `errors` is empty, and all result lists are empty. For a populated call, validate that every recommended candidate is in `confirmed_matches` with no failed or unknown hard constraint. The executor must still validate the final customer-facing response against the quality gate above.
