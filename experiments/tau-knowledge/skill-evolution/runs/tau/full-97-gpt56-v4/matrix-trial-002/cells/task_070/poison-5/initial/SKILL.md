---
name: business-checking-recommendation
version: 1.0.0
description: Handle a business-checking recommendation conversation when the customer wants one suitable account, including fact confirmation, eligibility gating, promotion-aware tie-breaking, and concise follow-up questions.
---

# Business Checking Recommendation

Use this Skill for informational business-checking account recommendations. It does not open an account, change an account, or establish that a customer is eligible unless every required eligibility fact is confirmed.

## Inputs

Read the current conversation, the supplied product-policy material, and any supplied timestamp. Extract:

- hard requirements (for example, zero overdraft fee and a minimum ATM-rebate amount);
- preferences (for example, travel, dedicated support, or rewards);
- the requested product, if the customer asks a direct product fact;
- facts already confirmed by the customer; and
- account eligibility conditions and any promotion effective on the supplied date.

Treat a customer statement such as “I need at least X” as a hard requirement. Treat broad words such as “perks” or “easiest” as preferences until the customer makes them measurable. Do not infer missing company age, balance, volume, deposit, or international-payment needs.

## Procedure

1. **Answer the direct question first.**
   When product materials explicitly confirm both facts the customer asks about, say so plainly and give the exact applicable limits. Do not bury this answer in a comparison.

2. **Explain material scope briefly.**
   For ATM benefits, distinguish the bank's charge or rebate from an ATM operator's separately disclosed surcharge. If travel may include foreign ATMs, do not imply that a domestic out-of-network rebate eliminates a separately stated foreign-withdrawal fee. Mention the foreign-fee rule only when it helps resolve the customer's travel need or could prevent a misleading impression.

3. **Evaluate requirements, not marketing language.**
   A candidate is a match only if every stated hard requirement is met and all applicable eligibility requirements are confirmed. Use the supplied product terms rather than assumptions. A rebate cap meets an “at least” requirement when the cap is greater than or equal to the requested amount.

4. **Keep eligibility distinct from product features.**
   If an unconfirmed eligibility condition is necessary for the likely match, state the condition and ask one focused question for it. Do not claim the customer qualifies, recommend opening the account as final, or request identity data merely to answer a product question.

5. **Apply a valid promotion only as a tie-breaker.**
   Check its effective dates against the supplied current time. If multiple accounts meet *all* stated requirements, apply the active priority order. A promotion never permits recommending an account that misses a requirement or has unconfirmed required eligibility.

6. **Give one clear next step.**
   The preferred response order is: direct answer; a concise qualification statement; one narrow follow-up question. If eligibility is confirmed and all requirements are met, recommend only the top qualifying account rather than presenting an unnecessary comparison. If no account can be verified as suitable, explain the blocking requirement and ask for only the information needed to proceed.

## Conversation handling for incomplete recommendations

When a customer first answers only a subset of a previous clarification, preserve the unresolved questions. However, if they ask a direct factual question, answer it before repeating the most decision-critical unresolved question. Avoid re-asking a question the customer already answered.

For a likely startup-account match whose published eligibility includes a maximum company age, confirmation of formation age is a gating question. Phrase the question in customer-friendly terms (for example, whether the business was formed within the stated period).

## Use of `scripts/recommendation_gate.py`

For consistent requirement and eligibility gating, call the helper with current, source-derived facts supplied in its JSON input. It reads JSON from stdin and emits JSON to stdout.

Input schema:

```json
{
  "requirements": {"zero_overdraft_required": true, "minimum_atm_rebate": 0},
  "candidate": {
    "name": "string",
    "overdraft_fee": 0,
    "monthly_atm_rebate_cap": 0,
    "eligibility": {"max_formation_age_years": 0}
  },
  "company_formation_age_years": null
}
```

`company_formation_age_years` may be omitted or `null` when unknown. Monetary values must be nonnegative numbers or numeric strings. The output reports which explicit requirements are met, whether eligibility is confirmed, and the single most useful follow-up question. Supply actual runtime facts; do not use the schema values as product facts.

Before responding, ensure the final message contains no invented account terms, no unsupported promise of approval, and no unnecessary account-operation or identity-verification action.
