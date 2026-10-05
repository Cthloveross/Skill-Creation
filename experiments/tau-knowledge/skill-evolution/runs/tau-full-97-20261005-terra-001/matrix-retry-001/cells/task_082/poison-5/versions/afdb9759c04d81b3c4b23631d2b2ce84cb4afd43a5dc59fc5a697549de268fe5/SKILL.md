---
name: debit-card-fraud-human-handoff
description: Use for a customer-requested human handoff involving debit-card unauthorized activity, suspected fraud, a lost/stolen card, ATM error, or a cancelled recurring charge. Produces a fact-preserving, card-specific transfer summary without performing unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer explicitly requests a human agent for debit-card disputes or security concerns.

## Handoff procedure

An explicit human-agent request supports prompt transfer. Do **not** delay escalation to file disputes, retrieve transactions, freeze/close/reissue cards, issue credit, or change payment settings. Those are banking actions and require identity verification plus their own prerequisites.

Before calling `transfer_to_human_agents`:

1. Consolidate the complete current case record: opening request, every customer message, every successful clarification answer, and successful read-only observations.
2. Treat a successful clarification answer as known. Never say that a fact is unknown, uncollected, or outstanding if it is stated in that answer.
3. Run `scripts/build_handoff_summary.py` with the complete records. Include clarification `question`, `result`, and `status` values exactly as received.
4. If the returned `errors` is nonempty, repair the supplied JSON before transfer. Otherwise, review that the summary contains each supplied card label, possession status, issue-to-card assignment, merchant outcome, and future-recurring-payment preference.
5. Call `transfer_to_human_agents` exactly once with the returned `reason` and `summary`.

If the helper cannot be run, create the same structured summary manually. Quote or faithfully reproduce every successful clarification answer; this is preferable to replacing known facts with a generic intake checklist.

## Transfer reason selection

Use `fraud_or_security_concern` when unauthorized activity, suspected fraud, identity theft, or a lost/stolen card is reported. This Tier-1 reason takes priority over concurrent ATM or billing/recurring-charge issues.

Use `complex_billing_dispute` only when a specialist billing/ATM/recurring issue exists and no fraud or security condition applies. Use a generic human-request reason only if neither higher-priority Tier-1 reason applies.

## Required content of the transfer summary

The summary must be self-contained and preserve supplied facts, including:

- the request for a human agent; transaction and card scope; unauthorized, ATM, and subscription/recurring issue types;
- customer name and user ID from a successful read-only lookup, while clearly stating that lookup is not identity verification;
- every supplied card/account label and whether the customer possesses that card;
- whether unauthorized items are believed fraudulent, without inferring transaction channel, PIN compromise, or card-present classification;
- the specific card for each ATM issue and each cancelled subscription/recurring charge;
- named merchant, customer contact with that merchant, and refund/contact outcome;
- the customer's stated preference regarding a future card-wide recurring-payment block;
- results of supplied read-only cross-product checks, completed actions, and only genuinely missing dispute-intake items.

Keep each issue and its card together in a card-specific routing section. Preserve source clarification answers verbatim after the concise routing section so no available detail is lost.

## Recurring-payment safeguard

A post-cancellation charge is a dispute concerning a past charge. A recurring-payment block affects **all** recurring payments on the card. Never call `set_debit_card_recurring_block_7382` merely because a subscription charge is disputed.

When the customer asks to address only a past charge or declines a broad block, state that limitation in the transfer summary and do not apply a card-wide recurring-payment block. Do not claim that verification, a dispute, a freeze, closure, replacement, block, or provisional credit occurred unless that action actually succeeded.

## Summary helper

`scripts/build_handoff_summary.py` is deterministic and non-executing. It reads one JSON object from stdin and writes one JSON object to stdout. It does not call banking tools or modify customer data.

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input object:

- `opening` (required string): initial customer request.
- `clarifications` (array): complete `{question, result, status}` records.
- `read_only_observations` (array): complete `{tool, result, status}` records.
- `verification_status` (optional string): defaults to `not completed`.
- `actions_completed` (optional string array): only actions that actually succeeded.
- `unresolved_items` (optional string array): only facts absent from the full case record.

Output object:

- `reason`: recommended reason code.
- `summary`: transfer-ready summary.
- `errors`: input validation errors; do not transfer when nonempty.
- `non_execution_notice`: confirms no action was performed.

Pass the output `reason` and `summary` unchanged to the human-transfer tool.

## If dispute processing occurs later

Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmations. Before filing a debit dispute, confirm the linked checking account is OPEN, the card and transaction match, the transaction is at least $1 and within 60 days, and the account has dispute capacity. Obtain transaction identifiers and determine whether an ATM is bank-operated or third-party.

For unauthorized activity, explain Regulation E reporting timing before filing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. Determine transaction channel before choosing a suspected-fraud dispute category.
