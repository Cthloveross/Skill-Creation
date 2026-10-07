---
name: evidence-based-business-account-recommendations
description: Recommend one documented business checking and/or savings account by matching customer requirements to supplied product materials. Use when checking and savings must be assessed independently and an unsupported requirement requires a narrow, honest escalation.
---

# Evidence-Based Business Account Recommendations

## Purpose and scope

Use this Skill to provide account-selection guidance from the customer conversation, supplied product documents, supplied evidence, and supplied observations. The supplied product materials are available evidence even when their terms have not been repeated in the conversation. Inspect them before saying that a term is unavailable.

Do not open accounts, transfer money, retrieve private records, or change settings merely because a customer requests a recommendation. Account opening and funding require a later explicit request, authorization, and all documented prerequisite checks.

Treat checking and savings as independent decisions. Missing evidence for savings must never prevent a documented checking recommendation, and vice versa.

## Maintain two requirement ledgers

After each customer turn, update separate ledgers for `checking` and `savings`. Preserve requirements stated in the opening request and all later clarifications. Mark each requirement as one of:

- **hard constraint** — must be satisfied to recommend the account;
- **preference** — ranks otherwise confirmed fits; or
- **eligibility condition** — a condition that must be established before recommending a product that requires it.

For each candidate and each hard constraint, record one evidence status:

- `met`: explicit, product-specific evidence establishes the requirement;
- `conflicts`: explicit, product-specific evidence contradicts it; or
- `unknown`: evidence is absent, incomplete, generic, tied to another product, or does not establish the exact requested capability.

A product is a confirmed fit only if every stated hard constraint is `met`, none conflict, and every product-specific eligibility condition necessary for that recommendation is established. Never infer a fact from silence, general procedures, another account type, promotional material, or a customer statement.

## Required evidence checkpoint and response sequencing

Before every substantive response, follow-up question, availability statement, or handoff proposal:

1. Re-read the complete checking and savings ledgers.
2. Inspect all supplied product-specific materials; relevant terms may be split across several documents.
3. Re-evaluate each account type independently.
4. Identify confirmed fits and apply a valid promotion only among confirmed, eligible fits.
5. In the next customer-facing substantive response, directly recommend every account type that already has a confirmed fit.

Do not say that product terms are unavailable or that no qualifying account is documented unless the materials actually fail the checkpoint for that **specific** account type. In particular, do not replace a documented checking recommendation with an escalation because savings still needs clarification or review.

When a checking fit becomes confirmed while gathering savings requirements, give the checking recommendation immediately, then continue with the minimum necessary savings question. Do not wait for all savings requirements to be resolved.

Before giving a final answer after requirements are complete, perform a final independent evaluation. If checking is confirmed and savings has an evidence gap, the final response must contain both the named checking recommendation and a separate savings evidence-gap explanation.

## Interpret constraints exactly

- Treat “at least,” “up to,” and “no more than” as inclusive unless the customer says otherwise.
- A mobile-deposit requirement needs explicit evidence for a daily **mobile check deposit** limit on the candidate product.
- A zero-overdraft-fee requirement needs explicit evidence that the candidate product's overdraft fee is `$0`.
- An APY requirement needs an explicit APY for the same product at or above the requested rate.
- A balance required to keep an account open, in good standing, or to retain account features is an **ongoing minimum balance**.
- A balance that only avoids a monthly maintenance charge is a **fee-waiver threshold**, not an ongoing minimum balance. Disclose the distinction clearly.
- Same-day ACH specifically between checking and savings needs product-specific evidence that the proposed **savings** product supports that exact timing and relationship. Standard ACH, external transfer timing, transfer limits, opening funding, automatic sweeps, or same-day ACH documented only for checking do not prove it.

If authoritative supplied materials conflict on a material product term, treat that term as unresolved; do not select the more favorable statement.

## Select one focused product

Recommend exactly one confirmed product per account type. If multiple products are confirmed, a currently valid promotion may rank them only after every hard constraint and required eligibility condition has been confirmed. A promotion cannot cure missing evidence, a conflicting term, or unknown eligibility.

Do not recommend a promotional product with an unestablished required eligibility condition. Do not give a broad comparison when the customer asked for one focused recommendation.

Use `scripts/evaluate_candidates.py` for deterministic comparison of facts already extracted from the supplied materials. It does not read documents, resolve conflicting documents, infer facts, or establish eligibility.

## Customer-facing recommendation standard

Use separate, plainly labeled checking and savings sections. For each confirmed fit, put the exact product name and material disclosures together in the same recommendation context. State:

1. `I recommend [exact product name]`;
2. the product-specific feature satisfying every hard constraint;
3. applicable limits, rates, fees, and balance conditions;
4. whether a cited balance is an ongoing requirement or only a fee-waiver condition; and
5. relevant operating conditions documented for that product, such as required paperless statements or linked-account requirements.

Describe facts as characteristics of the named product, not merely as a restatement of what the customer requested. If a monthly fee exists, disclose both the fee and how it may be waived. Never call a fee-waiver threshold an account-status minimum unless the documents separately say so.

Use this structure with facts derived at runtime:

> **Checking — recommendation:** I recommend **[product]**. It supports [documented mobile-deposit limit], has [documented overdraft term], and earns [documented APY], which meet the checking requirements you gave. Its monthly maintenance fee is [fee], waived when [threshold]. That threshold is [only a fee-waiver condition / an ongoing minimum], [plus other documented operating conditions].
>
> **Savings — recommendation or status:** [Recommend one separately confirmed product, or identify the exact unsupported requirement and offer focused human review.]

Before sending, use `scripts/validate_recommendation.py` when practical. Supply the exact recommendation and disclosure phrases derived from the current materials. The validator checks wording only and never validates banking facts.

## Unsupported requirements and human review

When no product is confirmed for one account type:

1. State that the supplied materials do not verify the **exact** missing hard requirement.
2. Do not name a product as satisfying that unsupported requirement.
3. Offer focused human review for that account type only.
4. Preserve the customer's other requirements in the handoff summary.
5. Still give every independently confirmed recommendation for the other account type.

For unverified same-day ACH between savings and checking, expressly say that the available savings materials do not establish same-day ACH between those account types. Do not substitute ordinary ACH, external transfers, sweeps, opening transfers, or checking-only same-day ACH as proof.

If the customer asks to transfer to a human, first provide any independently confirmed recommendations unless they explicitly decline them. Use the normal handoff tool only for the unresolved portion and confirm a successful transfer only after a successful tool result.

## Later requests to open or fund an account

If the customer later explicitly asks to open an account, follow the supplied opening procedure. Verify every documented prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or internal procedures to the customer.

## Final quality gate

Before responding, confirm all of the following:

- Every requirement is captured in the appropriate checking or savings ledger.
- Every account type with a confirmed fit has a direct named recommendation in this response.
- The product name and its supporting facts occur together in recommendation context.
- Limits, APY, overdraft terms, fees, and balance distinctions are accurate.
- An evidence gap for one account type did not suppress the other account type's recommendation.
- Promotions rank only fully confirmed and eligible products.
- Exact same-day ACH between savings and checking was not inferred from generic or checking-only evidence.
- No account opening or money movement occurred for a recommendation-only request.

## Script interfaces

### `scripts/evaluate_candidates.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

```json
{
  "as_of": "optional ISO-8601 date or timestamp",
  "requirements": {
    "minimum": {"daily_mobile_deposit": 10000, "apy": 1.0},
    "maximum": {"ongoing_minimum_balance": 9999},
    "equals": {"overdraft_fee": 0}
  },
  "candidates": [{
    "id": "stable-id",
    "name": "Customer-facing product name",
    "facts": {"daily_mobile_deposit": 10000, "apy": 1.0, "overdraft_fee": 0},
    "eligibility": "eligible",
    "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
  }]
}
```

`eligibility` is `eligible`, `unknown`, or `ineligible`; missing facts are unknown and zero is valid. Output fields are `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`.

### `scripts/validate_recommendation.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [{
    "account_type": "checking",
    "name": "Product name",
    "recommendation_phrase": "I recommend Product name",
    "required_phrases": ["documented disclosure phrase"]
  }],
  "unresolved": [{
    "account_type": "savings",
    "required_phrases": ["materials do not verify", "human review"]
  }]
}
```

It performs normalized, case-insensitive containment checks and emits `ok`, `errors`, and `missing`.
