---
name: evidence-based-business-account-recommendations
description: Select one documented business checking and/or savings account from supplied product evidence, independently evaluate each account type, disclose material terms, and narrowly escalate only requirements that available evidence cannot verify.
---

# Evidence-Based Business Account Recommendations

## Scope

Use this Skill for a customer who wants a focused business checking or savings recommendation from the supplied conversation, product documents, and current observations.

A recommendation request is informational only. Do **not** open an account, move money, retrieve customer data, alter settings, or perform verification unless the customer later makes a separate explicit request that requires that action.

Product documents supplied with the task are evidence. Review them before claiming that a term, feature, or qualifying account is unavailable.

## Maintain independent requirement ledgers

Keep two separate ledgers, one for `checking` and one for `savings`. Update them after every customer message. Include requirements from the opening request and all later clarifications.

For each requirement, record:

- `kind`: `hard`, `preference`, or `eligibility`;
- `meaning`: the exact requested condition, including direction and threshold;
- `evidence`: `met`, `conflicts`, or `unknown` for each candidate; and
- document support or the reason evidence is missing.

Do not carry a savings evidence gap into the checking ledger, or vice versa. A product is a confirmed fit only when every hard condition is explicitly `met`, no hard condition conflicts, and product-specific eligibility needed for that product is established.

Classify an expressed must-have, non-negotiable condition, maximum, minimum, or required feature as hard. Treat a stated preference such as a desired rate as hard only when the customer makes it mandatory; otherwise use it to rank confirmed fits.

## Evidence rules

Use only explicit, product-specific evidence for material terms. Never infer a fact from silence, a generic account-opening procedure, a different account type, a different product, an unrelated feature, or a promotion.

Apply these interpretations:

- “At least,” “up to,” and “no more than” are inclusive.
- A mobile-deposit requirement needs a stated daily **mobile check deposit** limit for the same candidate.
- A zero-overdraft requirement needs a stated `$0` overdraft fee for the same candidate.
- An APY requirement needs a stated APY for the same candidate at or above the requested rate.
- A balance needed to keep an account open, in good standing, or retain features is an ongoing minimum balance.
- A balance that only avoids a monthly maintenance fee is a fee-waiver threshold, not an ongoing minimum balance.
- If sources materially conflict for a product term, mark that term unresolved rather than choosing the favorable source.
- Same-day ACH between business savings and checking requires explicit evidence that the proposed **savings** product supports that exact capability. Standard ACH timing, generic transfers, external transfers, transfer limits, opening funding, automatic sweeps, and a checking-only same-day-ACH feature do not establish it.

## Mandatory decision checkpoint

Before every substantive response after receiving a requirement, do the following:

1. Re-read both complete ledgers, including all prior clarifications.
2. Inspect all supplied product evidence. Relevant facts may be split over multiple documents.
3. Determine confirmed, excluded, and unresolved candidates for each account type independently.
4. Apply a valid promotion only among candidates that already meet every hard condition and have established eligibility.
5. In the next substantive customer-facing response, name and recommend every account type that has a confirmed fit.

This checkpoint is mandatory even if another account type still needs a question or human review. Never state that product terms are unavailable when supplied documents establish the relevant terms.

In particular, once checking has a confirmed fit, recommend it immediately. Do not delay it until savings requirements are complete, and do not replace it with a whole-request escalation.

## Promotions and eligibility

A promotion ranks candidates; it never changes a product term or cures missing evidence. A promotional candidate must still meet all customer hard requirements.

If a candidate has an additional eligibility condition, such as business age, and that condition is not established by supplied evidence, mark that candidate `unknown` rather than selecting it merely because it has promotional priority. Select the best fully documented eligible fit instead.

## Produce one focused recommendation

Recommend exactly one product for each account type that has a confirmed fit. Do not provide a broad comparison when the customer asked for one choice.

For each recommendation, use a plainly labeled section and put the name and material terms together. State:

1. `I recommend [exact product name]`.
2. How its documented terms meet every hard condition.
3. Material limits, APY, overdraft terms, fees, and balance terms.
4. Whether a disclosed balance is an ongoing minimum or only a fee-waiver condition.
5. Other documented operational conditions relevant to the recommendation, such as required paperless statements or linked-account requirements.

Describe these as product facts, not as a repeated list of customer requirements. If the product has a monthly fee, disclose both the amount and the waiver condition. Do not describe a fee-waiver threshold as a required balance unless the evidence independently establishes an ongoing minimum.

Use this response shape, populated only with facts established at runtime:

> **Checking — recommendation:** I recommend **[product]**. Its [limit], [overdraft term], and [APY] meet the checking requirements you gave. Its monthly maintenance fee is [fee], waived when [threshold]. The [threshold] is [only a fee-waiver condition / an ongoing account-status requirement].
>
> **Savings — recommendation or status:** [Name one independently confirmed savings fit, or identify the exact unverified hard condition and offer focused review.]

## Unsupported requirements and handoff

If an account type has no confirmed candidate:

1. Identify the exact hard requirement that the supplied materials do not verify.
2. Do not name a product as satisfying that unsupported requirement.
3. Offer human review for that account type only.
4. Preserve all other requirements in the handoff summary.
5. Still deliver any confirmed recommendation for the other account type in the same response.

For an unverified savings same-day-ACH requirement, state clearly that the supplied savings materials do not establish same-day ACH **between savings and checking**. Do not substitute ordinary ACH, sweeps, external-transfer information, or checking-only same-day ACH.

If the customer requests a human transfer, first provide any independently confirmed recommendation unless the customer expressly declines it. Use the normal handoff tool for only the unresolved portion. Confirm a transfer only after its tool result is successful. Choose a reason supported by the available transfer reason enum; use `customer_requests_human_no_specific_reason` for a customer-requested review without a more specific supported reason.

## Later account-opening requests

A later explicit request to open or fund an account is a different workflow. Follow the supplied opening procedure, verify every documented prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Transfer opening funds only with explicit authorization. Do not expose internal tool names or procedures to the customer.

## Quality gate

Before sending a response, verify:

- Every requirement is in the correct ledger.
- Every independently confirmed account type is directly recommended in this response.
- The recommendation names the product and states its supporting material facts together.
- Mobile-deposit limits, APY, overdraft terms, fees, and balance distinctions match the supplied evidence.
- A promotion was considered only after fit and eligibility were established.
- An evidence gap in one account type did not suppress the other recommendation.
- Same-day ACH between savings and checking was not inferred from weaker evidence.
- No account opening, transfer, or other banking action was taken for recommendation-only guidance.

## Script interfaces

### `scripts/evaluate_candidates.py`

Reads one JSON object from stdin and writes one JSON object to stdout. Supply only facts already extracted from runtime product evidence; the script does not read documents, infer missing facts, resolve source conflicts, or establish eligibility.

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

Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`. `eligibility` must be `eligible`, `unknown`, or `ineligible`. Missing facts are unknown; numeric zero is valid.

### `scripts/validate_recommendation.py`

Reads one JSON object from stdin and writes one JSON object to stdout. It checks that caller-supplied recommendation and escalation phrases occur in a proposed response; it does not validate the underlying banking facts.

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

It emits `ok`, `errors`, and `missing`. Use it as an omission check after deriving all phrases from the current supplied evidence.
