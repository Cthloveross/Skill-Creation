---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking and/or savings account from supplied materials. Evaluate each account type independently, disclose the selected product's material terms, and narrowly escalate only requirements the supplied evidence cannot verify. Use for product-selection guidance, not account opening, funding, or transfers.
---

# Business Account Fit Recommendation

## Scope and safety

Use this Skill for a customer who wants a focused business account recommendation from the materials supplied at runtime. Read the full conversation, all supplied product documents and evidence, and any supplied current-time observation.

A recommendation is not authorization to open an account, transfer money, change an account, or disclose account information. Do not take banking actions solely because the customer asks which product to choose.

Treat **checking and savings as independent decisions**. An evidence gap for savings must not prevent a documented checking recommendation, and vice versa.

## Maintain separate requirement ledgers

Create a distinct ledger for every requested account type. Update the ledgers after **every** customer turn, using all prior turns rather than only the most recent reply.

Classify each customer statement as one of:

- **Hard constraint:** Must be explicitly documented as satisfied before recommending a product.
- **Preference:** May break a tie only after all hard constraints are satisfied.
- **Opening or eligibility fact:** Relevant to opening only, unless the product itself explicitly makes it an eligibility condition for the recommendation.

For every plausible candidate, record each hard constraint as `met`, `conflicts`, or `unknown`, with the exact product-specific supporting term. Missing evidence is `unknown`, never `met`.

Interpret requirements precisely:

- “At least” and “no more than” are inclusive numeric bounds.
- A mobile-deposit requirement needs an explicit daily mobile-check-deposit limit at or above the requested amount.
- “No overdraft fee” needs a product-specific documented overdraft fee of $0.
- A checking APY requirement needs an explicit checking APY at or above the requested rate.
- A maximum acceptable **ongoing minimum balance** applies to an actual required balance for account status. A balance required only to waive a monthly fee is a fee-waiver threshold, not an ongoing minimum balance.
- Always disclose a material monthly maintenance fee and its waiver condition. Never relabel a waiver threshold as an ongoing minimum balance.
- “Same-day ACH between checking and savings” needs documentation that the relevant savings product supports that exact relationship-specific capability. Generic transfers, a transfer limit, standard ACH timing, automatic sweeps, opening-funding instructions, or same-day ACH documented only for checking do not establish it.

Do not infer eligibility, account status, verification, business age, tenure, balances, linked-account status, product capability, or rate from the customer’s description, another product, another account type, or a generic procedure.

## Evaluate each account type independently

For checking and savings separately:

1. Search all product-specific materials. Terms for one product may be distributed across several documents.
2. Exclude a candidate that conflicts with any hard constraint.
3. Mark a candidate unconfirmed if any hard constraint, material product term, or required product-specific eligibility condition is unknown.
4. A candidate is a **confirmed match** only when every hard constraint is documented as met, no hard constraint conflicts, and no required product-specific eligibility condition is unresolved.
5. When one or more confirmed matches exist, select exactly one. Use an active promotion only as a tie-breaker among fully confirmed matches.
6. When no confirmed match exists, identify the exact unsupported constraint and arrange or offer focused review for that account type only.

When a promotion has dates, compare them with the supplied current time. A promotion never overrides a hard constraint, an unknown term, or unknown product-specific eligibility. Do not recommend a promoted product whose documented eligibility condition has not been established.

## Per-turn decision checkpoint

After each turn that supplies or changes requirements, check the ledgers immediately.

- As soon as one account type has a confirmed match, prepare an explicit recommendation for that account type.
- Do not wait for the other account type’s requirements to be complete before recommending the confirmed match.
- If later information creates an unsupported requirement for the other account type, preserve the already confirmed recommendation; escalate only the unsupported account type.
- Before saying that terms are unavailable, before offering a general handoff, and before calling a handoff tool, inspect each ledger separately.
- Never claim that documentation is unavailable if the relevant ledger contains a confirmed match.
- Never escalate the entire request merely because one requested account type has an evidence gap.

If more information is needed, ask only a targeted question for the account type that remains unresolved. Do not repeat requirements already known or ask the customer to compare products after a documented match is available.

## Customer-facing recommendation

Once an account type has a confirmed match, give a direct, focused recommendation. The recommendation itself—not an earlier clarification—must include:

1. The exact customer-facing product name.
2. Every material hard constraint and the term that satisfies it.
3. Relevant rates, fees, limits, and balance conditions.
4. A clear distinction between any ongoing minimum balance and any fee-waiver threshold.
5. Any material documented operating condition, such as required paperless statements or a required linked checking account.

For an account type with no confirmed match:

1. State that the supplied materials do not verify the exact missing capability or condition.
2. Do not name a product as satisfying the unsupported requirement.
3. Offer focused human review for that account type and exact missing requirement.
4. If a handoff is made, include the unresolved requirement and the customer’s other material constraints in the handoff summary.

Use a response structure like this, populated only with verified runtime facts:

> **Checking:** I recommend **[checking product]**. It meets your stated needs because [documented limit], [documented overdraft term], and [documented APY]. Its monthly maintenance fee is [fee], and [balance condition] is [an ongoing minimum balance / a condition for waiving that fee].
>
> **Savings:** I cannot confirm a savings product that meets [exact requirement], because the supplied materials do not document [exact capability]. I can arrange focused human review of that savings requirement.

Do not frame a savings evidence gap as uncertainty about an already documented checking recommendation.

## Response audit

Before sending the final customer-facing response, normalize the independently completed ledgers and audit the draft with `scripts/validate_recommendation.py`.

For each confirmed recommendation, provide its account type, product name, and exact material disclosure anchors. For each unresolved account type, provide the unsupported requirement and evidence-gap or review wording that must appear. The script checks omissions only; it does not establish product facts or turn unknown evidence into a match.

A draft is ready only when the audit returns `ok: true`, or all reported omissions have been corrected. Use `scripts/evaluate_candidates.py` only after extracting runtime facts into its input schema; it is a deterministic filter, not a substitute for document review.

## Final quality gate

Confirm before responding that:

- Checking and savings were evaluated separately using all customer turns.
- Every account type with a confirmed match is explicitly recommended by name.
- A recommendation is not delayed, withdrawn, or hidden because another account type is unresolved.
- The final recommendation message includes the material terms supporting the named product.
- Fees, APY, limits, and balance conditions are accurate for the selected product.
- A fee-waiver threshold was not described as an ongoing minimum balance.
- No savings product is said to support same-day ACH between checking and savings without exact evidence.
- Unsupported features produce a narrow account-type-specific escalation, not an invented claim or general refusal.
- Promotions were used only among active, fully confirmed matches.
- No account opening, funding, or transfer was performed solely from a recommendation request.

## Opening requests after a recommendation

If the customer later asks to open an account, follow the supplied opening procedure. Verify every stated prerequisite, obtain the exact official account class, and use normal banking tools only after explicit authorization. Transfer opening funds only with explicit authorization. If the customer defers required funding, disclose any documented funding deadline. Do not expose internal tool names or internal procedures to the customer.

## Failure handling

- If authoritative supplied documents conflict on a material term, do not choose between the values; seek confirmation or escalate that specific term.
- If no candidate is documented to meet a hard constraint, identify that constraint precisely.
- If focused review is necessary or the customer requests a human, use the normal handoff process when appropriate and summarize only the unresolved issue and relevant constraints.
- Do not infer unsupported facts to avoid an escalation.

## Candidate evaluator

`scripts/evaluate_candidates.py` reads one JSON object from stdin and writes one JSON object to stdout. It accepts normalized facts extracted from runtime material and has no embedded product facts.

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

`eligibility` is `eligible`, `unknown`, or `ineligible` and defaults to `eligible`. Numeric bounds are inclusive. The output includes `errors`, `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`. Promotion rank affects only confirmed candidates with an active dated promotion.

## Response-audit script

`scripts/validate_recommendation.py` reads one JSON object from stdin and emits one JSON object to stdout.

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

The output has `ok`, `errors`, `missing_recommendations`, `missing_material_phrases`, and `missing_unresolved_handling`. Matching is normalized case-insensitive containment. Independently verify all facts from the supplied documents before using the result.
