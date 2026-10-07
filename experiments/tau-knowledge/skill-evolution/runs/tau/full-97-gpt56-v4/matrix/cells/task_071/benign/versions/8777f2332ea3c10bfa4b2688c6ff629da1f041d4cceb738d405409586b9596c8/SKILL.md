---
name: evidence-based-business-account-recommendation
description: Recommend one business checking and/or savings account from supplied product evidence when a customer gives feature requirements. Applies a currently active promotion only among products that independently meet every stated requirement. Use for account-selection advice; it does not itself authorize account opening or transfers.
---

# Evidence-Based Business Account Recommendation

## Purpose and boundary
Give a focused, customer-friendly recommendation based solely on the current task's product documents, customer statements, and observed time. This Skill is for **selecting** an account, not opening one. Do not verify identity, open an account, transfer money, or expose internal tools while handling an advice request. If the customer later makes a separate request to open an account, follow the applicable account-opening procedure separately; do not treat this recommendation as an authorization to do so.

## Required runtime inputs
Read the supplied public task materials at runtime:

- the opening request and all subsequent clarifications;
- product terms and any eligibility conditions;
- promotion notices, including their dates, account category, and priority order;
- a current-time observation when a promotion is relevant.

Do not rely on product names, missing facts, or facts for a different account type. Do not invent an unstated APY, balance requirement, fee, feature, eligibility outcome, or promotion date.

## Method

1. **Identify the request.** Split checking and savings into separate recommendation decisions. Determine whether the customer only wants advice or has clearly asked to take a banking action. For advice, make no banking-tool call.
2. **Collect only needed clarification.** When requirements are not yet specific, ask concise category-specific questions (for example, checking mobile-deposit needs or savings transfer speed). Do not ask about preferences that the customer has not indicated are important. Treat a later correction as replacing the earlier interpretation.
3. **Make testable requirements.** Translate explicit needs into predicates, such as `mobile_deposit_daily_limit >= 10000`, `overdraft_fee == 0`, `apy >= 1`, `same_day_ach == true`, or `domestic_wire_fee <= 15`. Apply a documented product eligibility condition only to that product and only when the customer has confirmed it. A missing fact never passes a predicate.
4. **Make evidence-backed candidate lists.** For each account category, list only products with documentation that establishes every stated predicate. Do not infer that a product has no minimum balance because a document is silent, or infer that a transfer feature applies in both directions when it says otherwise.
5. **Apply promotion correctly.** First test all requirements. Then, only if the observed calendar date falls inclusively within the notice's active dates, choose the highest-ranked qualifying product in that promotion's category-specific order. A promotion never cures a failed or undocumented requirement. Without an active promotion, select a sole qualifier only; if multiple qualify and the evidence contains no non-promotional tie-breaker, explain the tie rather than arbitrarily choosing one.
6. **Respond directly.** Lead with one account per requested category only when it is supported. Give the one or two terms that establish the fit. Mention a confirmed product-specific eligibility fact when relevant. If promotion priority selected the product, describe it as currently prioritized—not as a product feature. If no full match can be established, say exactly which term is undocumented or which requirement has no match; never promise approval or account opening.

## Recommended response shape

- “For business checking, I recommend **[account]**: [documented feature] meets your [need]. [Optional confirmed eligibility and current-priority statement.]”
- “For business savings, I recommend **[account]**: [documented feature] meets your [need].”
- If the customer is only seeking advice, optionally offer to explain the next step. Do not say an account is open.

Do not expose document IDs, internal promotion mechanics, account IDs, or internal tool names.

## Deterministic selector

`scripts/select_recommendations.py` accepts one JSON object on stdin and emits one JSON object on stdout. It is optional; the executor extracts only documented facts before using it. It never retrieves documents or takes bank actions.

### Input schema

```json
{
  "requirements": {
    "checking": [{"field": "mobile_deposit_daily_limit", "operator": ">=", "value": 10000}],
    "savings": [{"field": "same_day_ach", "operator": "==", "value": true}]
  },
  "products": [
    {"name": "Product name", "category": "checking", "facts": {"mobile_deposit_daily_limit": 25000}}
  ],
  "promotion": {
    "active_from": "YYYY-MM-DD",
    "active_to": "YYYY-MM-DD",
    "priority": {"checking": ["Product name"], "savings": ["Product name"]}
  },
  "current_time": "YYYY-MM-DDTHH:MM:SS"
}
```

`requirements`, `promotion`, and `current_time` may be omitted. Requirement operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. A fact that is absent or incompatible with an operator fails the requirement.

### Run and validate

```text
python scripts/select_recommendations.py < normalized_input.json
```

For each category, the output includes `qualifying`, `selected`, and `selection_basis`. Use `selected` only when it is non-null and appears in `qualifying`. `active_promotion_priority` means the selection was determined by an active listed promotion; `sole_qualifier` means no tie existed. `unresolved_tie` and `no_qualifier` require a transparent customer-facing explanation rather than a recommendation.
