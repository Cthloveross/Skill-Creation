---
name: business-checking-recommendation
version: 1.1.0
description: Recommend an evidence-supported business checking account by enforcing stated must-haves and documented eligibility, applying active promotional priority among qualifying accounts, and giving a complete fee and upgrade comparison without performing an account-opening action.
---

# Business Checking Recommendation

Use this skill when a customer asks which business checking account fits their needs, including an upgrade from an existing account. This is an advisory workflow. Do not open, modify, close, or otherwise act on an account merely because the customer asked for a recommendation.

## Gather current decision facts

Use the current conversation, supplied product documents, and observed current time. Do not infer undocumented product terms or customer facts. Record:

- Customer **must-haves** separately from preferences. Treat “must,” “non-negotiable,” “absolutely need,” and a stated maximum fee as hard constraints.
- Product-specific eligibility facts and the customer's answer to each one.
- Candidate fees, waiver thresholds, minimum-balance requirements, APY, limits, and service features.
- The active promotion's inclusive start/end dates and its ordering, if supplied.
- Documented facts about the existing account when the request is an upgrade.

Interpret a maximum monthly-cost preference as a numeric maximum when the customer states one. For example, an account with a documented monthly maintenance fee below the customer's stated cap meets that fee preference; the fee still must be disclosed.

A balance threshold or minimum-balance requirement is a material tradeoff to disclose. Do not treat an unknown customer balance as a failed product-specific eligibility rule unless the product documentation actually makes that balance a condition of eligibility or the customer says they cannot meet it.

## Decision method

1. Identify all hard constraints and product eligibility conditions.
2. Exclude a product only when evidence shows it fails a hard constraint or a documented eligibility condition. State the specific reason for every higher-priority product excluded.
3. If a fact required to evaluate a true hard constraint or eligibility condition is missing, mark that candidate conditional and ask the focused question needed to resolve it. Never silently assume it is met.
4. Among fully qualifying candidates, apply promotional ordering only if the supplied current date is within the promotion's effective dates. Promotion never overrides a customer requirement.
5. Use only documented preferences and features to break any remaining tie.
6. Compare the selected account to the customer's existing account only where both values are documented. Describe supported improvements and material tradeoffs.

## Mandatory completed-recommendation response

Once the available evidence identifies a fully qualifying best account, give the recommendation directly in the same customer-facing response. Do **not** replace it with an escalation, a generic promise to review options, or an additional question that is not necessary to determine eligibility or a stated must-have.

The response must contain all applicable items below:

1. Name the recommended account plainly.
2. Explain why it satisfies each customer must-have, using the exact documented values. In particular, when zero overdraft fees are required, explicitly use the words **overdraft fee** and state the documented `$0`/`$0.00` amount (or “zero,” if that is the documented expression).
3. State the selected account's monthly maintenance fee as a dollar amount whenever documented, even if it is within the customer's budget. Include a documented waiver threshold and minimum-balance requirement when supplied, and distinguish the two rather than treating them as the same thing.
4. Explain why it is an upgrade using at least one documented comparison to the customer's current account. Prefer a concrete APY, transaction-limit, or service-access comparison; do not make unsupported “better” claims.
5. If promotion affects the result, say it is active and applies only after explaining why any higher-priority promotional candidate is ineligible or otherwise does not meet the customer's requirements.
6. State that the answer is a recommendation, not confirmation that an account has been opened.

When the customer has ruled out a higher-priority promotional account through a documented eligibility answer, continue to the next qualifying promotional account. Do not treat the excluded account's ineligibility as a reason to stop the recommendation process.

A concise response structure is:

> **Recommendation:** [selected account]. [Higher-priority account] is not available because [documented failed eligibility]. [Selected account] meets your [must-have] because its [fee/feature] is [exact value]. Its monthly maintenance fee is [exact value]; [documented waiver/minimum-balance context]. Compared with your current account, it provides [supported, concrete upgrade]. This is a recommendation only; opening it requires separate checks.

## Deterministic ranking helper

Use `scripts/rank_accounts.py` for repeated comparison once product facts have been transcribed from the current supplied evidence. It performs no banking action.

### Input JSON

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "customer_facts": {"business_age_years": 6},
  "requirements": {
    "required_features": {"overdraft_fee": 0},
    "min_features": {"apy": 1.0},
    "max_features": {"monthly_maintenance_fee": 50}
  },
  "candidates": [
    {
      "name": "Account name",
      "features": {"overdraft_fee": 0, "monthly_maintenance_fee": 25},
      "eligibility_rules": [
        {
          "field": "business_age_years",
          "operator": "<=",
          "value": 4,
          "reason": "business must be within four years of formation"
        }
      ],
      "promotion": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "priority": 1},
      "preference_score": 0,
      "selection_rank": 0
    }
  ],
  "existing_account": {"name": "Current account", "features": {"apy": 0.5}},
  "comparison_directions": {"apy": "higher"},
  "opening_prerequisites": [{"name": "identity verified", "confirmed": false}]
}
```

All fields except `candidates` are optional. `required_features` means exact equality; numeric minimum and maximum feature maps mean inclusive limits. Missing features or customer facts are reported as unconfirmed, not as matches. Eligibility rules support `<=`, `<`, `>=`, `>`, `==`, `!=`, `in`, and `not_in`.

Run it with JSON on stdin:

```sh
python3 scripts/rank_accounts.py < request.json
```

It emits JSON with `ok`, `recommendation`, `qualified_candidates`, `conditional_candidates`, `excluded_candidates`, comparison data, and unverified opening prerequisites. Before using its output, require `ok: true`; ensure any named recommendation is in `qualified_candidates`; and use promotion as a reason only when that candidate reports `promotion_active: true`.

The helper ranks only the facts provided to it. The executor must still write the mandatory customer-facing explanation above, including selected-account fees and documented upgrade context.

## If the customer asks to open the recommended account

First obtain a fresh confirmation of the desired account class. Then separately verify every prerequisite in the supplied opening procedure before using its documented banking tool. A recommendation, a current business account, or an account comparison does not prove opening eligibility. Do not escalate merely because opening checks have not yet been performed; ask for or obtain the documented checks through the normal authorized workflow.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Failure handling

- If no candidate is fully qualified, say that no confirmed recommendation can yet be made, list the deciding missing or failed facts, and ask only the focused clarifying question(s).
- If a promotion cannot be date-validated, ignore its ordering rather than assuming it applies.
- If a required product term is absent, do not borrow that term from another product.
- If the ranking helper reports invalid input, correct the decision record from supplied evidence rather than coercing values or inventing facts.
