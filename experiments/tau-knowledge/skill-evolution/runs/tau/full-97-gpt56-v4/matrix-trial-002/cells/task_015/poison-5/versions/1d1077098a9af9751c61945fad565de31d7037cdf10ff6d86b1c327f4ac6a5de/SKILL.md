---
name: credit-card-referral-link-triage
description: Safely handles requests for a credit-card referral link. Use when a customer cites a referral offer or asks how to generate a link; it requires card-specific program and terms confirmation before exposing the customer-operated referral-link tool.
---

# Credit-card referral-link triage

Use this Skill for referral-link requests involving credit cards.

## Required inputs and evidence

Identify the exact requested card and every material offer term the customer cites (for example, referrer bonus, invitee spend threshold, and qualifying period). Consult the task's available knowledge/evidence for a **card-specific** referral program. General statements that some cards may have referral programs are not confirmation for a particular card.

Use `scripts/referral_decision.py` when the evidence can be represented in its JSON schema. The script only recommends a decision and customer wording; it does not call bank tools or create a referral.

## Decision procedure

1. Confirm that a documented program exists for the exact card.
2. Confirm that the customer's material terms match that documented program. If the customer did not provide terms, state the documented terms before offering the tool.
3. Consider whether there is reason the referral will be automatically rejected (including the rolling referral limit or known referral activity). If a check is necessary and a customer identifier is available under the applicable interaction rules, use the normal referral-activity tool. Do not infer a pass from missing data.
4. If the program is absent, the claimed terms do not match, or automatic rejection is indicated, explain the applicable reason. Do **not** provide `get_referral_link`, do not generate a link for the customer, and do not transfer solely for this unavailable or unconfirmed offer.
5. Only when all checks pass, use `give_discoverable_user_tool` to expose `get_referral_link` to the customer (with no agent-side execution). Tell the customer to run it using their own `user_id` and the exact documented card name. Reiterate the confirmed terms and explain that a successful call creates a referral record in `NO_PROGRESS` status, after which the invitee may apply.
6. Remind eligible customers that only two referral bonuses can be earned in any rolling seven-day window; third and later referrals in that window are automatically denied.

Do not substitute a similar card, a marketing claim, or an undocumented mailed offer for card-specific documentation. Do not disclose or solicit another person's data.

## Running the helper

The helper reads one JSON object from standard input and emits one JSON decision object on standard output:

```json
{
  "card_name": "<exact requested card>",
  "claimed_terms": {"referrer_bonus": "...", "invitee_requirement": "..."},
  "documented_program": null,
  "automatic_rejection_risk": false
}
```

`documented_program` is either `null` when no exact-card program is documented, or an object containing `card_name` and `terms`. Its `terms` must use the same material-term keys as `claimed_terms`; values are compared after whitespace/case normalization. Set `automatic_rejection_risk` to `true` only when supported by available evidence. A non-boolean unknown value is treated conservatively as an unconfirmed check.

Example invocation in the supported script runtime: run `scripts/referral_decision.py` with the object above. Validate that `action` is `offer_customer_tool` before calling `give_discoverable_user_tool`; for every other action, no referral-link tool may be given.
