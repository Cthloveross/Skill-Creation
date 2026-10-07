---
name: business-checking-recommendation
version: 1.0.0
description: Recommend one business checking account from supplied account materials when a customer has stated must-have features. Use it for comparison or recommendation requests, including time-limited promotional priorities. It verifies every must-have from evidence before recommending and does not treat undocumented features as satisfied.
---

# Business Checking Recommendation

Use this Skill when a customer asks which business checking account best fits their needs. It produces a defensible single recommendation without opening an account or changing customer data.

## Required runtime inputs

Read the current conversation, account materials, and any supplied read-only time observation. Extract a structured input for `scripts/select_account.py`:

- `requirements`: every customer **must-have**, represented as a field, comparison operator, and value.
- `offers`: one object per account. Include only facts expressly supported by the supplied materials. Omit a field when it is not established.
- `promotion_active`: true only when the observed current date falls within the promotion period and the promotion applies to this type of recommendation.
- `promotion_rank`: the applicable priority number for each promoted offer (lower is better).
- `tie_breakers`: optional customer-relevant, evidence-supported preferences for resolving otherwise valid choices.

The helper's full JSON schema is documented in the script header and in its validation errors.

## Decision procedure

1. Identify the customer’s hard requirements from the conversation and clarifications. Do not convert a vague preference such as “most perks” into an unsupported requirement.
2. Extract facts separately for each account. Preserve units and scope. For example, distinguish a bank-assessed domestic ATM fee, a foreign ATM fee, an ATM-owner surcharge, and a monthly rebate cap.
3. A missing fact is **not** proof that the account meets the requirement. Leave it absent; the helper marks the offer as needing evidence rather than eligible.
4. Run `scripts/select_account.py` with the extracted facts.
5. Apply promotional priority only after all hard requirements have been verified. A promoted account with an unknown or failed must-have must not be recommended on that basis.
6. If the helper selects an offer, give the customer a direct recommendation. State the requirements it satisfies and the material operational terms that explain the benefit (for example, rebate cap and fee treatment). Also disclose material tradeoffs explicitly documented for the selected account, such as maintenance fees, balance thresholds, or a per-withdrawal foreign fee.
7. If no offer qualifies, say that the available information does not establish an account that meets every must-have. If a fact is missing, identify the missing feature rather than claiming the account lacks it. Ask whether the customer wants to relax a requirement or obtain more account information.
8. If several offers remain tied and there is no valid promotion or evidence-supported tie breaker, do not invent a “best” account. Ask one focused preference question or present the remaining decision point.

## Customer-facing response rules

- Give one recommendation when selection is unambiguous; do not make the customer compare a long list.
- Do not say an account has “no fees” when the evidence only establishes no overdraft fee or a rebate.
- Explain caps as caps and describe whether a rebate is automatic only when that is documented.
- Do not initiate account opening. If the customer asks to open an account later, separately follow the applicable identity verification and account-opening procedure and eligibility checks.
- Do not claim a customer is personally eligible based solely on product features.

## Runnable helper

The script reads one JSON object from standard input and writes one JSON object to standard output:

```json
{
  "requirements": [
    {"field": "overdraft_fee", "operator": "equals", "value": 0},
    {"field": "atm_rebate_cap", "operator": "at_least", "value": 15}
  ],
  "offers": [
    {
      "name": "Account name from current materials",
      "facts": {"overdraft_fee": 0, "atm_rebate_cap": 25},
      "evidence": {"overdraft_fee": "source title", "atm_rebate_cap": "source title"},
      "promotion_rank": 2
    }
  ],
  "promotion_active": true,
  "tie_breakers": []
}
```

Run it with the executor's packaged-script facility or equivalent Python runtime. Its `status` is one of:

- `selected`: use `recommendation`, `selection_basis`, and supporting evidence to compose the answer.
- `no_verified_match`: no offer has verified satisfaction of every must-have; inspect `offer_assessments`.
- `ambiguous`: the available evidence does not justify a single choice; inspect `remaining_offers`.
- `invalid_input`: correct the extraction error before using the result.

Validate the final response against the helper output: every claimed must-have must appear in the selected offer’s `matched_requirements`, every factual claim must be in the current materials, and a promotion basis must appear only when `promotion_active` is true.
