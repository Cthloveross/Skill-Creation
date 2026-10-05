---
name: credit-card-referral-link-eligibility
description: Assess a request for a credit-card referral link, validate the claimed offer against card-specific documentation, and either give the customer the self-service referral-link tool or clearly refuse without a transfer.
---

# Credit Card Referral Link Eligibility

Use this Skill when a customer asks to create, obtain, or share a credit-card referral link.

## Required checks

1. Search the supplied knowledge base for an active, **card-specific** referral program matching the exact requested card.
2. Extract the documented referral terms, including reward, qualifying event, required spend or activity, and timeframe where stated.
3. Compare the customer's claimed terms with the documented terms. A generic referral article is not confirmation that a particular card participates.
4. Determine whether there is a documented reason the referral would be automatically rejected, including the rolling seven-day bonus limit.

Use `scripts/assess_referral_request.py` after converting the search results into the documented-program and structured-term inputs described below. The helper provides a consistent permit/refuse determination; it does not search the knowledge base or perform banking actions.

## Decision and response

### Do not provide a referral tool
Do **not** call `give_discoverable_user_tool` when any of the following is true:

- No card-specific referral program is documented.
- The customer’s claimed terms conflict with the documented program.
- The referral is expected to be automatically rejected.

Explain the applicable reason plainly. If the terms conflict, state the correct documented terms when they are available. If no card-specific program is documented, say that the requested card’s referral offer cannot be confirmed from the available documentation; do not validate a mailer or invent offer details. Do not transfer the customer to a human for these outcomes.

In particular, general statements that some cards may have referral offers do not establish eligibility for the requested card or validate a claimed reward amount, spend condition, or time period.

### Provide the customer tool only after all checks pass
If a program is documented, all stated terms match, and no automatic denial is expected:

1. Reiterate the documented program terms and the rolling seven-day limit: at most two referral bonuses in a rolling seven-day period; third and later referrals in that window are automatically denied.
2. Call `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link`. Do not call the referral tool as the agent.
3. Tell the customer to run the tool themselves with their own `user_id` and the exact documented `card_name`. Explain that a successful call creates a referral record with status `NO_PROGRESS`, after which the referred person may apply through the generated link.

Do not retrieve identity data, verify identity, or log verification merely to provide this self-service tool. Never generate a link on the customer's behalf.

## Helper input and output

Run the helper as follows:

```json
{
  "card_name": "exact card name from the customer",
  "claimed_terms": {"reward": "...", "qualification": "...", "timeframe": "..."},
  "documented_program": true,
  "documented_terms": {"reward": "...", "qualification": "...", "timeframe": "..."},
  "automatic_rejection": false,
  "rejection_reason": "optional documented reason"
}
```

`documented_program` must be true only when a search found a card-specific program. Provide the same term keys in both objects for every term the customer stated and the program documents. Use `null` for either term object only if it is unavailable. `automatic_rejection` must be based on documented facts, not speculation.

The script emits JSON with `tool_permitted`, `decision`, `term_match`, and a customer-facing `message`. Before acting, validate that:

- `tool_permitted` is true only for `decision: "provide_self_service_tool"`;
- the message does not claim unverified terms;
- the actual tool is offered only in that permitted branch.

If search evidence is incomplete, set `documented_program` to false and refuse rather than assuming participation.
