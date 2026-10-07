---
name: business-checking-single-recommendation
description: Recommend one business checking account from supplied product evidence when a customer states non-negotiable requirements and does not want a comparison. Use this for informational account selection only; do not use it to open, modify, or transact on an account.
---

# Business Checking: Single, Evidence-Based Recommendation

Use this Skill when the task is to identify one business checking account that satisfies a customer's stated needs. It is designed to avoid treating unverified eligibility as satisfied and to apply a supplied, time-bounded promotional priority only after all customer requirements are met.

## Inputs to collect

At runtime, derive the following only from the current request, its clarifications, current-time observation, and supplied product/policy evidence:

1. **Hard requirements**: values the customer says are mandatory (for example, a maximum overdraft fee or a minimum monthly ATM-fee rebate).
2. **Candidate facts**: each account's documented fees, benefits, eligibility rules, and any material caveats.
3. **Eligibility status** for each candidate: `confirmed`, `not_confirmed`, or `ineligible`. A required eligibility fact that the customer cannot confirm is `not_confirmed`, not `confirmed`.
4. **Promotion status**: whether a documented promotion is active at the observed current time, plus its ordering among accounts. Do not apply expired, future, or inapplicable promotions.

Do not infer missing product terms, customer eligibility, fee waivers, or benefit amounts. Do not convert a count-based benefit into a dollar benefit unless the source expressly supports that interpretation.

## Procedure

1. Identify hard requirements from the conversation. Treat words such as “absolutely,” “cannot,” “non-negotiable,” “at least,” and “must” as hard constraints.
2. Build a structured candidate list using the supplied evidence. Include only factual claims that will be used in the response.
3. Mark a candidate `ineligible` if supplied evidence shows it fails a requirement. Mark it `not_confirmed` if it depends on an eligibility fact that is unavailable. A candidate with either status cannot be recommended as meeting all requirements.
4. Run `scripts/rank_accounts.py` with normalized candidate facts and requirements. The script filters candidates that cannot be established to satisfy every hard constraint, then applies active promotional rank and a supplied ordinary rank as deterministic tie-breakers.
5. If the script returns a recommendation, tell the customer the one account name first. Give a concise rationale tied to each hard requirement and, where useful, one clearly documented usability/perk feature. State only facts represented in the structured input.
6. If a higher-priority account was not recommendable because eligibility is unconfirmed, do not present it as a competing recommendation. Briefly state that its eligibility could not be established if that explains the result. Do not pressure the customer for information that is not needed to make the supported recommendation.
7. If no candidate is eligible and confirmed, explain which needed facts or requirements prevent a recommendation and ask only for the information that could resolve the decision.

This is an informational recommendation, not an account-opening workflow. Do not invoke account-opening, profile, payment, transfer, or other banking-action tools merely to make the recommendation. If the customer later asks to open an account or perform another banking action, follow the separately supplied procedure and its verification, authority, ownership, product-eligibility, balance, fee, limit, cutoff, recipient/card-detail, and confirmation prerequisites before acting.

## Script interface

`scripts/rank_accounts.py` reads one JSON object from standard input and writes one JSON object to standard output.

### Input schema

```json
{
  "requirements": {
    "max_overdraft_fee": 0,
    "min_atm_rebate_monthly": 0
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "Account name from current evidence",
      "eligibility": "confirmed",
      "overdraft_fee": 0,
      "atm_rebate_monthly": 0,
      "promotion_rank": 1,
      "ordinary_rank": 100,
      "facts": ["A documented product fact safe to cite"]
    }
  ]
}
```

`max_overdraft_fee` and `min_atm_rebate_monthly` are optional. Monetary values must be numeric and expressed in the same currency/unit as the evidence. `promotion_rank` and `ordinary_rank` are optional positive integers; a lower rank is preferred. `facts` is optional and is returned unchanged for use in the customer-facing rationale.

### Output schema

On success, output contains `status: "recommended"`, a `recommendation` object, and `excluded` candidates with non-sensitive reasons. If nothing can be established to meet the requirements, output contains `status: "no_confirmed_match"`, `recommendation: null`, and exclusions. Invalid input produces `status: "invalid_input"` and an error message.

### Runnable example

```sh
python3 scripts/rank_accounts.py <<'JSON'
{"requirements":{"max_overdraft_fee":0,"min_atm_rebate_monthly":15},"promotion_active":true,"candidates":[{"name":"Example A","eligibility":"confirmed","overdraft_fee":0,"atm_rebate_monthly":20,"promotion_rank":2,"facts":["Zero overdraft fee"]}]}
JSON
```

## Validation before responding

Check that:

- every hard requirement is addressed by the selected account with a documented value;
- its eligibility is `confirmed`;
- active promotion priority was applied only among confirmed matches;
- amounts, time periods, and benefit units match the evidence;
- the final answer recommends exactly one account when a confirmed match exists and does not imply an account has been opened.
