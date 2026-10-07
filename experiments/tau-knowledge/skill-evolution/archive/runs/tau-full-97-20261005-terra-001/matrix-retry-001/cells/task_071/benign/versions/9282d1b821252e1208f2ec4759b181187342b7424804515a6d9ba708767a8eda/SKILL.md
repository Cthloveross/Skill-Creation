---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking and/or savings account from supplied product materials. Use when a customer wants a focused account choice, and separately escalate only requirements that the materials do not verify.
---

# Business Account Fit Recommendation

## Purpose and scope

Use this Skill for product recommendations, not for opening, funding, or transferring accounts. Read the full customer conversation, supplied product documents, supplied evidence, and any current-time observation before responding.

Evaluate **checking and savings independently**. An unknown savings feature does not make a documented checking recommendation unavailable, and vice versa. Never say that all product terms are unavailable merely because one requested account type or feature cannot be confirmed.

## Requirement ledger

For each requested account type, create a separate ledger before making a recommendation. Record each customer statement as one of:

- **Hard constraint**: must be satisfied to recommend the product.
- **Preference**: use only after all hard constraints are met.
- **Eligibility or opening fact**: may affect opening, but must not be assumed from the customer's current account or business description.

For every hard constraint, find the relevant product-specific document and classify each candidate as **met**, **conflicts**, or **unknown**. A product is a confirmed match only when every hard constraint is met by supplied evidence and no required product-specific eligibility condition remains unknown.

Use the words in customer requirements precisely:

- “At least” and “no more than” are inclusive numeric bounds.
- “No overdraft fees” requires an explicitly documented overdraft fee of $0.
- A stated inability to maintain a balance concerns an **ongoing required minimum balance**. A balance required only to waive a monthly fee is not an ongoing minimum balance.
- Disclose a fee-waiver threshold as a waiver condition, together with the monthly fee. Do not call it a required minimum unless the documents do.
- “Same-day ACH between checking and savings” requires evidence that the relevant savings product supports that exact relationship-specific capability. Generic transfer instructions, standard ACH, transfer limits, automatic sweeps, internal funding instructions, or same-day ACH documented only for checking do not prove it.

Do not infer verification status, account status, account tenure, account count, balances, startup age, or a product feature from a similarly named product, a general procedure, or the customer's existing account.

## Evidence-first selection procedure

Perform this procedure separately for each account type.

1. Extract all hard constraints from the complete conversation, including facts supplied across clarification turns.
2. Search the supplied product materials for each constraint. Read related documents for the same candidate when a term is distributed across multiple documents.
3. Build the candidate ledger with the exact supporting or conflicting term for each constraint. Absence of an explicit term is `unknown`, not a pass.
4. Exclude candidates with a documented conflict. Mark candidates with an unknown required term or eligibility condition as unconfirmed.
5. If one or more confirmed candidates remain, select exactly one. Apply an active promotion only as a tie-breaker among confirmed candidates.
6. If no candidate is confirmed for that account type, identify the precise requirement that cannot be verified and offer focused human review for that account type only.

A promotion never overrides a hard constraint, missing product term, or unverified eligibility condition. Check its stated dates against the supplied current time before applying it.

### Mandatory checkpoint before escalation

Before stating that terms are unavailable, recommending human review for an entire request, or sending a transfer, inspect the completed ledger for **each** requested account type:

- If an account type has a confirmed candidate, name and recommend that candidate now.
- Give the documented recommendation even if the other requested type has no confirmed candidate.
- Do not suppress a confirmed match due to a promotion candidate whose required eligibility is unknown.
- Do not describe product documentation as unavailable if the ledger contains a confirmed match with evidence for each material hard constraint.

The optional evaluator script can filter already-normalized candidates. It does not replace document reading: the executor determines the product facts, whether documents conflict, and whether a document proves a relationship-specific capability.

## Customer-facing response

Once material requirements are sufficient, give a direct result rather than another broad comparison question. The final recommendation message must contain the following sections that apply:

1. **Checking:** If checking has a confirmed candidate, explicitly name the one selected checking product. In the same final message, connect every checking hard constraint to its documented term. Include, when relevant, daily mobile-deposit capacity, overdraft fee, APY, monthly maintenance fee, and the nature of any balance condition.
2. **Savings:** Name one savings product only if all stated savings hard constraints are documented as met. State the relevant documented rate, fees, balance condition, linked-account condition, and transfer capability.
3. **Narrow evidence gap:** If savings or checking cannot be confirmed, state that the supplied materials do not verify the exact missing feature. Do not present any product as meeting that feature. Offer focused human-agent review for that unresolved account type and requirement.
4. **Material conditions:** Mention material documented conditions, such as required e-statements or a linked checking account, when they affect the recommendation.
5. **Next step:** If the customer asks to open an account, explain that account-opening eligibility must be verified first. Do not expose internal tool names.

Use clear wording such as:

> **[Account type]:** I recommend **[product]** because it provides [documented terms satisfying the hard constraints]. Its [monthly fee] is [documented fee condition]; [balance term] is a [fee-waiver threshold or ongoing minimum, as documented].
>
> **[Other account type]:** I cannot confirm a recommendation for [exact requirement], because the supplied materials do not verify [exact capability]. I can arrange focused human review of that requirement.

Only fill this structure with facts supported by the current supplied materials. The positive recommendation and the narrow escalation must remain distinct; never phrase a savings evidence gap as uncertainty about a documented checking choice.

## Final response quality gate

Before sending the response, confirm all of the following:

- Checking and savings were evaluated independently.
- Every account type with a confirmed match has an explicit, customer-facing product name.
- The final recommendation itself, not merely an earlier clarification, states the material terms supporting the named product.
- Fees, APY, limits, and balance conditions are accurate and attributed to the selected product.
- A fee-waiver threshold has not been mislabeled as an ongoing minimum balance.
- No product is said to support same-day ACH between checking and savings without evidence of that exact capability.
- Unknown features result in a precise, account-type-specific escalation rather than an invented product claim or an overall refusal.
- Promotions were used only among fully confirmed candidates and only when active.

## If the customer asks to open an account

A recommendation is not authorization to open an account. Follow the supplied opening procedure and verify all stated prerequisites before taking action. Obtain the exact official account class. Transfer opening funds only with explicit customer authorization, and disclose any documented funding deadline if the customer defers funding. Use normal banking tools only when the prerequisite checks and customer authorization permit it.

## Failure handling

- If authoritative supplied documents conflict on a material term, do not select a value; seek confirmation or escalate that term.
- If a customer asks for a human agent, or focused review is needed for an unsupported requirement, use the normal banking handoff process when appropriate and summarize the unresolved requirement and relevant constraints.
- Do not infer capabilities from product names, generic workflows, or another account type.
- Do not claim that a product is a fit based solely on a promotion or a soft preference.

## Candidate evaluator

`scripts/evaluate_candidates.py` reads one JSON object from stdin and emits one JSON object to stdout. It is optional and contains no product-specific facts.

Input schema:

```json
{
  "as_of": "optional ISO-8601 date or timestamp",
  "requirements": {
    "numeric_min": {"field": 0},
    "numeric_max": {"field": 0},
    "equals": {"field": "value"}
  },
  "candidates": [
    {
      "id": "stable identifier",
      "name": "customer-facing name",
      "facts": {"field": 0},
      "eligibility": "eligible",
      "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    }
  ]
}
```

`eligibility` is `eligible`, `unknown`, or `ineligible` and defaults to `eligible`. Numeric bounds are inclusive. Promotion rank affects only candidates without failed or unknown constraints, and only when `as_of` falls within the inclusive promotion dates.

Output schema:

```json
{
  "errors": ["input validation errors"],
  "confirmed_matches": [{"id": "...", "name": "..."}],
  "needs_confirmation": [{"id": "...", "unknown_constraints": ["..."]}],
  "excluded": [{"id": "...", "failed_constraints": ["..."]}],
  "recommended_order": ["candidate id"]
}
```

Runnable validation input:

```json
{"requirements": {}, "candidates": []}
```

Its output must be valid JSON with an empty `errors` list and empty result lists. For populated input, each ID in `recommended_order` must also occur in `confirmed_matches` and have no failed or unknown constraint. The executor must still perform the evidence ledger, mandatory checkpoint, and final response quality gate.
