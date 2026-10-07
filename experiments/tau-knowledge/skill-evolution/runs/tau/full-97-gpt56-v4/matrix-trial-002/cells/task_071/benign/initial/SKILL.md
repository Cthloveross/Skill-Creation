---
name: business-account-recommendation
version: 1.0.0
description: Recommend one business checking and one business savings account from documented account facts, stated customer requirements, and time-bounded promotion priorities. Use for informational account-selection requests; do not open accounts unless the customer separately asks to proceed.
---

# Business Account Recommendation

Use this Skill when a customer asks which business checking and/or savings account best fits stated needs. It produces a concise, evidence-grounded recommendation rather than an account-opening action.

## Boundaries

- Treat each stated requirement as a hard filter. A promotional account is eligible only after it meets every relevant stated requirement.
- Do not infer unprovided features, fees, opening eligibility, availability windows, or account suitability beyond the documented facts.
- A recommendation is not an instruction to open an account. Do not verify identity, unlock opening tools, open an account, or transfer funds unless the customer explicitly asks to take that next step.
- If a requirement has no documented comparison data, say so and ask whether it is a deciding factor rather than claiming that an account meets it.

## Method

1. **Separate requirements by account type.** For example, a daily mobile-deposit minimum applies to checking; same-day ACH access applies to savings. Preserve units and qualifiers such as “at least,” “per day,” and “no additional fee.”
2. **Build candidate facts from the supplied knowledge.** Record only explicit values, including account type, limits, availability, fees, integration details, and evidence citations.
3. **Apply hard filters.**
   - Numeric lower bounds pass only when the documented limit is greater than or equal to the requested minimum.
   - A required capability passes only when documentation explicitly says it is available/enabled.
   - If the customer requires a particular price, compare that price separately; availability alone does not establish a price.
4. **Apply promotion priority last.** Determine the current date from the provided time observation. A promotion applies only if that date lies within its stated inclusive effective range. Among qualifying accounts in the same type, select the lowest promotion-rank number. If no active priority applies, do not invent a preference.
5. **Return one direct recommendation per requested account type.** State the account name, the exact documented fact(s) that satisfy the requirement, and a brief note about a material documented tradeoff when relevant. Mention that the recommendation reflects the requirements provided, not unstated preferences.
6. **Offer the next informational step.** For example, offer to discuss documented fees, balances, or eligibility before opening. Do not imply that the customer is eligible without checking the applicable opening procedure.

## Applying the method to the supplied conversation

The supplied requirements are a checking mobile-deposit capacity of at least the requested daily amount and savings access through same-day ACH. Use the provided account documents to populate candidates, then use the observed current date to evaluate the checking and savings promotion notices. The evidence supplied with the task identifies the supporting documents for the qualifying checking account, the qualifying savings account, their relevant capabilities, and the active promotion ordering.

A suitable customer-facing response should be short and decisive, for example in this structure (replace bracketed text only with documented findings):

> Based on the requirements you shared, I recommend **[checking account]** for checking because its documented daily mobile check-deposit limit is **[limit]**, which meets your at-least-[requirement] daily need. For savings, I recommend **[savings account]** because documented same-day ACH is available, which supports rapid reserve access. These choices also follow the active applicable recommendation priority after meeting your stated requirements. If you would like, I can next review the documented fees, balance requirements, and account-opening eligibility before you decide whether to open them.

Do not state that same-day settlement is guaranteed: it may depend on eligibility, submission timing, processing windows, or review where documentation says so.

## Optional deterministic helper

`scripts/select_accounts.py` filters and ranks a runtime-supplied candidate set. It deliberately contains no account catalog or instance-specific answers. Supply facts extracted from the current task documentation.

### Input JSON schema

```json
{
  "as_of": "YYYY-MM-DD or timestamp",
  "requirements": {
    "checking": {"mobile_deposit_daily_min": 10000},
    "savings": {"same_day_ach_required": true}
  },
  "candidates": [
    {
      "name": "Official account name",
      "account_type": "checking or savings",
      "facts": {
        "mobile_deposit_daily_limit": 0,
        "same_day_ach": true
      },
      "evidence": ["document identifier or citation"]
    }
  ],
  "promotions": [
    {
      "account_type": "checking or savings",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "priority": ["Official account name", "Another official account name"]
    }
  ]
}
```

`mobile_deposit_daily_limit` is required only to evaluate a checking deposit-limit requirement. `same_day_ach` is required only when same-day ACH is required. Candidate facts may include other documented fields, but the helper will not infer a match from them.

### Output JSON schema

The helper emits an object with `as_of`, `recommendations`, and `unqualified`. Each recommendation contains the selected candidate, the machine-readable `reasons` used to qualify it, its active `promotion_rank` when applicable, and citations copied from that candidate. `unqualified` reports candidates and explicit filter failures, enabling the executor to explain missing matches accurately.

### Runnable call example

```bash
python3 scripts/select_accounts.py <<'JSON'
{"as_of":"2025-01-15","requirements":{"checking":{"mobile_deposit_daily_min":10000},"savings":{"same_day_ach_required":true}},"candidates":[],"promotions":[]}
JSON
```

The example intentionally has no candidates and should return empty recommendations, not invent account names. Before relying on output, confirm that every selected account has a `pass` reason for every stated requirement, that the relevant promotion is active on `as_of`, and that citations point to the current supplied documentation.
