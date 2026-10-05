---
name: business-checking-recommendation
version: 1.0.0
description: Recommend a business checking account from supplied product evidence by enforcing non-negotiable requirements and product eligibility first, applying active promotional priority only among qualifying products, and clearly separating advice from account-opening actions.
---

# Business Checking Recommendation

Use this skill when a customer asks which business checking account best fits their needs, including an upgrade from an existing account. It produces an evidence-based recommendation; it does **not** open, modify, or close an account.

## Inputs to collect

Build a decision record from the current conversation and the supplied product documents. Do not invent product terms or customer facts.

- Customer requirements, separated into:
  - **Non-negotiable requirements** (for example, a maximum overdraft fee).
  - Eligibility facts (for example, business age).
  - Preferences (yield, transfer capacity, support, fee tolerance, international capabilities, and so on).
- The current date/time when a promotion has an effective period.
- Candidate product facts supported by the supplied documents:
  - eligibility rules;
  - fees, rates, limits, balance requirements, and service features;
  - promotion start/end dates and priority, if any.
- Existing-account facts when the customer requests an upgrade comparison.
- Any account-opening prerequisites described in the supplied procedure. Keep these separate from the recommendation unless the request is to actually open an account.

Represent money and numeric limits as JSON numbers before invoking the helper. Use ISO dates (`YYYY-MM-DD` or an ISO timestamp). Record missing or ambiguous facts as unknown rather than assuming that they are satisfied.

## Decision method

1. Identify hard constraints from the customer's words. Treat statements such as “must,” “non-negotiable,” and “absolutely need” as mandatory.
2. Eliminate a product if evidence shows it fails a hard constraint or product-specific eligibility condition.
3. Do not treat an unverified condition as satisfied. Mark the candidate conditional/unconfirmed and ask the minimum clarifying question needed if it could change the result.
4. Of the fully qualifying products, apply a promotional ordering only when the promotion is active on the supplied current date. Promotional priority never overrides a stated requirement.
5. Break remaining ties using documented preferences and the supplied `preference_score` / `selection_rank`. Do not claim that a feature is better unless the evidence supports the comparison.
6. Compare the selected product with the customer's existing account only on fields documented for both accounts. State consequential tradeoffs, especially maintenance fees, waiver thresholds, minimum-balance requirements, transaction limits, and qualification conditions.
7. Give one direct recommendation when there is a fully qualifying best option. Explain: (a) why it meets the must-haves, (b) why any higher-priority candidate was excluded, and (c) the material tradeoffs or next confirmation needed. If no product is fully confirmed, do not guess; present the conditional options and ask for the missing fact.

A promotion is time-limited evidence, not a permanent product ranking. Use the observed current date rather than the date of a document or a presumed system date.

## Helper

`scripts/rank_accounts.py` deterministically applies eligibility, hard feature constraints, promotion dates/priorities, and explicit tie-break values.

### JSON input schema

```json
{
  "as_of": "ISO-8601 date or timestamp",
  "customer_facts": {"fact_name": "value"},
  "requirements": {
    "required_features": {"feature_name": "required exact value"},
    "min_features": {"feature_name": 0},
    "max_features": {"feature_name": 0}
  },
  "candidates": [
    {
      "name": "product name",
      "features": {"feature_name": "value"},
      "eligibility_rules": [
        {
          "field": "customer fact name",
          "operator": "<=|<|>=|>|==|!=|in|not_in",
          "value": "required value",
          "reason": "customer-facing reason if unmet"
        }
      ],
      "promotion": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "priority": 1},
      "preference_score": 0,
      "selection_rank": 0
    }
  ],
  "existing_account": {"name": "current product", "features": {}},
  "comparison_directions": {"feature_name": "higher|lower"},
  "opening_prerequisites": [
    {"name": "prerequisite to verify", "confirmed": false}
  ]
}
```

All fields other than `candidates` are optional. `required_features` requires exact equality; `min_features` and `max_features` require numeric values. An absent required feature or customer fact is reported as unconfirmed, never as a match. `preference_score` is only a documented, explicit tie-breaker; it cannot make a failed hard requirement qualify.

The helper emits one JSON object with `ok`, `recommendation`, ranked `qualified_candidates`, `conditional_candidates`, `excluded_candidates`, comparison data, and `opening_prerequisites_to_verify`. A null `recommendation` means the available evidence does not establish a fully qualified choice.

Runnable invocation after placing a decision record in `request.json`:

```sh
python3 scripts/rank_accounts.py < request.json
```

Validate the output before responding:

- `ok` must be `true`.
- A non-null recommendation must appear in `qualified_candidates` and have no failed or unconfirmed mandatory checks.
- Confirm that `promotion_active` is true before describing promotional priority as a reason.
- Do not describe `opening_prerequisites_to_verify` as completed.

## Banking-action boundary

This skill is advisory. Do not call an account-opening, transfer, profile-change, or other banking-action tool just because a recommendation was requested. If the customer subsequently asks to open the recommended account, obtain a fresh confirmation of the selected account class and follow the currently supplied opening procedure.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a business-checking opening, also verify every prerequisite specified in the supplied opening documentation (including status, account-count, balance, and closure-status checks where applicable) before using the documented opening tool. A recommendation and an existing business account do not themselves prove those requirements.

## Failure handling

- If a necessary product term or eligibility fact is absent, say so and ask a focused clarification rather than extrapolating from another product.
- If all candidates fail or remain unconfirmed, state that no confirmed recommendation can be made from the evidence and list the deciding missing facts.
- If promotion dates cannot be evaluated, ignore promotional priority rather than assuming it applies.
- If the helper reports invalid input, correct the structured decision record from the supplied evidence; do not silently coerce unsupported values.
