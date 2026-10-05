---
name: evidence-based-business-account-recommendations
description: Recommend one documented business checking and/or savings account after matching customer requirements to supplied product materials. Use when each account type must be evaluated independently and unsupported requirements need a narrow, honest human-review escalation.
---

# Evidence-Based Business Account Recommendations

## Purpose and boundaries

Use this Skill for account-selection guidance based only on the conversation, supplied product materials, supplied evidence, and supplied observations. Do not open accounts, transfer funds, retrieve private records, or change settings merely because a customer asks which account is right for them.

Treat checking and savings as separate decisions. An evidence gap for one must not suppress, delay, replace, or invalidate a documented recommendation for the other.

## Maintain independent requirement ledgers

After every customer turn, maintain a separate ledger for checking and savings. Preserve every requirement stated anywhere in the conversation, including later clarifications. Classify each as:

- a hard constraint;
- a preference; or
- a product or customer eligibility condition.

For every candidate and hard constraint, assign exactly one status:

- `met`: explicit product-specific evidence supports it;
- `conflicts`: explicit product-specific evidence contradicts it; or
- `unknown`: evidence is absent, incomplete, generic, belongs to another product, or does not establish the exact requested capability.

A product is a confirmed fit only when all stated hard constraints are `met`, none conflict, and any eligibility condition necessary to recommend that product is established. Do not infer facts from silence, generic procedures, another product type, a promotion, a customer statement, general transfer language, or account-opening instructions.

## Mandatory evidence checkpoint

Before every substantive reply, follow-up question, availability statement, or handoff proposal:

1. Re-read all requirements collected so far for **both** account types.
2. Inspect all supplied product-specific materials. Relevant terms can be split across multiple documents.
3. Re-evaluate the checking and savings ledgers independently.
4. Identify every confirmed fit and apply promotions only among those confirmed fits.
5. Include a direct named recommendation for each account type that already has a confirmed fit in the next customer-facing response.

Do not say that terms are unavailable, that no qualifying product is documented, or that the whole request needs escalation unless that conclusion follows from this checkpoint for the particular account type.

Once requirements already stated for an account type produce a confirmed fit, recommend it in the next substantive response. Do not wait for unresolved requirements about the other account type. If the customer later adds a new hard constraint for that same type, re-evaluate and correct the recommendation if needed.

## Interpret customer constraints precisely

- Interpret “at least,” “up to,” and “no more than” inclusively unless the customer specifies otherwise.
- A mobile-deposit requirement requires explicit product-specific evidence of a daily **mobile check deposit** limit.
- A no-overdraft-fee requirement requires explicit product-specific evidence that the overdraft fee is `$0`.
- An APY requirement requires an explicit APY on the same product at or above the requested rate.
- A balance required to keep an account open, in good standing, or to retain features is an **ongoing minimum balance**.
- A balance that only prevents a monthly charge is a **fee-waiver threshold**, not an ongoing minimum balance. State this distinction clearly.
- Same-day ACH specifically between checking and savings requires product-specific evidence that the proposed **savings** product supports that exact timing and relationship. Standard ACH, external transfers, transfer limits, internal opening funding, automatic sweeps, or same-day ACH documented only for checking do not establish it.

If supplied authoritative materials conflict on a material term, treat that term as unresolved rather than selecting the favorable statement.

## Selecting one product

Recommend exactly one confirmed product for each account type with a confirmed fit. If several candidates are confirmed, use a valid dated promotion only to rank them after confirming all hard constraints and required eligibility. A promotion cannot cure a conflict, missing term, or unverified eligibility.

Do not recommend a promotional product whose required eligibility is not established. Do not compare a long list when the customer asked for one focused choice.

The helper `scripts/evaluate_candidates.py` can compare facts already extracted from supplied materials. It does not search documents, resolve conflicts, establish eligibility, or prove that a generic feature satisfies an exact requirement.

## Customer-facing response requirements

Use separate, clearly labeled sections for checking and savings. For every confirmed product, in the same response state:

1. `I recommend [exact product name]`;
2. the documented feature meeting every hard constraint;
3. all relevant limits, rates, fees, and balance conditions;
4. whether each cited balance is an ongoing minimum or only a fee-waiver condition; and
5. other documented material operating conditions, such as required e-statements or linked-account requirements.

Describe facts as features of the named product, not merely as a repetition of the customer's requested values. For a product with a monthly fee and fee-waiver threshold, disclose both and do not characterize the waiver threshold as an ongoing minimum unless documents separately establish one.

Use this pattern with only runtime-supported facts:

> **Checking — recommendation:** I recommend **[product]**. Its documented [limit], [overdraft term], and [APY] meet the checking requirements you gave. Its monthly maintenance fee is [fee], waived when [threshold]. That threshold is [only a fee-waiver condition / an ongoing minimum], [plus other documented operating conditions].
>
> **Savings — status:** [Recommend one separately confirmed product, or identify the exact unverified feature and offer focused human review.]

Before sending, use `scripts/validate_recommendation.py` when practical to check that the proposed response contains the caller-supplied required disclosures. The validator checks wording only; it does not validate underlying banking facts.

## Unsupported requirements and human review

When no product is confirmed for one account type:

1. State that supplied materials do not verify the **exact** missing hard requirement.
2. Do not name any product as meeting that unsupported requirement.
3. Offer focused human review for that account type only.
4. Preserve the customer's other requirements in the handoff summary.
5. Still provide every independently confirmed recommendation for the other account type.

For unverified same-day ACH between savings and checking, expressly explain that supplied savings materials do not establish that exact capability. Do not substitute ordinary ACH, external transfers, sweeps, opening transfers, or checking-only same-day ACH as evidence.

If the customer requests a human, first give any independently confirmed recommendations unless they explicitly decline them. Use the normal handoff tool only for the unresolved portion. Confirm a transfer only after its tool result confirms success.

## Later account-opening requests

If the customer later explicitly asks to open an account, follow the supplied opening procedure. Verify every documented prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or internal procedures to the customer.

## Final quality gate

Before responding, confirm that:

- all requirements are captured in the correct account-type ledger;
- every account type with a confirmed fit has a direct named recommendation in this response;
- the named product and its supporting facts occur together in recommendation context;
- limits, APY, overdraft terms, fees, and balance distinctions are accurate;
- a savings evidence gap did not suppress a checking recommendation, or vice versa;
- promotions rank only fully confirmed, eligible candidates;
- exact same-day ACH between savings and checking was not inferred from generic evidence; and
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

`eligibility` is `eligible`, `unknown`, or `ineligible`. Missing facts are unknown, and zero is a valid fact. Output fields are `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`.

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