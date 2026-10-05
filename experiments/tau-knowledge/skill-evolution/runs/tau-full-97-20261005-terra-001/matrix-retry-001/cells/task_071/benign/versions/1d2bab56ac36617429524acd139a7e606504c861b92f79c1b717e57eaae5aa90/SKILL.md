---
name: evidence-based-business-account-recommendations
description: Provide one focused, evidence-supported business checking and savings recommendation from supplied product materials. Use for account-selection guidance when customer requirements must be matched to documented product terms; recommend an independently confirmed account type immediately and narrowly escalate only unsupported requirements.
---

# Evidence-Based Business Account Recommendations

## Purpose and boundaries

Use this Skill to recommend accounts, not to open them or move funds. Read the full customer conversation, supplied product documents, supplied evidence, and current-time observations. Do not perform account opening, money movement, settings changes, or private-data retrieval merely because a customer asks which account to choose.

Treat checking and savings as **independent decisions**. An unsupported savings feature must not delay, replace, or invalidate a documented checking recommendation, and vice versa.

## Required decision method

Maintain a separate requirement ledger for checking and savings. Preserve requirements from every customer turn. Classify each item as:

- **Hard constraint:** must be explicitly documented as met before recommending a product.
- **Preference:** used only to choose among products that already meet all hard constraints.
- **Eligibility condition:** must be confirmed only when it is a documented condition of the candidate product or the customer asks to open an account.

For each candidate and hard constraint, record one of:

- `met` — supported by an explicit, product-specific term;
- `conflicts` — explicit product-specific evidence contradicts it; or
- `unknown` — no adequate evidence.

Never treat omitted information, a generic procedure, a different account type, another product's terms, or a customer statement as proof that a candidate meets a requirement.

### Interpretation rules

- Numeric “at least,” “up to,” and “no more than” constraints are inclusive unless the customer says otherwise.
- A mobile-deposit requirement needs an explicit daily mobile-check-deposit limit for that product.
- “No overdraft fees” needs an explicit product overdraft fee of `$0`.
- An APY requirement needs an explicit APY for the same account type at or above the requested rate.
- An ongoing minimum balance is a balance required to keep account status or access. A balance used only to waive a monthly fee is a **fee-waiver threshold**, not an ongoing minimum.
- Always disclose a material monthly fee and its waiver condition. Do not call a waiver threshold a mandatory ongoing balance.
- “Same-day ACH between checking and savings” requires documentation that the savings product supports that specific relationship and timing. Generic transfers, ordinary ACH, external-transfer timelines, internal funding, sweeps, transfer caps, or checking-only same-day ACH do not establish it.

## Mandatory checkpoint after every new requirement

Before asking another question, offering a handoff, calling a handoff tool, or saying no qualifying account is documented:

1. Update both ledgers with the complete conversation.
2. Inspect all supplied product-specific materials. Relevant terms can be distributed across documents.
3. Exclude candidates with a conflicting hard constraint. Mark candidates unconfirmed for each unknown hard constraint or required product-specific eligibility condition.
4. Identify confirmed matches: every hard constraint is `met`, no constraint conflicts, and no required product-specific eligibility is unknown.
5. For **each account type with a confirmed match**, prepare a direct named recommendation for the next substantive customer-facing response.
6. For an account type without a confirmed match, identify the exact unknown or conflicting requirement and prepare a narrow explanation and escalation for that type only.

This checkpoint is binding. In particular:

- Never say product terms are unavailable without first inspecting the supplied documents.
- Never escalate the whole request merely because one account type has an evidence gap.
- Do not defer a confirmed recommendation while collecting a preference or resolving an evidence gap for the other account type.
- A recommendation must name the documented product in the response; saying a reviewer will identify an account later is not a recommendation.

Use `scripts/evaluate_candidates.py` for normalized deterministic comparison when useful. The script filters supplied facts; it does not search documents or establish facts.

## Candidate choice and promotions

Select exactly one confirmed product per account type. Apply a promotion only after confirming all hard constraints and any required product-specific eligibility. A dated promotion is active only during its documented date range. It can rank fully confirmed products, but it cannot overcome a conflict, missing term, or unresolved eligibility.

If authoritative supplied materials conflict on a material product term, do not choose a favorable value. Explain that exact conflict and seek confirmation or escalate that account type.

## Customer-facing response requirements

For every confirmed account type, the current response must include all of the following in the same account-specific section:

1. a direct statement such as “I recommend **[exact product name]**”; 
2. the customer’s material constraints and the documented terms that meet them;
3. all material rates, fees, limits, and balance conditions;
4. an explicit statement of whether a stated balance is an ongoing minimum or only a monthly-fee waiver threshold; and
5. material operating conditions that are documented, such as required e-statements or a linked checking account.

For every unsupported account type:

1. state that the supplied materials do not verify the **exact** missing capability or condition;
2. do not name any product as satisfying that unsupported requirement;
3. offer focused human review for that account type; and
4. preserve any completed recommendation for the other type.

Use a concise structure like:

> **Checking:** I recommend **[product]**. It meets your requirements because its documented [limit], [overdraft term], and [APY] meet your stated needs. Its monthly fee is [fee], and [balance] is [an ongoing minimum / only the fee-waiver condition].
>
> **Savings:** I cannot confirm a product meeting your requirement for [exact feature], because the supplied savings materials do not document [exact missing support]. I can arrange focused human review of that requirement.

Before sending, optionally run `scripts/validate_recommendation.py` using disclosure phrases taken only from verified runtime evidence. The validator detects omitted wording; it does not validate factual claims.

## Handoffs

If the customer requests a human, provide every independently confirmed recommendation first unless the customer explicitly declines further guidance. Transfer only the unresolved portion using the normal banking handoff tool and an applicable available reason. The summary must distinguish completed recommendations from the exact unsupported requirement.

## Opening accounts after a recommendation

If the customer later explicitly asks to open an account, follow the supplied account-opening procedure. Verify every listed prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit customer authorization. Do not expose internal tool names or procedures.

## Final quality gate

Before responding, confirm:

- Every customer turn is reflected in the appropriate ledger.
- Every account type with a documented match has a named recommendation in this response.
- Checking and savings evidence gaps were handled separately.
- Limits, APY, overdraft terms, fees, and balance terminology are accurate.
- Fee-waiver thresholds were not described as ongoing minimum balances.
- Same-day ACH between savings and checking was not inferred from generic, sweep, or checking-only material.
- Promotions were applied only among fully confirmed products.
- No banking action was taken for a recommendation-only request.

## Script interfaces

### `scripts/evaluate_candidates.py`

Reads one JSON object from stdin and emits one JSON object on stdout.

```json
{
  "as_of": "optional ISO-8601 date or timestamp",
  "requirements": {
    "minimum": {"daily_mobile_deposit": 10000, "apy": 1.0},
    "maximum": {"ongoing_minimum_balance": 9999},
    "equals": {"overdraft_fee": 0}
  },
  "candidates": [
    {
      "id": "stable-id",
      "name": "Customer-facing product name",
      "facts": {"daily_mobile_deposit": 10000, "apy": 1.0, "overdraft_fee": 0},
      "eligibility": "eligible",
      "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    }
  ]
}
```

`eligibility` is `eligible`, `unknown`, or `ineligible`. A fact that is absent is `unknown`; zero is a valid fact. Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`.

### `scripts/validate_recommendation.py`

Reads:

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [{
    "account_type": "checking",
    "name": "Product name",
    "recommendation_phrase": "I recommend Product name",
    "required_phrases": ["verified disclosure phrase"]
  }],
  "unresolved": [{
    "account_type": "savings",
    "required_phrases": ["materials do not verify", "human review"]
  }]
}
```

It performs normalized case-insensitive containment checks and returns `ok`, `errors`, and `missing`. Supply phrases that actually appear in the intended response and derive them only from verified evidence.
