---
name: business-checking-recommendation
version: 1.0.0
description: Recommend exactly one business checking account from supplied product evidence when a customer has stated must-have features, eligibility is known or uncertain, and a dated promotional-priority rule may apply. Use for recommendation requests, not for account-opening execution.
---

# Business Checking Recommendation

## Purpose

Turn the customer's stated needs and the supplied product evidence into one supported recommendation. Treat explicit customer requirements as hard constraints. Do not recommend a product if a required product attribute or a required eligibility condition is unknown, unsupported, or fails.

This Skill separates recommendation from account opening. Do not verify identity, open an account, or invoke banking tools unless the customer explicitly elects to proceed after receiving the recommendation and the applicable opening procedure has been completed.

## Required runtime inputs

Gather or derive the following at runtime:

1. The customer's hard requirements and preferences. A requirement is hard when the customer calls it required, non-negotiable, a minimum, or otherwise makes it a condition of selection.
2. Candidate account facts and citations from the supplied knowledge/evidence.
3. Account-specific eligibility conditions and their status (`true`, `false`, or `unknown`).
4. The current date/time when a dated promotion could affect ordering.

Use `references/source-map.md` for the supplied-account evidence relevant to this task. It is a citation map, not a substitute for checking current-date applicability or customer eligibility.

## Decision method

1. Extract hard constraints faithfully. For example, a zero-overdraft-fee request becomes `overdraft_fee == 0`; a request for at least a stated monthly ATM rebate amount becomes `atm_rebate_monthly >= requested_amount`.
2. Record unknown eligibility honestly. An account whose required eligibility condition is unknown is not established as qualifying; do not select it merely because it might qualify.
3. Build structured candidate data and optionally run `scripts/select_account.py`. The script applies hard constraints, excludes failed or unknown required eligibility, evaluates dated promotions, and returns a deterministic selection.
4. Only apply a promotion to products that already meet every hard requirement and have confirmed eligibility. Check whether the promotion is active on the runtime date before using it.
5. If no qualifying account is established, ask the smallest useful eligibility or requirement question. Do not guess or recommend a near match.
6. Give one recommendation, not a broad comparison. State the features that satisfy the customer's must-haves, include concise material caveats supported by evidence, and cite the relevant product documents in internal work when citations are required by the host.

## Task-specific application notes

For the supplied request, the customer has two hard constraints: no overdraft fee and at least the requested monthly ATM-fee rebate amount. The customer also did not confirm the formation-age condition required for Sky Blue. The source map identifies the supported product facts, the promotion dates, and the general opening prerequisites.

When the active promotion applies, follow its stated ordering only after qualification has been established. A product with an unconfirmed formation-age requirement is not a confirmed qualifying option. Do not turn a preference for ease/perks into an unsupported claim; use documented benefits such as dedicated support only when they are in the evidence.

## Script interface

`scripts/select_account.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "requirements": [
    {"key": "attribute_name", "op": "eq|gte|lte|contains|in", "value": 0, "hard": true}
  ],
  "candidates": [
    {
      "name": "Account name",
      "attributes": {"attribute_name": 0},
      "eligibility": [
        {"key": "condition", "status": "true|false|unknown", "reason": "optional explanation"}
      ],
      "soft_score": 0,
      "sources": ["document identifier"]
    }
  ],
  "promotion": {
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD",
    "priority": ["Account name in promotion order"]
  }
}
```

`hard` defaults to `true`. Missing attributes fail hard constraints. `soft_score` is used only when no active promotion ranks the qualifying products; it must be based on documented customer preferences rather than invented benefits. Dates are inclusive. The script returns `recommended` as either one qualifying candidate summary or `null`, along with qualification and exclusion reasons.

A runnable invocation is:

```text
python scripts/select_account.py < request.json
```

In the packaged runtime, pass the same object to `run_skill_script` with `relative_path` set to `scripts/select_account.py`.

## Output validation and customer response

Before responding, confirm all of the following:

- Exactly one account is named when a recommendation is possible.
- Every hard requirement passed for that account.
- All required account eligibility conditions are confirmed true.
- Any promotion used was active on the relevant date and did not override requirements.
- Monetary terms and caveats match a supplied source.
- No account-opening action was taken without an explicit request and completion of the separate eligibility/verification process.

A concise response should lead with the chosen account, connect it to the customer's must-haves, mention material fees or thresholds relevant to the recommendation, and offer next steps without assuming consent to open an account.
