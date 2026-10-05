---
name: debit-card-fraud-human-handoff
description: Use when a customer requests a human agent while reporting debit-card unauthorized activity, suspected fraud, a lost or stolen card, an ATM error, or a post-cancellation recurring charge. Creates a fact-preserving, card-specific transfer summary and avoids unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill for a requested human handoff involving debit-card disputes or security concerns.

## Core rule

A human-agent request may be transferred promptly. Do not delay a requested handoff in order to file disputes, search transactions, freeze or close a card, reissue a card, issue credit, or change payment settings. Those are banking actions with separate verification and eligibility prerequisites.

The handoff summary is a case record for the receiving agent. Every successful clarification answer and supplied successful read-only observation must be considered before transfer. Never label a detail as unknown, uncollected, or outstanding when it appears in a successful clarification answer or observation.

## Required execution sequence

1. Assemble the complete runtime case record from the opening request, all customer messages, all clarification records, and all supplied read-only observations.
2. Include **every** clarification object, retaining its `question`, `result`, and `status`; do not provide only the opening request to the helper.
3. Run `scripts/build_handoff_summary.py` using that complete record.
4. If `errors` is nonempty, correct the input record and rerun the helper before transferring.
5. Read the returned `summary` and confirm it retains the completed clarification answers verbatim. In particular, verify that card labels, card-possession statements, issue-to-card assignments, merchant outcome, and recurring-payment preference have not been omitted.
6. Call `transfer_to_human_agents` exactly once using the returned `reason` and `summary`.

Do not replace the generated structured summary with a generic intake checklist. If the helper is unavailable, faithfully include each successful clarification question and answer in the transfer summary, in addition to a concise card-specific routing section.

## Choosing the transfer reason

Use `fraud_or_security_concern` when the case includes unauthorized activity, suspected fraud, identity theft, or a lost/stolen debit card. This Tier-1 reason takes priority over concurrent ATM, merchant, subscription, or billing issues.

Use `complex_billing_dispute` only if specialist billing, ATM, or recurring-charge handling is needed and no fraud/security condition applies. Use a generic human-request reason only if no higher-priority reason applies.

## Summary requirements

The summary must be self-contained and distinguish known facts from facts that remain to be gathered. Preserve, when supplied:

- the customer’s request for a human agent, total transaction/card scope, and all reported issue types;
- customer name and user ID found by successful read-only lookup, with the clear qualification that lookup is not identity verification;
- each card or account label and whether the customer still possesses that card;
- whether unauthorized activity is believed fraudulent, without inventing transaction channel, PIN status, or a card-present/card-not-present classification;
- the card associated with each ATM issue and each recurring/subscription issue;
- the merchant name, cancellation/contact details, and merchant response;
- the customer’s preference about a future card-wide recurring-payment block;
- results of supplied read-only cross-product checks, actual completed actions, and only genuinely unresolved filing details.

Use a card-specific routing section, then retain successful clarification answers verbatim. Verbatim retention is required because clarification answers may contain material facts beyond fixed intake fields.

## Recurring-payment safeguard

A charge that occurred after a subscription was cancelled is a dispute about a past charge. A recurring-payment block affects **all** recurring payments on the card, not one merchant.

Never call `set_debit_card_recurring_block_7382` merely because the customer disputes a subscription charge. If the customer asks to address only a past charge or declines a broad block, preserve that limitation in the handoff summary and do not apply a card-wide recurring-payment block.

Do not state that verification, a dispute, a card freeze, closure, replacement, payment block, or provisional credit occurred unless the action actually succeeded.

## Summary helper

`scripts/build_handoff_summary.py` is deterministic and non-executing. It reads one JSON object from standard input and writes one JSON object to standard output. It does not call tools or modify customer data.

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input schema:

- `opening` (required string): initial customer request.
- `clarifications` (array): complete clarification objects with `question`, `result`, and `status`.
- `read_only_observations` (array): complete observation objects with `tool`, `result`, and `status`.
- `verification_status` (optional string): defaults to `not completed`.
- `actions_completed` (optional string array): only actions that actually succeeded.
- `unresolved_items` (optional string array): only items absent from the complete case record.

Output schema:

- `reason`: recommended transfer reason code.
- `summary`: transfer-ready factual case summary.
- `errors`: validation errors. Do not transfer while nonempty.
- `non_execution_notice`: confirms that no action was performed.

Pass `reason` and `summary` unchanged to `transfer_to_human_agents`.

## If a banking action is later requested

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmations. Before filing a debit-card dispute, confirm the linked checking account is OPEN, the card and transaction match, the transaction is at least $1 and within 60 days, and the account has dispute capacity. Obtain transaction identifiers and determine whether an ATM is bank-operated or third-party.

Before filing an unauthorized-activity dispute, explain Regulation E reporting timing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. Determine transaction channel before choosing a suspected-fraud dispute category.
