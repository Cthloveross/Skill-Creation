---
name: evidence-based-business-account-recommendation
description: Conduct a short requirements conversation and recommend one evidence-supported business checking and/or savings account. Use an active, category-specific promotion only to prioritize products that meet all customer requirements. This is advisory account-selection support, not account opening.
---

# Evidence-Based Business Account Recommendation

## Scope
Help a customer choose business checking, business savings, or both from the supplied product evidence. This Skill ends with a recommendation. Do not verify identity, open an account, transfer funds, or make any banking-tool call for an advisory request.

## Conversation flow

Use the live conversation as the source of what the customer has actually said. If task materials contain possible clarifications, use them to understand what must be learned, but do not present an answer as though the customer has already supplied it before it appears in the dialogue.

1. When the customer says they have requirements but has not given them, ask one concise intake question covering both requested categories. For checking, invite needs such as monthly fees, mobile-deposit limits, transactions, cash, wires, integrations, or minimum balance. For savings, invite APY, expected balance, withdrawal/transfer access, fees, or minimum balance.
2. When a checking requirement is known but savings requirements are not, ask a focused savings question. When savings is known but checking is not, do the converse. Do not ask the customer to compare product options when they asked for a direct answer.
3. Before recommending a product with a documented customer-eligibility condition, ask only for the needed confirmation if it has not been provided. Never treat a condition for one product as a general condition for another.
4. After enough requirements and relevant eligibility confirmations are known, give the recommendation without asking unnecessary questions. If the available documents cannot establish a material requirement, explain that limitation instead of inventing a fit.

## Evidence and selection method

1. Keep checking and savings as independent decisions. Translate each stated need into a testable condition, for example a daily mobile-deposit limit at least a stated amount or same-day ACH availability.
2. Build each candidate list using only supplied documents. A product qualifies only when the evidence explicitly establishes every stated requirement applicable to it. A missing fact, a fact about another account category, or a product name is not evidence.
3. Read the observed current date before using a promotion. A notice applies only from its stated start date through its stated end date, inclusive.
4. If active, promotion order is only a tie-breaker among products that already qualify, and only within its stated account category. A promoted product that fails a requirement is never a recommendation.
5. If no active promotion supplies a valid selection, do not fabricate product superiority. Give the sole documented match, or clearly say that the evidence leaves multiple matches or no confirmed match.

## Customer-facing response

Lead with exactly one recommendation for each requested category when a supported selection exists. State the one or two documented terms that meet the customer’s need. If relevant, state the confirmed product-specific eligibility fact. A current promotion may be described briefly as the reason it was prioritized, never as a product feature.

Do not promise approval, account opening, funds availability, an unverified fee, or an unstated balance rule. Do not expose document IDs, internal decision details, or tool names. You may offer to help with next steps if the customer asks to proceed, but do not imply that an account has been opened.

## Optional deterministic helper

`scripts/select_recommendations.py` reads normalized evidence from JSON stdin and writes a JSON decision to stdout. It does not retrieve facts or perform banking actions. The executor must extract only explicit facts before using it.

```json
{
  "requirements": {
    "checking": [{"field": "mobile_deposit_daily_limit", "operator": ">=", "value": 10000}],
    "savings": [{"field": "same_day_ach", "operator": "==", "value": true}]
  },
  "products": [
    {"name": "Product name", "category": "checking", "facts": {"mobile_deposit_daily_limit": 0}},
    {"name": "Product name", "category": "savings", "facts": {"same_day_ach": true}}
  ],
  "promotion": {
    "active_from": "YYYY-MM-DD",
    "active_to": "YYYY-MM-DD",
    "priority": {"checking": ["Product name"], "savings": ["Product name"]}
  },
  "current_time": "YYYY-MM-DDTHH:MM:SS"
}
```

Run:

```text
python scripts/select_recommendations.py < normalized_input.json
```

`requirements`, `promotion`, and `current_time` are optional. Supported operators are `==`, `!=`, `>=`, `>`, `<=`, `<`, and `in`. Before using a result, verify that each `selected` item appears in that category’s `qualifying` list. An empty qualifying list means the customer-facing response must not claim a match.
