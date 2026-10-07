---
name: evidence-based-business-account-recommendations
description: Provide one focused, evidence-supported business checking and/or savings account recommendation from supplied product materials. Use when customer requirements must be matched to documented terms, including when one account type can be recommended while another has an unsupported requirement that needs focused human review.
---

# Evidence-Based Business Account Recommendations

## Scope and safety

Use this Skill for account-selection guidance. Read the complete conversation, supplied product materials, supplied evidence, and any supplied current-time observation. Do not open accounts, transfer money, retrieve private records, or change settings merely because a customer asks which account to choose.

Treat checking and savings as two independent decisions. Missing documentation for savings must never block, delay, retract, or turn into an escalation of a documented checking recommendation, and vice versa.

## Maintain separate requirement ledgers

After **every** customer turn, update a separate ledger for checking and savings. Preserve every requirement stated anywhere in the conversation and classify it as one of:

- hard constraint;
- preference; or
- product/customer eligibility condition.

For each candidate and hard constraint, record one status only:

- `met`: explicit, product-specific documentation supports it;
- `conflicts`: explicit, product-specific documentation contradicts it; or
- `unknown`: product-specific documentation is absent or insufficient.

A candidate is confirmed only if every stated hard constraint is `met`, none conflicts, and any product-specific eligibility condition needed for the recommendation is established. Do not infer facts from silence, another account type, a generic process, a customer statement, another product, a promotion, generic transfer language, or an opening procedure.

## Critical response-order rule

A recommendation is due as soon as the requirements already stated for that **account type** identify a confirmed fit. Do not wait for the customer to finish discussing the other account type.

Before asking any follow-up question, saying terms are unavailable, proposing a handoff, or sending another substantive response:

1. Re-read all customer requirements collected so far.
2. Inspect all supplied product-specific documents; material terms may be split across documents.
3. Re-evaluate both ledgers independently.
4. Identify confirmed candidates for each type.
5. Put a named recommendation for every confirmed type in the next customer-facing response.

This rule applies even when the next planned question concerns the other account type. For example, once checking requirements have a documented fit, the next substantive response must recommend that checking product; it must not ask another savings question first or say that all product terms are unavailable.

A later savings evidence gap is not a reason to replace a completed checking recommendation with a general escalation. If a customer adds a new checking hard constraint later, re-evaluate the named product against that new constraint and correct the recommendation if necessary.

Use `scripts/evaluate_candidates.py` only after extracting facts from the supplied runtime materials. The helper compares supplied facts; it neither searches documents nor proves eligibility.

## Interpret terms precisely

- Treat “at least,” “up to,” and “no more than” as inclusive unless the customer says otherwise.
- A mobile-deposit requirement requires an explicit daily **mobile check deposit** limit for that product.
- A no-overdraft-fee requirement requires an explicit product overdraft fee of `$0`.
- An APY requirement requires an explicit APY for that same product at or above the requested rate.
- A balance necessary to keep an account open, in good standing, or to access its features is an **ongoing minimum balance**.
- A balance that only avoids a monthly charge is a **fee-waiver threshold**, not an ongoing minimum balance. Explain this distinction in the recommendation.
- A requirement for same-day ACH specifically between checking and savings requires product-specific evidence that the proposed **savings** product supports that exact timing and relationship. Do not infer it from standard external ACH, generic transfers, transfer limits, internal opening funding, automatic sweeps, or same-day ACH documented only for checking.

If authoritative supplied materials conflict on a material term, treat the term as unresolved rather than selecting the favorable statement.

## Select one product

Recommend exactly one confirmed product for each account type that has a confirmed fit. A dated promotion may rank candidates only after every hard constraint and required eligibility condition is confirmed. A promotion cannot cure unknown terms, conflicts, or unverified eligibility.

If a promotional candidate has an eligibility condition not established by the conversation or supplied records, it is not a confirmed candidate. Do not recommend it merely because it has promotional priority.

## Required customer-facing recommendation

Use separate, clearly labeled sections for checking and savings. For every confirmed product, the same response must contain:

1. `I recommend [exact product name]`;
2. the documented fact supporting every hard constraint;
3. relevant rates, fees, limits, and balance conditions;
4. a clear statement whether a cited balance is an ongoing minimum or only a fee-waiver condition; and
5. any documented material operating condition, such as required e-statements or a linked account.

Do not merely repeat the customer’s requested values. State them as documented features of the named product. For a product with a monthly fee and waiver threshold, disclose both the fee and threshold, and do not call the waiver threshold an ongoing minimum unless documents independently say so.

Use this response shape, populated only with documented runtime facts:

> **Checking — recommendation:** I recommend **[product]**. It supports [documented deposit/transfer capability], has [documented overdraft term], and earns [documented APY], meeting the requirements you gave. Its monthly maintenance fee is [fee], waived when [threshold]. That threshold is [only a fee-waiver condition / an ongoing minimum], [plus any other documented operating condition].
>
> **Savings — status:** [recommend a separately confirmed product, or state the exact unsupported feature and offer focused human review].

## Unsupported account types and handoffs

If no product is confirmed for one account type:

1. State that supplied materials do not verify the **exact** missing requirement.
2. Do not name any product as satisfying that unsupported requirement.
3. Offer focused human review for that account type only.
4. Preserve other stated requirements in the handoff summary.
5. Still provide recommendations that are already confirmed for the other type.

For an unverified same-day-ACH-between-checking-and-savings requirement, say that supplied savings materials do not establish that exact capability. Do not represent ordinary ACH, external transfers, sweeps, opening transfers, or checking-only same-day ACH as proof.

If the customer asks for a human, provide all independently confirmed recommendations first unless they expressly decline them. Use the normal handoff tool only for the unresolved portion. Confirm that a handoff occurred only after the tool result confirms success.

## Later account-opening request

If the customer later explicitly asks to open an account, follow the supplied opening procedure. Verify every documented prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or internal procedures to the customer.

## Final quality gate

Before sending a response, verify:

- every stated requirement is in the correct ledger;
- every account type with a confirmed fit has a direct named recommendation in this response;
- the recommendation names the product alongside its supporting facts, rather than only elsewhere in the conversation;
- relevant limits, APY, overdraft terms, fees, and balance distinctions are accurate;
- an evidence gap for one type did not suppress a confirmed recommendation for the other;
- promotions ranked only fully confirmed and eligible candidates;
- same-day ACH between savings and checking was not inferred from generic transfer evidence; and
- no account opening or money movement was performed for a recommendation-only request.

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

`eligibility` must be `eligible`, `unknown`, or `ineligible`. Missing facts are unknown; zero is a valid fact. The output contains `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`.

### `scripts/validate_recommendation.py`

Reads one JSON object from stdin and writes one JSON object to stdout:

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

It performs normalized, case-insensitive containment checks and emits `ok`, `errors`, and `missing`. It checks wording presence only; it does not establish banking facts.
