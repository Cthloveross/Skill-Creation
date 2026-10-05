---
name: debit-card-fraud-human-handoff
description: Transfer debit-card fraud, unauthorized-transaction, lost-card, ATM-error, or cancelled-recurring-charge cases to a human agent while preserving all available customer clarifications in a card-specific handoff summary. Use when the customer explicitly requests a human agent and no verified banking action should be taken before escalation.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill for a customer who requests a human agent concerning debit-card disputes, especially unauthorized activity, suspected fraud, a lost or stolen card, ATM errors, or a charge after cancellation.

## Immediate escalation workflow

An explicit request for a human agent supports immediate escalation. Do not delay the transfer in order to file a dispute, retrieve transaction history, freeze or close a card, reissue a card, issue credit, or alter recurring-payment settings. Those are banking actions and require identity verification and their applicable prerequisites.

Before the one `transfer_to_human_agents` call:

1. Read the complete current case record: opening message, all subsequent customer messages, all successful clarification answers, and successful read-only observations.
2. Treat every successful clarification response as a known fact. Do not call a fact unknown, unconfirmed, unavailable, or outstanding when it appears in a successful response.
3. Run `scripts/build_handoff_summary.py` with the complete records. Pass clarification records verbatim; do not replace them with generic labels or counts.
4. If `errors` is nonempty, correct the input and rerun the helper. Review the summary to ensure it preserves the customer-provided card labels, possession states, issue-to-card routing, merchant outcome, and recurring-payment preference.
5. Call `transfer_to_human_agents` exactly once using the helper's `reason` and `summary`.

If the helper is unavailable, create the equivalent summary manually. Keep ATM and its card together, keep the subscription/merchant and its card together, and include every successful clarification answer. State only truly absent details as unresolved.

## Transfer reason priority

Use `fraud_or_security_concern` if the case includes unauthorized activity, suspected fraud, identity theft, or a lost/stolen card. This Tier-1 reason has priority over concurrent ATM, subscription, or other billing issues and over a generic request for a human.

Use `complex_billing_dispute` only when an ATM, subscription, or billing issue needs specialist handling and no fraud/security condition applies. Use a generic human-request reason only when no higher-priority reason applies.

## Required handoff information

The handoff must be self-contained. Include, where supplied:

- The customer’s request for a human agent and the transaction/card scope.
- Unauthorized, ATM, and subscription/recurring issue types.
- Located customer name and user ID from successful read-only lookup. Explicitly distinguish this lookup from completed identity verification.
- Each customer-supplied card/account label and the reported possession status.
- The customer’s fraud belief for unauthorized items, without inferring transaction channel, PIN status, or card-present/card-not-present classification.
- The specific card associated with the ATM issue and with the subscription issue.
- The subscription merchant, merchant-contact result, and refund outcome.
- The customer’s future recurring-payment preference.
- The result of a completed read-only credit-card cross-product check, if one is available.
- Completed actions and only genuinely missing filing details.

A successful clarification is stronger than a generic intake checklist. For example, a known card label is not replaced by “card details needed”; instead, only an absent card ID may be listed as needed.

## Recurring-payment safeguard

A past post-cancellation charge is a dispute issue. A recurring-payment block affects **all** recurring payments on a card. Never call `set_debit_card_recurring_block_7382` merely because a prior subscription charge is disputed.

If the customer wants only a prior charge addressed or declines a broad block, preserve that limitation in the handoff and do not place a card-wide recurring-payment block.

Do not claim that verification, a dispute, a freeze, closure, replacement, recurring block, or provisional credit occurred unless the corresponding action succeeded. A user-information lookup is not identity verification.

## Summary helper

`scripts/build_handoff_summary.py` is deterministic and non-executing. It reads one JSON object from stdin and writes one JSON object to stdout. It does not invoke banking tools or modify customer data.

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input object:

- `opening` — required nonempty opening/request string.
- `clarifications` — complete array of `{question, result, status}` records. Every record with status `ok` or `success` is preserved as known case information.
- `read_only_observations` — array of `{tool, result, status}` records. Name/user-ID lookup and credit-card-check results are safely summarized.
- `verification_status` — optional string; defaults to `not completed`.
- `actions_completed` — optional array of successfully completed action descriptions.
- `unresolved_items` — optional array containing only facts genuinely absent from the complete case record.

Output object:

- `reason` — recommended human-transfer reason.
- `summary` — transfer-ready, fact-preserving summary.
- `errors` — malformed-input issues. Do not transfer while this is nonempty.
- `non_execution_notice` — confirmation that no action was performed.

Validate that supplied card names, possession facts, ATM routing, subscription routing, merchant contact outcome, and recurring-block preference all appear in the returned `summary`. Then pass `reason` and `summary` unchanged to the transfer tool.

## Later dispute handling

Only begin ordinary debit-dispute processing if a human transfer is not requested or a responsible specialist directs it. Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmations.

Before filing a debit-card dispute, validate the linked checking account is OPEN, card and transaction match, transaction amount is at least $1, transaction age is within 60 days, and account-tier dispute capacity is available. Retrieve transaction history for transaction IDs and determine whether an ATM is bank-operated or third-party.

For unauthorized activity, explain Regulation E reporting timing before filing: within two business days of the statement has maximum $50 liability, within 60 days has maximum $500 liability, and after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. If fraud is suspected, determine the transaction channel before selecting a fraud category.
