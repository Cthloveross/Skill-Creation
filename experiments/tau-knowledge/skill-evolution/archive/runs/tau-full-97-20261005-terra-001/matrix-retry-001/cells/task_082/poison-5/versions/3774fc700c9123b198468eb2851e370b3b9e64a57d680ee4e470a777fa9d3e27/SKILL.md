---
name: debit-card-fraud-human-handoff
description: Use when a customer requests a human agent while reporting debit-card unauthorized activity, suspected fraud, a lost or stolen card, ATM errors, or recurring charges after cancellation. Produces a fact-preserving, card-specific handoff and prevents unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer wants a human handoff for debit-card disputes or security concerns.

## Non-negotiable handoff rule

A requested handoff may be prompt, but it must not discard facts already collected for that handoff. Before calling `transfer_to_human_agents`, consolidate the opening request, every successful clarification answer, and every successful supplied read-only observation into the transfer summary.

Do **not** call the transfer tool with a generic summary or an intake checklist if successful clarification answers are available. Do **not** characterize a supplied fact as unknown, uncollected, unavailable, or outstanding. A read-only customer lookup may identify the record but does not by itself complete identity verification.

Do not delay a requested handoff to file disputes, search transactions, freeze or close a card, reissue a card, issue credit, or change payment settings. Those are banking actions with separate prerequisites.

## Required execution sequence

1. Build a complete runtime case record containing:
   - `opening`: the customer's initial request;
   - `clarifications`: **all** clarification objects supplied by the runtime, including `question`, `result`, and `status`;
   - `read_only_observations`: **all** supplied observation objects, including `tool`, `result`, and `status`;
   - optional factual `verification_status`, `actions_completed`, and `unresolved_items`.
2. Run `scripts/build_handoff_summary.py` through the supplied Skill script runner with that complete record. Do not substitute an opening-only record when clarification or observation records are available.
3. If the returned `errors` is nonempty, correct the record and run the helper again. Otherwise, use the returned `summary` unchanged as the human-transfer summary.
4. Before transfer, verify that the output includes the known answers verbatim and has not omitted card names, possession status, issue-to-card assignments, merchant outcome, or the customer's recurring-payment preference.
5. Call `transfer_to_human_agents` exactly once using the helper's returned `reason` and `summary`.

If the helper cannot be run, manually create the same self-contained summary. Include every successful clarification question and answer verbatim, followed by a card-specific routing section. Never replace supplied answers with guessed fields or a statement that facts are missing.

## Transfer-reason selection

Use `fraud_or_security_concern` when unauthorized activity, suspected fraud, identity theft, or a lost/stolen debit card is reported. This is the highest applicable Tier-1 reason and takes priority over concurrent ATM, merchant, subscription, or billing matters.

Use `complex_billing_dispute` only for ATM, recurring-charge, or other billing disputes when no fraud or security condition applies. Use a generic human-request reason only when no higher-priority reason applies.

## Required handoff content

The summary must distinguish known facts from facts genuinely still needed. Preserve, when supplied:

- the explicit request for a human agent, total transaction/card scope, and every reported issue type;
- located customer name and user ID, while clearly distinguishing lookup from completed verification;
- each card/account label, and whether the customer retains that physical card;
- whether unauthorized activity is believed fraudulent, without inventing transaction channel, PIN compromise, or card-present/card-not-present classification;
- the card associated with each ATM issue and with each recurring/subscription issue;
- merchant name, cancellation/contact history, and merchant response;
- the customer's preference about future card-wide recurring-payment blocking;
- supplied read-only cross-product results, actual successfully completed actions, and only genuinely unresolved dispute-filing facts.

Use a card-specific routing section whenever card assignment information is supplied. Preserve successful clarification answers verbatim even if a concise routing statement was also written; the answers are the authoritative source for facts that do not fit fixed fields.

## Recurring-payment safeguard

A charge after subscription cancellation concerns a **past** charge and uses the dispute process. A recurring-payment block affects **all** recurring payments on a card, not just one merchant.

Never call `set_debit_card_recurring_block_7382` merely because a customer disputes a subscription charge. If the customer wants only a past charge addressed or declines a broad block, record that exact limitation in the handoff and do not apply a card-wide recurring-payment block.

Do not state that a verification, dispute, freeze, closure, replacement, payment block, or provisional credit occurred unless that action actually succeeded.

## Summary helper

`scripts/build_handoff_summary.py` is deterministic and non-executing. It reads one JSON object from stdin and emits one JSON object to stdout. It does not call tools or modify customer data.

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
- `summary`: transfer-ready factual summary, including verbatim successful clarifications.
- `errors`: input validation errors. Do not transfer while nonempty.
- `non_execution_notice`: confirms that no action was performed.

Pass `reason` and `summary` unchanged to `transfer_to_human_agents`.

## If a banking action is later requested

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and required confirmations. Before filing a debit-card dispute, confirm the linked checking account is OPEN, the card and transaction match, the transaction is at least $1 and within 60 days, and the account has dispute capacity. Obtain transaction identifiers and determine whether an ATM is bank-operated or third-party.

Before filing an unauthorized-activity dispute, explain Regulation E reporting timing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. Determine transaction channel before selecting a suspected-fraud dispute category.
