---
name: business-account-fit-recommendation
description: Give a focused, evidence-based recommendation for business checking and savings accounts from supplied product materials, while isolating and escalating only account-specific requirements that cannot be verified.
---

# Business Account Fit Recommendation

## Scope

Use this Skill when a customer asks which business checking and/or savings account is right for them. It supports recommendations, not account opening, funding, or transfers.

Treat checking and savings as **independent decisions**. A missing savings fact must never suppress a documented checking recommendation. Likewise, a checking uncertainty must not invalidate a separately supported savings conclusion.

## Gather and classify requirements

Read the complete conversation, supplied product documents, evidence, and current-time observation. Extract each requirement into one of these groups:

- **Hard constraints:** requirements a product must demonstrably satisfy.
- **Soft preferences:** tie-breakers after all hard constraints are met.
- **Customer eligibility facts:** facts about the customer that may be needed for a product.
- **Product facts:** documented account terms and capabilities.
- **Unknowns:** absent customer facts or absent product documentation.

Do not infer identity verification, account status, balance, tenure, account count, eligibility, or a capability from an account the customer already has.

Interpret common language precisely:

- “At least” and “no more than” are inclusive bounds.
- “No overdraft fees” requires an explicitly documented overdraft fee of $0.
- “I cannot maintain $X” concerns an ongoing required minimum balance. A balance that only waives a monthly fee is not an ongoing minimum requirement.
- A fee-waiver threshold must be disclosed accurately along with the fee; never relabel it as a mandatory minimum balance.
- “Same-day ACH between checking and savings” requires documentation of that exact capability for the relevant savings product and relationship. Generic transfers, transfer limits, standard ACH timing, sweeps, or same-day ACH documented only for checking do not establish it.

Ask only for information necessary to resolve a material requirement. Once a checking candidate is documented as meeting all known checking constraints, do not wait for unrelated savings clarification before recommending it.

## Candidate decision procedure

For each requested account type separately:

1. List candidate products only where relevant product terms are documented.
2. Compare every hard constraint with product-specific evidence.
3. Exclude products that conflict with a hard constraint.
4. Mark a candidate **unconfirmed**, rather than qualifying it, if a required term or product-specific eligibility condition is unknown.
5. If one or more candidates are confirmed, select exactly one. Use an active promotion only as a tie-breaker among confirmed matches.
6. A promotion never overrides a hard constraint, missing term, or unknown eligibility condition.
7. If no product can be confirmed for that account type, state the exact unsupported requirement and offer focused human review for that requirement.

Never say that terms or account materials are unavailable when supplied materials document the terms needed for a qualifying candidate.

The optional `scripts/evaluate_candidates.py` helper can filter a normalized candidate set. It cannot extract facts, resolve conflicting documents, or determine whether a document proves a relationship-specific capability; the executor must do those tasks from the supplied materials.

## Required customer-facing response

When sufficient requirements have been collected, respond directly. Do not replace a recommendation with a general transfer merely because another requested account type has an evidence gap.

Use this structure:

1. **Checking recommendation:** Explicitly name the one documented-fit checking product, if one exists.
2. **Checking evidence:** In the same recommendation message, map every checking hard constraint to the actual documented term. Include applicable mobile-deposit capacity, overdraft fee, APY, monthly maintenance fee, and balance condition. Distinguish an ongoing minimum balance from a fee-waiver threshold.
3. **Savings outcome:** Name one savings account only if every stated savings hard constraint is documented as met. State the relevant rate, fees, minimum-balance condition, linked-account condition, and transfer capability.
4. **Narrow escalation:** If a savings requirement is not documented, say that no supplied savings documentation verifies that exact feature. Do not claim that a product meets it, and offer or perform escalation specifically to verify that savings requirement.
5. **Material conditions:** Mention documented e-statement, linked-account, or similar conditions that materially affect the choice.
6. **Next step:** If the customer later requests opening, explain that eligibility must first be verified. Do not expose internal tool names.

A suitable response pattern is:

> **Checking:** I recommend **[documented checking product]**. It provides [documented deposit term], [documented overdraft term], and [documented APY]. Its [monthly fee] is [fee condition]; [balance amount] is a [waiver threshold or ongoing minimum, as documented].
>
> **Savings:** I cannot confirm a savings recommendation for your [specific requirement]. The supplied savings materials do not verify [exact capability]. I can have a human agent verify that requirement while your checking recommendation remains [checking product].

Fill brackets only with current supplied evidence. Do not use this pattern to assert missing facts.

## Final-response quality gate

Before sending the final recommendation, verify:

- Each account type was evaluated independently.
- Every independently supported type has an explicit, named recommendation.
- The checking recommendation names the product and states each material requested checking term in the final recommendation, not only in prior clarification.
- Maintenance fees and fee-waiver thresholds are accurate and are not presented as ongoing minimums unless documentation calls them ongoing minimums.
- No savings account is presented as supporting same-day ACH between savings and checking without documentation of that exact feature.
- An unsupported feature produces a precise, narrow escalation, while supported recommendations remain in the response.
- No recommendation relies solely on promotion priority, assumed capabilities, or unknown product-specific eligibility.

## Opening-account guardrails

A recommendation alone is not authorization to open an account. If the customer explicitly asks to proceed:

- For business checking, verify identity and all supplied prerequisites concerning existing account status, balances, account count, and the exact official account class.
- For business savings, verify identity, qualifying open business checking, savings-account count, absence of negative balances, and any required checking tenure and balance.
- Obtain the exact official account class before opening.
- Transfer opening funds only with explicit customer authorization. If a documented deferred-funding deadline applies, disclose it.

## Failure handling

- If documents conflict on a material term and no authoritative supplied evidence resolves the conflict, seek confirmation rather than choosing a value.
- If customer eligibility is unknown, do not use that product as a promotion-driven recommendation.
- Ignore promotions outside their documented dates.
- Do not infer a capability from similarly named products, general procedures, transfer limits, or a feature documented for another account type.
- Escalate only the unresolved portion of the request.

## Candidate evaluator

`scripts/evaluate_candidates.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "as_of": "optional ISO-8601 date or timestamp",
  "requirements": {
    "numeric_min": {"field": 0},
    "numeric_max": {"field": 0},
    "equals": {"field": "value"}
  },
  "candidates": [
    {
      "id": "stable identifier",
      "name": "customer-facing name",
      "facts": {"field": 0},
      "eligibility": "eligible",
      "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    }
  ]
}
```

`eligibility` is `eligible`, `unknown`, or `ineligible` and defaults to `eligible`. Numeric bounds are inclusive. A promotion applies only if `as_of` is within its inclusive date range and the candidate has no failed or unknown hard constraint.

Output schema contains `errors`, `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`. Each candidate result identifies failed and unknown constraints.

Runnable validation input:

```json
{"requirements": {}, "candidates": []}
```

Validate that output is JSON, `errors` is empty, and all result lists are empty. For populated input, every item in `recommended_order` must also be a confirmed match with no failed or unknown constraint. The executor must still apply the final-response quality gate.
