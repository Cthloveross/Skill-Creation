---
name: debit-card-fraud-human-handoff
description: Use when a customer asks for a human agent while reporting debit-card unauthorized activity, suspected fraud, a lost or stolen card, ATM errors, or a recurring charge after cancellation. Creates a fact-preserving, card-specific transfer summary without taking unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill for a requested human handoff involving debit-card disputes or security concerns.

## Required outcome

Transfer the customer once with a complete, factual case summary. A requested handoff can be immediate, but it must preserve the information already supplied for the receiving specialist.

When unauthorized activity, suspected fraud, or a lost/stolen card is reported, use:

- `reason`: `fraud_or_security_concern`

This Tier-1 reason takes priority over concurrent ATM, recurring-charge, or other billing issues. Use `complex_billing_dispute` only when no fraud/security condition is present.

## Mandatory pre-transfer record assembly

Before `transfer_to_human_agents`, assemble the runtime case record from the **current task inputs**, not only the opening message:

```json
{
  "opening": "<initial customer request>",
  "clarifications": ["<every supplied clarification object>"],
  "read_only_observations": ["<every supplied observation object>"],
  "verification_status": "not completed",
  "actions_completed": [],
  "unresolved_items": ["<only facts genuinely not supplied>"]
}
```

For each clarification object, retain its `question`, `result`, and `status` exactly. Include every object whose status is `ok` or `success`. Do not substitute an opening-only record if the runtime has supplied clarification answers.

Run the packaged summary builder with that full record:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

The script reads one JSON object from stdin and emits one JSON object on stdout:

- `reason`: recommended transfer reason.
- `summary`: transfer-ready case summary.
- `errors`: malformed-input errors; do not transfer while nonempty.
- `non_execution_notice`: confirms the helper performed no customer action.

Pass the returned `reason` and `summary` unchanged to `transfer_to_human_agents`. Call that tool exactly once unless its result requires a retry.

If the helper is unavailable, manually follow its output structure. In particular, quote every successful clarification answer in the transfer summary and add the card-specific routing section described below. Never state that a fact is unknown, uncollected, unavailable, or outstanding if it appears in a successful clarification or supplied read-only result.

## Required summary content

The transfer summary must be self-contained and distinguish known facts from genuinely unresolved intake requirements. Preserve, when supplied:

1. The customer’s explicit request for a human and the stated transaction/card scope, including every reported issue type.
2. A located customer name and user ID from a read-only lookup, while accurately saying that lookup is not formal identity verification.
3. Each named card or account and whether the customer still possesses that physical card.
4. Whether the customer believes unauthorized activity is fraud. Do not invent transaction channels, PIN compromise, card IDs, transaction IDs, amounts, dates, or card-present/card-not-present classification.
5. An explicit **card-specific routing** section. Associate each unauthorized claim, ATM issue, and recurring/subscription issue with the card stated by the customer. Keep each card name close to its associated issue in the summary.
6. Subscription merchant name, cancellation history, merchant-contact outcome, and refund response.
7. The customer’s instruction regarding future recurring payments, especially a refusal of a broad card-wide block.
8. Material read-only results, such as a cross-product security check, and the actual verification/action status.
9. Only genuinely absent facts still needed for a later dispute filing, such as transaction identifiers, exact dates/amounts, transaction channel, PIN status, ATM operator/network, formal verification, and eligibility facts.

A reliable structure is:

```text
Human-agent handoff requested for debit-card dispute/security concerns.
Opening request and reported scope: <opening>.
Transfer routing reason: <reason>.
Located customer record: <known name and user ID>. Verification status: <status>; lookup alone is not completed identity verification.
Card-specific routing:
- <Card/account label>: <possession status>; <unauthorized/fraud and any other issue assigned to this card>.
- <Card/account label>: <possession status>; <ATM, subscription, and any other issue assigned to this card>.
Subscription/merchant handling: <merchant, cancellation/contact history, refund response>.
Recurring-payment preference: <customer instruction>. <State that no card-wide block is to be applied when declined.>
Completed clarification record (verbatim): <each successful question and answer>.
Read-only observations: <material lookup/cross-product facts>.
Actions completed before handoff: <actual successful actions or none>.
Still needed for dispute intake: <genuinely missing facts only>.
```

## No premature banking action

A customer’s request for a human agent does not itself authorize a dispute filing, card freeze/closure/reissue, recurring-payment block, credit, or profile change. Do not delay the requested transfer to perform those actions.

Do not claim that verification, a dispute, a card action, a payment block, or provisional credit occurred unless it actually succeeded.

## Recurring-payment safeguard

A charge after cancellation is a dispute about a **past** charge. A recurring-payment block affects **all** recurring/subscription payments on that card, not just one merchant.

Never call `set_debit_card_recurring_block_7382` merely because a subscription charge is disputed. If the customer wants only the past charge addressed or declines the broad block, preserve that limitation in the transfer summary and do not apply a card-wide recurring-payment block.

## If banking action is requested after handoff is not desired

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and required confirmation. Before a debit-card dispute filing, verify the linked checking account is OPEN, identify the matching card and transaction, confirm the amount is at least $1 and the transaction is within 60 days, and check the account’s open-dispute capacity.

For unauthorized activity, explain Regulation E timing before filing: within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from a transaction date. Determine the transaction channel before selecting a suspected-fraud dispute category.
