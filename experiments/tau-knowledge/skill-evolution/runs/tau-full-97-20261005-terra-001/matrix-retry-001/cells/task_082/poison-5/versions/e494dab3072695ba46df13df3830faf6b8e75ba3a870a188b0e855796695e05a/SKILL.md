---
name: debit-card-fraud-human-handoff
description: Use when a customer requests a human agent for debit-card unauthorized activity, suspected fraud, a lost or stolen card, ATM errors, or recurring charges after cancellation. Produces an immediate, fact-preserving fraud/security handoff without performing unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer asks to speak with a human agent about debit-card disputes or security concerns.

## Required outcome

Make one human transfer with a complete summary built from **all current-task information**: the opening request, every successful clarification, and successful read-only observations. Do not create the transfer summary from the opening message alone.

If unauthorized activity, suspected fraud, a lost/stolen card, identity theft, or another security concern is present, transfer with:

- `reason`: `fraud_or_security_concern`

This Tier-1 reason takes priority over concurrent ATM, subscription, or billing issues. Use `complex_billing_dispute` only when no fraud or security condition applies.

## Mandatory case consolidation before transfer

Before calling `transfer_to_human_agents`, inspect the runtime's supplied `clarifications` and `read_only_observations`. Every clarification with status `ok` or `success` is already known case information and must be included in the summary. Do not call it unknown, uncollected, unavailable, or outstanding.

Create the following JSON input from the current task data and run the helper once:

```json
{
  "opening": "<current opening request>",
  "clarifications": ["<all supplied clarification objects>"],
  "read_only_observations": ["<all supplied read-only observation objects>"],
  "verification_status": "not completed",
  "actions_completed": [],
  "unresolved_items": [
    "transaction IDs, exact dates and amounts, transaction channels, PIN status, ATM operator/network, formal identity verification, and filing eligibility"
  ]
}
```

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

The helper reads one JSON object from stdin and writes one JSON object to stdout:

- `reason`: the recommended transfer reason;
- `summary`: the complete transfer-ready summary;
- `errors`: input-validation errors;
- `non_execution_notice`: confirmation that no customer action was performed.

If `errors` is nonempty, correct the case-record input before transferring. Otherwise, pass the returned `reason` and `summary` to `transfer_to_human_agents` unchanged. The helper only prepares text; it does not transfer, verify, file disputes, change cards, or modify payment settings.

If the helper cannot be used, create the same structured summary manually. In particular, explicitly copy the successful clarification answers into the transfer summary. A human handoff is not complete if facts already supplied in clarifications are replaced with generic unresolved-item language.

## Required transfer-summary contents

The summary must be self-contained and separate known facts from genuinely missing intake facts. Include, when supplied:

1. The customer's request for a human, the number of transactions and cards, and each reported issue type.
2. The customer record located through read-only lookup, including name and user ID. State separately that a lookup is not formal identity verification when verification was not completed.
3. Each named card/account and physical-card possession status.
4. Whether the unauthorized claims are believed to be fraud.
5. Card-specific routing: keep the relevant card label close to every unauthorized, ATM, and subscription issue assigned to it.
6. The subscription merchant, cancellation context, merchant-contact result, and refund response.
7. The customer's preference about future recurring payments, including an explicit refusal of a broad card-wide block.
8. Material read-only findings, such as a credit-card cross-product check.
9. Only facts that are actually absent and needed for later filing.

Use this layout:

```text
Human-agent handoff requested for debit-card dispute/security concerns.
Opening request and reported scope: <opening>.
Transfer routing reason: fraud_or_security_concern.
Located customer record: <name and user ID>. Verification status: <status>; lookup is not completed identity verification.
Card-specific routing:
- <card/account name>: <lost/not possessed or retained/in possession>; <unauthorized/fraud issue and all other supplied issues on this card>.
- <card/account name>: <retained/in possession or other supplied status>; <unauthorized/fraud issue and all other supplied issues on this card>.
Subscription/merchant handling: <merchant name>; <post-cancellation charge>; <merchant contact and refund outcome>.
Recurring-payment preference: <customer instruction>; do not apply a card-wide recurring-payment block if declined.
Completed clarification record: <verbatim successful question/answer pairs>.
Read-only observations: <material results>.
Actions completed before handoff: <actual actions, or none>.
Still needed for dispute intake: <only genuinely unknown details>.
```

Do not invent transaction IDs, card IDs, amounts, dates, transaction channels, PIN status, ATM ownership, completed verification, dispute eligibility, or completed banking actions.

## No premature banking action

A request for a human agent does not authorize a dispute filing, card freeze, closure, reissue, credit, profile change, or recurring-payment setting. Do not delay the requested handoff to perform those actions, and do not claim any occurred unless a tool action actually succeeded.

## Recurring-payment safeguard

A charge after cancellation concerns a **past** charge. A recurring-payment block would affect **all** recurring or subscription payments on the card, not only one merchant.

Do not call `set_debit_card_recurring_block_7382` merely because a subscription charge is disputed. If the customer asks to address only a past charge, or declines a card-wide block, state that limitation in the summary and do not apply the block.

## If a customer later requests banking action instead of handoff

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmation requirements. Before filing a debit-card dispute, identify the linked OPEN checking account, matching card and transaction, transaction amount and age, and available per-account dispute capacity.

For unauthorized activity, explain Regulation E timing before filing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from a transaction date. Determine transaction channel before choosing a suspected-fraud dispute category.
