---
name: debit-card-fraud-human-handoff
description: Use when a customer requests a human agent for debit-card unauthorized activity, suspected fraud, a lost or stolen card, ATM errors, or a recurring charge after cancellation. Produces an immediate, complete fraud/security handoff without performing unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill for a requested human handoff involving debit-card disputes or security concerns.

## Required outcome

Make one successful `transfer_to_human_agents` call with a summary built from **all information already available in the current task**:

- the opening request;
- every clarification whose status is `ok` or `success`; and
- every successful read-only observation.

Do not create a handoff from the opening message alone. Successful clarification answers are known facts, not questions to leave outstanding.

When unauthorized activity, suspected fraud, a lost/stolen card, identity theft, or another security concern is present, use:

- `reason`: `fraud_or_security_concern`

This Tier-1 reason takes priority over concurrent ATM, subscription, and billing matters. Use `complex_billing_dispute` only if no fraud or security concern applies.

## Execution procedure

1. Do not file disputes, freeze or close cards, reissue cards, set payment blocks, or make profile changes solely because the customer requests a human agent.
2. Assemble the current opening text, full clarification objects, and full read-only observation objects into the helper input schema below.
3. Run `scripts/build_handoff_summary.py` through the available packaged-script runner. The script reads one JSON object from stdin and emits one JSON object to stdout.
4. If `errors` is nonempty, fix the input data shape and rerun before transferring. If `errors` is empty, call `transfer_to_human_agents` exactly once using the emitted `reason` and `summary`.
5. Do not alter the returned summary to remove card-specific facts, merchant outcome, customer preferences, or unresolved intake items.

Example helper input shape (replace all placeholders with the current task data):

```json
{
  "opening": "<opening customer request>",
  "clarifications": ["<all clarification objects>"],
  "read_only_observations": ["<all observation objects>"],
  "verification_status": "not completed",
  "actions_completed": [],
  "unresolved_items": [
    "transaction IDs, exact dates and amounts, transaction channels, PIN status, ATM operator/network, formal identity verification, and dispute-filing eligibility"
  ]
}
```

Helper output schema:

```json
{
  "reason": "fraud_or_security_concern",
  "summary": "<transfer-ready factual summary>",
  "errors": [],
  "non_execution_notice": "<confirms the helper took no action>"
}
```

The helper only prepares a summary. It does not transfer, verify identity, file a dispute, or change customer settings.

## Transfer-summary requirements

The summary must distinguish known facts from genuinely unresolved filing facts. Preserve the following when supplied:

1. The human-agent request, scope (transaction/card count when stated), unauthorized activity, ATM issue, and subscription issue after cancellation.
2. Located customer name and user ID from read-only lookup. A lookup is not the same as formal identity verification.
3. Every named card or account and its reported possession status.
4. Whether unauthorized transactions are believed fraudulent.
5. A card-by-card routing section. Keep each card name close to the unauthorized, ATM, and subscription matter assigned to it.
6. The subscription merchant name, cancellation context, merchant-contact outcome, and refund response.
7. The customer’s preference about a recurring-payment block, including an explicit refusal of a card-wide block when stated.
8. Material read-only findings, including a credit-card cross-product lookup if one was performed.
9. Only actually unknown transaction and eligibility information for the receiving specialist.

A useful structure is:

```text
Human-agent handoff requested for debit-card dispute/security concerns.
Located customer record: <name and user ID>; formal verification: <status>.
Card-specific routing:
- <Blue/named card>: <possession status>; <fraud/unauthorized issue>; <subscription merchant and cancelled-charge issue>.
- <Green/named card>: <possession status>; <fraud/unauthorized issue>; <ATM issue>.
Subscription merchant/contact result: <known outcome>.
Recurring-payment preference: <known instruction>.
Still needed for dispute intake: <unknown IDs, amounts, dates, channels, verification, and eligibility facts>.
```

Never label an `ok` clarification as unavailable, unknown, uncollected, or outstanding. Do not fabricate transaction IDs, card IDs, dates, amounts, channel, PIN status, ATM ownership, completed verification, or eligibility.

## Recurring-payment safeguard

A charge after cancellation is a dispute about a **past** charge. A recurring-payment block affects **all** recurring or subscription payments on the card, not one merchant.

Do not call `set_debit_card_recurring_block_7382` merely because a subscription charge is disputed. If the customer wants only a past charge addressed or declines a card-wide block, preserve that limitation in the handoff and do not apply the block.

## If the customer later asks for banking action

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmation requirements. For a debit-card dispute, identify the linked OPEN checking account, matching card and transaction, transaction amount and age, and available per-account dispute capacity.

Before filing an unauthorized debit-card dispute, explain Regulation E timing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from the transaction date. Determine transaction channel before selecting a suspected-fraud dispute category.
