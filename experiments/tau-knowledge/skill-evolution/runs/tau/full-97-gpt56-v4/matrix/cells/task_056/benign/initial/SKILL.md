---
name: business-checking-recommendation
version: 1.0.0
description: Recommend a business checking account from supplied account-policy evidence when a customer wants an upgrade or comparison. Use it to identify non-negotiable requirements, respect dated promotional priority only among qualifying accounts, disclose material tradeoffs, and avoid account-opening actions unless requested and eligible.
---

# Business Checking Recommendation

## Purpose
Give a concise, evidence-grounded account recommendation without treating a promotion, a feature preference, or an unverified eligibility condition as sufficient to override a customer's stated hard requirement.

This Skill is for informational recommendations. It does **not** open, modify, or close an account.

## Inputs to collect from the task context

1. The customer's current account and their stated goal (for example, an upgrade or more support/features).
2. Explicit hard requirements, especially wording such as “must,” “non-negotiable,” or “absolutely need.”
3. Account facts and eligibility conditions from the supplied knowledge evidence, including fees, limits, support, balance requirements, and feature facts relevant to the stated goal.
4. Any promotional ranking and its effective dates. Check the current date supplied by the runtime before applying it.
5. Any facts that are missing or unknown. Do not infer eligibility, balance capacity, transaction volume, company age, or account qualifications.

No identity lookup or verification is needed merely to provide a general recommendation. Do not access customer records unless the customer requests an account-specific action that requires it.

## Method

1. **Separate requirements from preferences.**
   - A stated zero-fee requirement for a particular fee category is a hard filter.
   - “More features” is a preference. Support it with concrete, source-backed comparisons to the current account; do not promise unspecified features.

2. **Screen every candidate.**
   - Reject a candidate if an established fact conflicts with a hard requirement.
   - Treat a required eligibility condition with an unknown status as *not confirmed qualifying*. Do not recommend that account as the answer solely because it has an attractive feature or promotional rank.
   - A fee of zero in one category does not mean all fees or balance-related consequences are zero. Keep fee categories distinct.

3. **Apply promotions only after screening.**
   - Apply a promotional ordering only when it is active on the runtime date.
   - Rank only accounts that meet every stated hard requirement and whose necessary eligibility conditions are established. An account cannot be promoted ahead of a qualifying alternative when its eligibility is unknown.

4. **Choose and explain the recommendation.**
   - Recommend the highest-ranked confirmed qualifier. If no promotion applies, choose the best source-supported fit for the stated preferences.
   - Compare it to the customer’s current account only using documented metrics relevant to the request (for example, APY, transfer capacity, or dedicated support).
   - State the key reason it meets each hard requirement and note material costs, balance thresholds, or constraints. Do not describe a monthly fee as waived unless the evidence establishes the applicable waiver condition.

5. **Handle uncertainty constructively.**
   - If a better-ranked candidate depends on an unknown condition, briefly say it was not selected because that condition has not been established.
   - Ask only targeted follow-up questions that could materially change the recommendation, such as typical balance, payment/transfer needs, cash deposits, international payments, or desired access/users. Do not delay a clear recommendation that is already supported by the evidence.

6. **Keep the scope informational.**
   - Do not open an account, change an existing account, or claim that a conversion is available unless the customer asks and the required procedure is supported.
   - If the customer later asks to open an account, first follow the supplied account-opening eligibility and verification procedure. Explain any missing prerequisite instead of guessing.

## Recommended response structure

Use plain, customer-facing language:

1. Lead with: “Based on your stated requirements, I recommend **[account]**.”
2. Explain the hard-requirement match, including the exact relevant fee category.
3. Give two or three documented upgrade comparisons against the current account that directly support the customer’s goal.
4. Mention material tradeoffs or balance conditions in a separate sentence.
5. If applicable, explain in one sentence why a promotional alternative was not selected (for example, an eligibility fact is not established).
6. Offer a short, targeted next step or question; do not pressure the customer to open the account.

Avoid claiming that the account is universally “best,” that eligibility is complete, or that a fee waiver will occur without the required balance/period facts.

## Optional deterministic screening helper

Use `scripts/select_account.py` when account facts have been transcribed from the supplied runtime evidence into structured JSON. The script reads one JSON object from stdin and writes one JSON object to stdout. It makes no bank changes.

Input schema:

- `candidates`: nonempty array of objects with:
  - `name` (string)
  - `facts` (object): source-backed values keyed by fact name
  - optional `eligibility_requirements`: array of `{ "key": string, "status": true|false|null }`; `null` means unknown
  - optional `feature_score` (number): only a source-backed, task-specific tie-breaker after hard screening
- `requirements`: array of `{ "key": string, "op": "eq"|"ne"|"gte"|"lte"|"exists", "value": any, "hard": boolean }`. Missing facts are unknown; missing hard facts do not qualify.
- optional `promotion`: `{ "active": boolean, "ordered_accounts": [string] }`
- optional `baseline_name` and `comparison_metrics` (array of fact keys) to emit supported comparisons with the current account.

Run it with a runtime-created input file:

```sh
python3 scripts/select_account.py < case.json
```

Interpret `selection` as the recommended confirmed qualifier. `unconfirmed_candidates` are not valid recommendations until their listed unknown eligibility conditions are established. Review `assessments` and the original evidence before wording a customer response.

## Validation checklist

Before sending the response, verify that:

- every stated non-negotiable requirement is explicitly addressed;
- the recommendation has no failed or unknown hard requirement;
- a dated promotion was used only if active and only after qualification;
- each numerical claim and comparison is present in supplied evidence;
- material balance, fee, and eligibility caveats are not omitted or conflated;
- no unauthorized account action, verification claim, or unsupported conversion claim is made.
