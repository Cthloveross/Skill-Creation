---
name: evidence-based-business-account-recommendations
description: Give focused, evidence-supported business checking and savings account recommendations from supplied product materials. Use when customer requirements must be matched to documented terms, including situations where one account type has a confirmed fit and the other needs a narrow escalation.
---

# Evidence-Based Business Account Recommendations

## Scope

Use this Skill for account-selection guidance only. Read the complete conversation, supplied product documents/evidence, and any supplied current-time observation. Do not open accounts, transfer funds, retrieve private data, or change settings merely because the customer asks for a recommendation.

Evaluate business checking and business savings **separately**. A documentation gap for savings never permits withholding, retracting, or escalating a documented checking recommendation; the converse is also true.

## Build two requirement ledgers

Keep a separate ledger for each account type and update it after every customer turn. Preserve all requirements stated anywhere in the conversation. Mark each item as a hard constraint, preference, or eligibility condition.

For every candidate and hard constraint, record exactly one status:

- `met`: an explicit product-specific source supports it;
- `conflicts`: an explicit product-specific source contradicts it; or
- `unknown`: adequate product-specific support is absent.

A candidate is confirmed only when every hard constraint is `met`, none conflicts, and any product-specific eligibility required for the recommendation is confirmed. Do not infer a fact from silence, general onboarding procedures, another account type, another product, a customer statement, a generic transfer feature, or a promotional notice.

## Interpret terms accurately

- Treat numeric “at least,” “up to,” and “no more than” constraints as inclusive unless the customer says otherwise.
- A mobile-deposit requirement needs an explicit daily **mobile check deposit** limit for that product.
- “No overdraft fees” needs an explicit product overdraft fee of `$0`.
- An APY requirement needs an explicit APY for the same product at or above the requested rate.
- A balance necessary to keep an account open, in good standing, or to access its features is an **ongoing minimum balance**.
- A balance that merely prevents a monthly charge is a **fee-waiver threshold**, not an ongoing minimum balance. State that distinction clearly.
- A request for same-day ACH specifically between checking and savings needs evidence that the proposed **savings** product supports that exact timing and account relationship. Do not infer it from standard ACH, external transfers, transfer limits, internal opening funding, automatic sweeps, or checking-only same-day ACH.

If authoritative materials conflict on a material term, treat that term as unresolved rather than selecting the more favorable statement.

## Mandatory decision checkpoint

Before asking another question, saying terms are unavailable, offering/escalating a handoff, or responding substantively after receiving a requirement:

1. Update both ledgers from the entire conversation.
2. Inspect all supplied product-specific materials; terms may be split across documents.
3. Exclude conflicts and identify all confirmed candidates for each account type.
4. For each type with a confirmed candidate, prepare a named recommendation immediately.
5. For each type without one, identify the exact unsupported or conflicting requirement.

This is a response-order rule: once one account type has a confirmed fit, give that recommendation in the **next substantive customer-facing response**, even if questions remain or evidence is missing for the other account type. Do not ask another question about savings before delivering an already-confirmed checking recommendation, unless the customer expressly asks to defer checking guidance.

Never state that product terms are unavailable without performing this inspection. Never replace a named confirmed recommendation with “a human will identify an account later.”

Use `scripts/evaluate_candidates.py` only after extracting product facts from the supplied runtime materials. The script compares supplied facts; it does not search documents, resolve ambiguity, or prove eligibility.

## Choosing one product

Recommend exactly one confirmed product for an account type. A dated promotion may rank candidates only after all their hard constraints and required eligibility conditions are confirmed. It cannot overcome unknown terms, conflicts, or unverified eligibility. Use the supplied time only to determine whether a dated promotion is active.

If a candidate has an eligibility condition not established in the conversation or records, it is not a confirmed candidate. Do not choose it solely because a promotion ranks it first.

## Required recommendation content

For each confirmed account type, use a distinct labeled section and include, in that section:

1. a direct statement: `I recommend [exact product name]`;
2. the documented facts that meet each customer hard constraint;
3. all material rates, fees, limits, and balance conditions relevant to the choice;
4. an explicit explanation of whether each stated balance is an ongoing minimum or only a fee-waiver condition; and
5. any material operating condition documented for the product, such as mandatory e-statements or a required linked account.

The named product and its supporting material terms must appear together in the recommendation response. Do not merely repeat the customer’s requested numbers as questions or unsupported assertions.

For a product with a monthly fee and a waiver threshold, disclose both the fee and the threshold. Do not describe the waiver threshold as an ongoing balance requirement unless the documents independently establish an ongoing requirement.

## Handling an unsupported account type

When no product is confirmed for one account type:

1. say the supplied materials do not verify the **exact** missing capability or condition;
2. do not name a product as meeting that unsupported requirement;
3. offer focused human review for only that account type; and
4. preserve and present the completed recommendation for the other type.

For example, if savings lacks documentation for same-day ACH between savings and checking, explain that exact evidence gap. Do not claim that an account with ordinary ACH, sweeps, or a transfer limit satisfies it. Preserve all other savings constraints in any handoff summary (for example, balance and wire-fee limits) so the reviewer can assess them.

A concise final form is:

> **Checking:** I recommend **[product]**. Its documented [mobile-deposit limit], [overdraft fee], and [APY] meet your stated requirements. The monthly fee is [fee]; [balance] is [only the fee-waiver condition/an ongoing minimum]. [Other material operating condition.]
>
> **Savings:** I cannot confirm a product for the requested [exact feature], because the supplied savings materials do not document [exact missing support]. I can arrange focused human review of that savings requirement.

Optionally use `scripts/validate_recommendation.py` before sending. Supply it only phrases that are present in the proposed response and supported by the runtime evidence.

## Human handoffs and later actions

If the customer asks for a human, first provide every independently confirmed recommendation unless the customer explicitly declines it. Use the normal banking handoff tool only for the unresolved portion and give a summary that separates completed recommendations from the precise evidence gap. Confirm a successful handoff only after its tool result confirms success.

If the customer later explicitly asks to open an account, follow the supplied opening procedure: verify each listed prerequisite, obtain the exact official account class, and use normal banking tools only after authorization. Move opening funds only with explicit authorization. Do not expose internal tool names or procedures to the customer.

## Final quality gate

Before sending a response, confirm:

- Every customer requirement is in the appropriate ledger.
- Each account type with a confirmed fit has a direct, named recommendation in this response.
- A missing savings fact did not block a confirmed checking recommendation, or vice versa.
- The recommendation itself states the relevant limits, APY, overdraft term, fees, and balance distinction accurately.
- Promotions were used only among fully confirmed eligible candidates.
- Same-day ACH between savings and checking was not inferred from generic transfer evidence.
- No account opening or money movement was performed for a recommendation-only request.

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
  "candidates": [{
    "id": "stable-id",
    "name": "Customer-facing product name",
    "facts": {"daily_mobile_deposit": 10000, "apy": 1.0, "overdraft_fee": 0},
    "eligibility": "eligible",
    "promotion": {"rank": 1, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
  }]
}
```

`eligibility` is `eligible`, `unknown`, or `ineligible`. Missing facts are unknown and zero is valid. Output contains `confirmed_matches`, `needs_confirmation`, `excluded`, `recommended_order`, and `errors`.

### `scripts/validate_recommendation.py`

Reads one JSON object from stdin and emits one JSON object on stdout:

```json
{
  "response": "proposed customer-facing response",
  "confirmed": [{
    "account_type": "checking",
    "name": "Product name",
    "recommendation_phrase": "I recommend Product name",
    "required_phrases": ["evidence-supported disclosure phrase"]
  }],
  "unresolved": [{
    "account_type": "savings",
    "required_phrases": ["materials do not verify", "human review"]
  }]
}
```

It performs normalized case-insensitive containment checks and emits `ok`, `errors`, and `missing`. It validates wording presence only; it does not establish banking facts.
