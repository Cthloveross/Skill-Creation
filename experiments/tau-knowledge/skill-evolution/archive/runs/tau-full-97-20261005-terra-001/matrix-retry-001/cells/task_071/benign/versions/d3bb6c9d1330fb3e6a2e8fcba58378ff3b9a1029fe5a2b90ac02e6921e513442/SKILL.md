---
name: business-account-fit-recommendation
description: Provide focused, evidence-based business checking and savings recommendations from supplied product materials. Use when a customer wants account-selection guidance; evaluate account types independently, recommend every documented fit immediately, and narrowly escalate only unsupported requirements.
---

# Business Account Fit Recommendation

## Scope

Use this Skill for informational account-selection guidance. Read the full conversation, runtime-supplied product materials, evidence, and current-time observations before responding.

Do **not** open accounts, move money, change settings, retrieve private account data, or otherwise perform a banking action merely because the customer requests a recommendation.

Treat checking and savings as separate decisions. Missing evidence for one account type must never prevent a documented recommendation for the other.

## Requirement ledgers

Maintain a distinct ledger for each requested account type. After each customer turn, preserve prior requirements and classify each new item as:

- **Hard constraint**: must be explicitly documented for a product to be recommended.
- **Preference**: may choose among already confirmed matches only.
- **Eligibility/opening fact**: relevant when opening is requested, or when a candidate has a documented product-specific eligibility condition.

For every candidate and hard constraint, record `met`, `conflicts`, or `unknown` and the exact supporting product term. Missing evidence is always `unknown`, never `met`.

Apply these rules:

- Numeric bounds such as “at least” and “no more than” are inclusive.
- A mobile-deposit requirement needs an explicit product daily mobile-check-deposit limit at or above the requested amount.
- “No overdraft fee” requires a documented product overdraft fee of $0.
- A checking APY requirement needs an explicit checking APY at or above the requested rate.
- A limit on an ongoing minimum balance concerns a balance required to maintain account status. A balance needed only to waive a monthly fee is a fee-waiver threshold, not an ongoing minimum.
- State every material monthly fee and its waiver condition. Never relabel a fee-waiver threshold as an ongoing minimum.
- “Same-day ACH between checking and savings” needs documentation that the relevant savings product supports that exact relationship-specific capability. Generic transfers, standard ACH, transfer limits, sweeps, funding instructions, or checking-only same-day ACH do not establish it.

Do not infer capability, rate, fee, timing, eligibility, account status, company age, or balance from a different product, account type, generic procedure, or customer statement.

## Mandatory decision checkpoint

Run this checkpoint after **every** turn that adds or changes requirements, before asking another question, offering a handoff, calling a handoff tool, or saying terms are unavailable.

1. Update both ledgers from all conversation turns.
2. Search all supplied product-specific materials; terms may be distributed across documents.
3. For each account type, exclude candidates with a conflicting hard constraint and mark candidates unconfirmed for any unknown hard constraint, material term, or required product-specific eligibility condition.
4. A candidate is a confirmed match only when every hard constraint is documented as met, none conflict, and required product-specific eligibility is established.
5. For each account type with one or more confirmed matches, select exactly one and prepare a recommendation **in the next substantive customer-facing response**.
6. For an account type with no confirmed match, identify the precise unsupported requirement and prepare a narrow escalation for that account type only.

This checkpoint is binding:

- If checking has a confirmed match, explicitly name and recommend it even when savings remains incomplete or unsupported.
- If savings has a confirmed match, explicitly name and recommend it even when checking remains incomplete or unsupported.
- Never make a whole-request escalation when only one ledger lacks a confirmed match.
- Do not defer a completed recommendation while collecting a preference for the other account type.
- Do not state that product terms or a qualifying option are unavailable until both ledgers have been inspected.

When information is genuinely needed, ask one targeted question only for the unresolved account type; do not repeat known requirements.

## Candidate selection

Use `scripts/evaluate_candidates.py` after normalizing evidence into its input schema. It is a deterministic filter and does not substitute for reviewing supplied documents.

Apply promotions only after identifying confirmed matches. A dated promotion is active only if the supplied time falls in its documented date range. It may prioritize among fully confirmed matches, but never overrides a hard constraint, unresolved eligibility, or missing evidence.

If authoritative supplied materials conflict on a material term, do not select a value; seek confirmation or escalate that exact conflict.

## Response construction and disclosure

For a confirmed account type, the current recommendation message itself must contain:

1. a direct recommendation and exact product name;
2. each material customer constraint and the documented product term satisfying it;
3. material rates, fees, limits, and balance conditions;
4. an explicit distinction between any ongoing minimum and any fee-waiver threshold; and
5. material documented operating conditions, such as required electronic statements or a linked-account requirement.

For an account type with no confirmed match:

1. say the supplied materials do not verify the exact missing feature or condition;
2. do not name any product as meeting that unsupported requirement;
3. offer focused human review for that account type and requirement; and
4. if transferring, preserve the other account type’s completed recommendation and summarize the unresolved feature plus material constraints for the reviewer.

Use `scripts/build_response.py` when a structured response is useful. Supply only facts verified from runtime materials. Its output is a draft, not evidence and not a banking action.

Use `scripts/validate_recommendation.py` as a final omission check. For every confirmed recommendation, include a `recommendation_anchor` such as a direct recommendation phrase plus separate anchors for all material terms. For every unresolved type, include evidence-gap and review anchors. Do not send a draft if the audit reports a missing recommendation or disclosure.

A suitable response structure is:

> **Checking:** I recommend **[product]**. It meets your needs because [documented limits, fees, APY, and balance terms]. Its monthly maintenance fee is [fee]; [balance term] is [an ongoing minimum / only the condition for waiving that fee].
>
> **Savings:** The supplied materials do not verify [exact capability]. I cannot confirm a savings product meeting that requirement and can arrange focused human review.

Do not frame the savings evidence gap as uncertainty about a separately documented checking recommendation.

## Human handoffs

If the customer requests a human, first provide every independently confirmed recommendation unless they expressly decline further guidance. Transfer only the unresolved portion using the normal handoff process and an available applicable reason code. A handoff summary must distinguish confirmed recommendations from unverified requirements.

## Opening after selection

If the customer later explicitly asks to open an account, follow the supplied opening procedure. Verify all listed prerequisites, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or procedures.

## Final quality gate

Before sending, confirm:

- Both account-type ledgers include every customer turn.
- Each completed ledger has a named recommendation in this response.
- Limits, APY, overdraft terms, fees, and balance terminology are accurate.
- A fee-waiver threshold is not described as an ongoing minimum.
- Same-day ACH between savings and checking was not inferred from generic or checking-only material.
- Every escalation is limited to the unsupported account type and exact evidence gap.
- Promotions were applied only among fully documented matches.
- No account-opening or funds-transfer action was taken for a recommendation request.

## Script interfaces

### `scripts/evaluate_candidates.py`

Reads one JSON object from stdin and writes one JSON object to stdout:

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

`eligibility` is `eligible`, `unknown`, or `ineligible`. Bounds are inclusive. Output fields are `errors`, `confirmed_matches`, `needs_confirmation`, `excluded`, and `recommended_order`.

### `scripts/build_response.py`

Reads a structured list of verified recommendations and unresolved requirements and returns `{ "response": "...", "errors": [...] }`. It does not validate claims; all fields must come from runtime evidence.

### `scripts/validate_recommendation.py`

Reads:

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [
    {
      "account_type": "checking",
      "name": "product name",
      "recommendation_anchor": "I recommend product name",
      "required_phrases": ["verified disclosure anchor"]
    }
  ],
  "unresolved": [
    {
      "account_type": "savings",
      "requirement": "unverified feature",
      "required_phrases": ["evidence-gap anchor", "human-review anchor"]
    }
  ]
}
```

Matching is normalized, case-insensitive containment. Output reports omissions; it never establishes facts.
