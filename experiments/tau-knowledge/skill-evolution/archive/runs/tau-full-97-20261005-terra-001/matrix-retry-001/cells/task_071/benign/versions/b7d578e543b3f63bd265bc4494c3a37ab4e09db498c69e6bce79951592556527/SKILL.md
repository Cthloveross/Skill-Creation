---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking and/or savings account from supplied materials, while separately escalating only account-type-specific requirements that the evidence cannot verify. Use for focused business account selection requests; do not use it to open, fund, or transfer accounts without a later explicit request and completed eligibility checks.
---

# Business Account Fit Recommendation

## Scope

Use this Skill to give a focused product recommendation from the documents supplied at runtime. Read the complete conversation, all supplied product materials, supplied evidence, and any supplied current-time observation.

Treat checking and savings as **independent decisions**. A missing savings capability does not invalidate a documented checking recommendation, and a checking uncertainty does not invalidate a documented savings recommendation.

A product recommendation is not authorization to open an account, transfer funds, or change an account. Do not perform banking actions for a request that only asks which account to choose.

## Build a separate requirement ledger

For each requested account type, collect requirements from every customer turn and classify each as:

- **Hard constraint:** Must be documented as satisfied before recommending the product.
- **Preference:** May break a tie only after every hard constraint is satisfied.
- **Opening or eligibility fact:** Relevant only if the customer asks to open an account, unless the product itself makes it a condition of eligibility.

For each plausible candidate, mark every hard constraint as `met`, `conflicts`, or `unknown`, with the exact supporting document term. Absence of an explicit term is `unknown`, not `met`.

Interpret requirements precisely:

- “At least” and “no more than” are inclusive bounds.
- “No overdraft fees” requires a product-specific documented overdraft fee of $0.
- A request for a mobile-deposit amount requires an explicitly documented daily mobile-check-deposit limit at or above that amount.
- A request for a checking APY requires an explicitly documented checking APY at or above the requested rate.
- A customer's maximum tolerable **ongoing minimum balance** applies to a documented required minimum balance. A balance needed only to waive a monthly fee is not an ongoing minimum balance.
- Always disclose a monthly maintenance fee and its waiver condition. Do not relabel a fee-waiver threshold as a required minimum balance.
- “Same-day ACH between checking and savings” requires documentation that the relevant savings product supports that exact relationship-specific capability. Generic transfers, standard ACH timing, internal funding instructions, automatic sweeps, a transfer limit, or same-day ACH documented only for checking do not establish it.

Do not infer account status, verification, business age, tenure, account counts, balances, linked-account status, or product features from the customer's description, a similarly named product, another account type, or a generic procedure.

## Selection procedure

Complete the following separately for checking and savings after the material requirements are known.

1. Search all product-specific documents for each requirement. Product terms may be distributed across multiple documents for the same product.
2. Exclude candidates with a documented conflict.
3. Mark a candidate unconfirmed if any hard constraint or required product-specific eligibility condition is unknown.
4. A candidate is a **confirmed match** only if all hard constraints are documented as met and no required product-specific eligibility condition is unknown.
5. If one or more confirmed matches remain, choose exactly one. Use an active promotion only as a tie-breaker among confirmed matches.
6. If no confirmed match remains, identify the exact unsupported requirement and offer focused human review for that account type only.

If a promotion has dates, compare them with the supplied current time. A promotion never overrides a hard constraint, an unknown product term, or unknown candidate-specific eligibility. In particular, do not select a promoted account when its documented eligibility condition has not been established by the customer.

## Mandatory recommendation checkpoint

Before saying product terms are unavailable, recommending a human review, or initiating a handoff, inspect the completed ledger for **each requested account type**.

- If checking has a confirmed match, explicitly recommend it even if savings must be escalated.
- If savings has a confirmed match, explicitly recommend it even if checking must be escalated.
- Never escalate the entire request merely because one account type has an evidence gap.
- Do not claim documentation is unavailable when a completed ledger contains a confirmed match.
- Do not suppress a confirmed non-promotional candidate merely because a promoted candidate has an unresolved eligibility condition.

This checkpoint is mandatory. The customer-facing response must contain the confirmed recommendation before or alongside an escalation for the other account type.

## Customer-facing response

Once requirements are sufficient, respond directly rather than asking another broad comparison question. Keep the result focused on one product per account type.

For every account type with a confirmed match, state in the final recommendation message:

1. The selected product's exact customer-facing name.
2. Each material hard constraint and the product term satisfying it.
3. Material fees, rate, limits, and balance conditions relevant to the choice.
4. The distinction between an ongoing required minimum balance and a fee-waiver threshold, when applicable.
5. Any material documented operating condition, such as required paperless statements or a required linked checking account.

For an account type with no confirmed match:

1. Say that the supplied materials do not verify the exact missing capability or condition.
2. Do not name any product as satisfying that unsupported requirement.
3. Offer focused human-agent review for that account type and that exact requirement.
4. Preserve the customer's other stated constraints in the handoff summary when a handoff is made.

Use this shape, filling it only with current documented facts:

> **Checking:** I recommend **[selected checking product]**. It meets your stated needs because [documented limit], [documented overdraft term], and [documented APY]. Its monthly maintenance fee is [fee]; [balance condition] is a [fee-waiver condition or ongoing minimum balance].
>
> **Savings:** I cannot confirm a savings recommendation that meets [exact missing requirement], because the supplied materials do not document [exact missing capability]. I can arrange focused human review of that savings requirement.

The checking recommendation and savings evidence gap must remain distinct. Do not phrase a savings gap as uncertainty about a checking candidate that is already documented as a match.

## Response audit

Before sending a recommendation, create a compact normalized ledger and use `scripts/validate_recommendation.py` to audit the proposed customer-facing text.

For each confirmed recommendation, provide the product name and the exact material phrases or terms that the response must disclose. For each unresolved requirement, provide the account type, the requirement, and wording that identifies the evidence gap or human review. The script detects omitted names and required disclosure anchors; it does not replace evidence review or determine product facts.

A response is ready only when the audit reports `ok: true`, or when every reported issue has been resolved by correcting the response or the normalized audit input. Do not use the script to convert an unknown fact into a match.

## Final quality gate

Confirm all of the following before responding:

- Checking and savings were evaluated independently.
- Every account type with a confirmed match has an explicit, customer-facing product name.
- The final recommendation itself, not a prior clarification, gives the material terms supporting the named product.
- Fees, APY, limits, and balance conditions are accurate for the selected product.
- A fee-waiver threshold was not called an ongoing minimum balance.
- No product is represented as supporting same-day ACH between checking and savings without exact evidence.
- An unsupported feature produces a narrow, account-type-specific escalation rather than an invented product claim or overall refusal.
- Promotions were used only among active, fully confirmed matches.
- No account opening, funding, or transfer was performed solely because a recommendation was requested.

## If the customer later asks to open an account

Follow the supplied opening procedure. Verify all stated prerequisites before taking action, obtain the exact official account class, and use normal banking tools only after the customer expressly authorizes the action. Transfer opening funds only with explicit authorization. If the customer defers a required opening deposit, disclose any documented funding deadline.

## Failure handling

- If authoritative supplied documents conflict on a material term, do not choose between the conflicting values; obtain confirmation or escalate that specific term.
- If no candidate is documented to meet a hard constraint, say precisely which constraint is unsupported.
- If the customer asks for a human agent, or focused review is needed, use the normal handoff process when appropriate and summarize only the unresolved issue and relevant constraints.
- Do not expose internal tool names or internal procedures to the customer.

## Candidate evaluator

`scripts/evaluate_candidates.py` optionally filters candidates after the executor has normalized facts from the runtime documents. It has no embedded product facts and does not replace the requirement ledger.

It reads one JSON object from stdin and writes one JSON object to stdout.

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

`eligibility` is `eligible`, `unknown`, or `ineligible` and defaults to `eligible`. Numeric bounds are inclusive. A promotion rank affects only confirmed candidates and only when `as_of` is within the inclusive promotion dates.

The output contains `errors`, `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`. Every ID in `recommended_order` must also appear in `confirmed_matches`.

## Response-audit script

`scripts/validate_recommendation.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [
    {"account_type": "checking or savings", "name": "product name", "required_phrases": ["material disclosure anchor"]}
  ],
  "unresolved": [
    {"account_type": "checking or savings", "requirement": "unverified requirement", "required_phrases": ["evidence-gap or review anchor"]}
  ]
}
```

The output has `ok`, `errors`, `missing_recommendations`, `missing_material_phrases`, and `missing_unresolved_handling`. The phrase matching is normalized case-insensitive containment, so use it as a disclosure check after independently verifying the facts in the documents.
