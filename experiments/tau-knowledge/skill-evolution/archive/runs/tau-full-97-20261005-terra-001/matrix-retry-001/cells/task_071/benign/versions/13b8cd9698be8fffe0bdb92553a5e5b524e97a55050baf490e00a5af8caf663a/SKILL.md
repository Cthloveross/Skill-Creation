---
name: business-account-fit-recommendation
description: Recommend one business checking account and, when requested, one business savings account from supplied product materials. Use when a customer gives operational requirements and wants a concise best-fit recommendation rather than an exhaustive comparison. Handles time-limited promotions, product eligibility uncertainty, and the separate prerequisites for opening an account.
---

# Business Account Fit Recommendation

## Purpose

Turn a customer's stated banking needs into a defensible, concise recommendation using the account documents and evidence provided at runtime. This Skill is for recommendation and explanation; it does **not** open, modify, fund, or transfer between accounts unless the customer subsequently and explicitly asks to do so.

## Inputs to inspect

Read the current conversation, supplied product documents/evidence, and any read-only observations. Extract separately:

1. **Checking requirements** — for example, daily mobile-deposit minimum, minimum APY, maximum overdraft fee, maximum acceptable required balance, and fee sensitivity.
2. **Savings requirements** — for example, yield, monthly fee, ongoing balance requirement, transfer access, sweep support, and linked-checking requirements.
3. **Account-opening intent** — distinguish “tell me what fits” from a request to open an account.
4. **Time-dependent facts** — use the provided current timestamp to determine whether a promotion is active.
5. **Facts that remain unknown** — do not treat an existing account mentioned by the customer as proof of tenure, balance, account status, identity verification, or any other opening prerequisite.

Treat an explicit evidence item that says an account meets a requirement as support for that exact requirement. Reconcile documents by account name and feature; do not transfer a feature, rate, fee, or limit from one account to another.

## Decision method

1. Convert the customer's language into hard constraints. For example:
   - “at least” is an inclusive lower bound;
   - “cannot have overdraft fees” means the documented overdraft fee must be exactly $0;
   - an ongoing minimum-balance requirement is different from a balance level that waives a monthly fee.
2. Build a candidate list from only products whose relevant terms are documented. A hard constraint with an unknown value is **not** confirmed as met.
3. Exclude candidates that conflict with a hard constraint. Do not substitute “usually,” a temporary free period, or an undocumented feature for a required feature.
4. If more than one candidate is confirmed to meet every requirement, apply a currently active promotion only as a tie-breaker and only when the promoted product itself is confirmed eligible and still meets every requirement. A promotion never overrides fit or eligibility.
5. For savings, do not invent a yield/fee/sweep priority the customer did not state. If the available material clearly supports a low-friction option (such as no monthly fee and no ongoing balance requirement) that is appropriate for the customer’s stated cash-flow concerns, it may be recommended as the practical default. State that this is the default used because no savings priority was supplied, not a claim that it is the highest-yield option.
6. Select one checking product and one savings product when each has a defensible fit. If there is no confirmed fit, identify the exact missing fact or unmet condition and ask only the necessary follow-up question.

For repeatable filtering, the executor may invoke `scripts/evaluate_candidates.py` with a normalized candidate list. The script is advisory: the executor remains responsible for extracting accurate product facts and explaining the decision in customer-facing terms.

## Required response structure

Give a direct answer in this order:

1. **Recommendation:** name exactly one checking account and, if requested and supported, exactly one savings account.
2. **Why the checking account fits:** explicitly map each stated checking requirement to the documented mobile-deposit limit, overdraft fee, APY, and balance/fee terms. Clearly distinguish a fee-waiver threshold from a required minimum balance.
3. **Why the savings account fits:** give its APY, monthly fee, ongoing balance requirement, opening-deposit requirement if documented, and any linked-checking condition that matters.
4. **Important caveats:** mention material conditions such as mandatory e-statements, a monthly fee that may apply if a waiver threshold is not met, or savings funding/linkage requirements. Do not claim a savings yield is “best” unless the supplied comparison actually establishes that.
5. **Before opening:** state the applicable opening prerequisites that must be verified, if the customer later asks to proceed. Recommendation alone does not establish eligibility.

Keep the result focused. Do not present a broad comparison table when the customer requested a single answer. Do not expose internal tool names, signatures, or tool workflows to the customer.

## Opening-account guardrails

If the customer later explicitly asks to open an account, follow the supplied opening procedure rather than assuming recommendation equals eligibility.

- For a business checking opening, confirm the documented identity, existing-account, account-count, account-status, balance, and requested account-class prerequisites before opening.
- For a business savings opening, confirm identity; an eligible OPEN business checking account; the documented savings-account count; no negative balances; and a qualifying checking account’s tenure and balance. A newly recommended checking account does not automatically establish those conditions.
- Capture the customer’s exact official account class before any opening action.
- If the customer authorizes opening-deposit funding, use only the qualifying checking account and handle a failed funding transfer as specified by the supplied procedure. If funding is deferred, communicate the documented funding deadline.

Do not make an account-opening or transfer action merely because the customer asked for a recommendation.

## Failure handling

- If two source documents conflict on the same product term, do not silently choose a value. State that the term needs confirmation or use a supplied authoritative evidence statement if one resolves the issue.
- If an account has additional product-specific eligibility requirements with unknown customer facts, do not use it as a promotion-driven recommendation until those facts are confirmed.
- If an active promotion is outside its stated date range according to the provided time, ignore it.
- If a required feature is not documented for a candidate, say it is unconfirmed rather than infer it from another account.

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

`eligibility` may be `eligible`, `unknown`, or `ineligible`; omitted eligibility is treated as `eligible`. Numeric constraints are inclusive. Candidate fact values may be numeric, numeric strings, booleans, or strings. Promotion rank is applied only to confirmed eligible candidates whose inclusive date window contains `as_of`.

Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`. Each entry identifies failed or unknown fields so the executor can explain the result accurately.

A runnable empty-input validation call is to send this JSON to the script:

```json
{"requirements": {}, "candidates": []}
```

Expected validation: stdout is valid JSON, `errors` is an empty list, and all three candidate-result lists plus `recommended_order` are empty. For a populated call, validate that every recommended candidate appears in `confirmed_matches`, has no failed or unknown hard constraints, and that any promotion ordering is active for the supplied `as_of` date.
