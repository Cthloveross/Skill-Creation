---
name: business-account-fit-recommendation
description: Recommend one documented-fit business checking and/or savings account from runtime-supplied product materials. Evaluate account types independently, disclose material terms for every confirmed recommendation, and narrowly escalate only an unverified requirement. Use for selection guidance, not account opening, funding, or transfers.
---

# Business Account Fit Recommendation

## Scope and safety

Use this Skill when a customer wants a focused business checking or savings recommendation. Read the entire conversation, supplied product documents, supplied evidence, and any supplied time observation before responding.

A recommendation is informational. Do not open an account, transfer funds, alter account settings, or retrieve private account data solely because the customer asks which product to choose.

Treat each requested account type as an independent decision. An unknown savings feature must never suppress, delay, retract, or turn into a general escalation a documented checking recommendation; the converse is also true.

## Maintain separate ledgers

Maintain a separate requirement ledger for checking and savings. Update every ledger after every customer turn, retaining all prior requirements.

Classify each statement as:

- **Hard constraint**: must be explicitly documented as met before a product can be recommended.
- **Preference**: may break a tie only among confirmed matches.
- **Opening or eligibility fact**: relevant only when opening is requested, unless the selected product itself has a documented eligibility condition.

For each candidate and each hard constraint, record `met`, `conflicts`, or `unknown`, with the product-specific source term. Absence of evidence is always `unknown`, not `met`.

Apply these interpretations:

- Numeric “at least” and “no more than” bounds are inclusive.
- A mobile-deposit requirement requires an explicit daily mobile-check-deposit limit at or above the requested amount.
- “No overdraft fee” requires a product-specific documented overdraft fee of $0.
- A checking APY requirement requires an explicit checking APY at or above the requested rate.
- An ongoing-minimum-balance limit applies to a balance required to maintain account status. A balance required only to waive a fee is a fee-waiver threshold, not an ongoing minimum.
- Disclose every material monthly fee and its waiver condition. Do not describe a fee-waiver threshold as a required ongoing minimum balance.
- “Same-day ACH between checking and savings” requires documentation that the relevant savings product supports that exact relationship-specific feature. Generic transfers, standard ACH, transfer limits, sweeps, opening-funding instructions, or same-day ACH documented only for checking do not prove it.

Do not infer customer eligibility, account status, company age, balances, product capabilities, fees, rates, or transfer timing from another product, account type, generic procedure, or the customer’s description.

## Candidate determination

Evaluate checking and savings separately:

1. Search all product-specific materials. A product’s terms can be distributed across documents.
2. Exclude a candidate with any conflicting hard constraint.
3. Mark a candidate unconfirmed if any hard constraint, material term, or required product-specific eligibility condition is unknown.
4. A candidate is a **confirmed match** only if all hard constraints are documented as met, none conflict, and no required product-specific eligibility condition is unresolved.
5. If one or more confirmed matches exist, select exactly one. Apply a current promotion only as a tie-breaker among fully confirmed matches.
6. If no confirmed match exists, identify the exact unsupported requirement and offer focused review only for that account type.

For dated promotions, compare dates with the supplied current-time observation. A promotion never overrides a hard constraint, unknown evidence, or unresolved product-specific eligibility.

## Binding completion checkpoint

After every turn that adds or changes requirements, inspect both ledgers before asking another question, saying documentation is unavailable, offering a handoff, or invoking a handoff tool.

- If an account type has a confirmed match, the next customer-facing substantive response **must explicitly recommend that product by name** and give its supporting material terms.
- A generic statement that a product is documented, that terms are available, or that a human can identify a fit does not satisfy this requirement.
- Do not wait for the other account type to be complete. Give the confirmed recommendation now and ask only the unresolved account-type question if needed.
- If later requirements make one account type unsupported, preserve the previously confirmed recommendation for the other account type and escalate only the unsupported part.
- Never state that product terms or a qualifying option are unavailable without first completing the separate ledger inspection.

When more information is genuinely needed, ask one targeted question for the unresolved account type. Do not repeat known requirements or ask the customer to compare products after a confirmed match exists.

## Customer-facing response requirements

For every confirmed account type, the recommendation message itself—not an earlier discovery question—must include:

1. The exact customer-facing product name and a direct recommendation.
2. Each material hard constraint and the product term that satisfies it.
3. Relevant rates, fees, limits, and balance conditions.
4. A clear distinction between an ongoing minimum balance and a fee-waiver threshold.
5. Any material operating condition that is documented, such as required electronic statements or a linked account requirement.

For an account type with no confirmed match:

1. State that supplied materials do not verify the exact missing feature or condition.
2. Do not name any product as satisfying that unsupported requirement.
3. Offer focused human review for that account type and exact requirement.
4. If transferring to a human, summarize the unresolved feature plus that account type’s material constraints. Use the normal handoff process and an applicable available reason code.

Use this structure, populated solely with verified runtime facts:

> **[Account type]:** I recommend **[product]**. It meets your stated needs because [documented terms]. Its monthly maintenance fee is [fee]; [balance term] is [an ongoing minimum / the condition for waiving that fee].
>
> **[Other account type]:** I cannot confirm a product meeting [exact requirement], because the supplied materials do not document [exact capability]. I can arrange focused human review of that requirement.

Never frame the second paragraph as uncertainty about the already documented recommendation.

## Draft audit and quality gate

Before sending a recommendation, audit the proposed response with `scripts/validate_recommendation.py`. Provide each confirmed account type, selected name, and disclosure anchors derived from runtime evidence. Provide each unresolved account type, unsupported requirement, and evidence-gap/review anchors. The audit detects omissions only; it never establishes facts.

Use `scripts/evaluate_candidates.py` only after extracting runtime evidence into its schema. It is a deterministic filter and does not replace document review.

Before responding, confirm:

- Each requested account type was evaluated independently from all customer turns.
- Every confirmed match is named and recommended in the current substantive response.
- The recommendation states accurate material limits, APY, fees, and balance conditions.
- A fee-waiver threshold was not relabeled as an ongoing minimum.
- Same-day ACH between savings and checking was not inferred from generic transfer material or checking-only evidence.
- Unsupported requirements received a narrow, account-type-specific escalation rather than an invented fit or whole-request refusal.
- Promotions affected only fully confirmed matches.
- No banking action was performed merely from a recommendation request.

## Opening requests after selection

If the customer later explicitly asks to open an account, follow the supplied opening procedure. Verify every listed prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or procedures.

## Failure handling

If authoritative supplied materials conflict on a material term, do not choose a value; seek confirmation or escalate that specific term. If the customer requests a human, preserve any independently confirmed recommendation and transfer only after giving it, unless the customer expressly declines further guidance.

## Candidate evaluator interface

`scripts/evaluate_candidates.py` reads one JSON object from stdin and emits one JSON object on stdout:

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

`eligibility` may be `eligible`, `unknown`, or `ineligible`. Bounds are inclusive. Output fields are `errors`, `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`.

## Recommendation-audit interface

`scripts/validate_recommendation.py` reads and writes JSON:

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [
    {"account_type": "checking", "name": "product name", "required_phrases": ["disclosure anchor"]}
  ],
  "unresolved": [
    {"account_type": "savings", "requirement": "unverified feature", "required_phrases": ["gap or review anchor"]}
  ]
}
```

Matching is normalized, case-insensitive containment. Verify all supplied anchors against runtime documents before relying on the result.
