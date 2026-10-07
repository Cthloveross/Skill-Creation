---
name: debit-card-fraud-human-handoff
description: Perform an immediate, fact-preserving transfer to a human agent when a debit-card case includes unauthorized activity, suspected fraud, a lost or stolen card, ATM error, or cancelled recurring charge. Use this Skill to produce a card-specific handoff summary from the complete runtime case record without performing unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer asks for a human agent about debit-card disputes, particularly where unauthorized activity, fraud, a lost/stolen card, ATM issue, or post-cancellation recurring charge is reported.

## Immediate handoff workflow

An explicit human-agent request permits an immediate escalation. Do not delay the transfer to file disputes, look up transactions, freeze or close a card, issue provisional credit, reissue a card, or change recurring-payment settings. Those are banking actions requiring completed verification and applicable prerequisites.

Before the single `transfer_to_human_agents` call:

1. Read the complete current case record: opening request, all customer messages, every successful clarification, and every successful read-only observation.
2. Treat successful clarification responses as known facts. Do **not** describe any part of a successful response as unknown, unconfirmed, unavailable, or still needed.
3. Run `scripts/build_handoff_summary.py` with the complete records exactly as available. Do not reduce the clarification responses to counts or generic categories before passing them to the helper.
4. Review the returned summary. It must retain the card-specific facts and merchant/preference facts supplied by the customer. If `errors` is nonempty, fix the malformed input before transfer.
5. Call `transfer_to_human_agents` exactly once with the returned `reason` and `summary`.

If the helper cannot be run, create the equivalent summary manually: preserve every successful clarification question and answer, organize the facts by issue/card, and state only genuinely missing intake details. Never replace a supplied card label, card-possession status, merchant result, or recurring-payment preference with “unknown.”

## Transfer reason selection

Use `fraud_or_security_concern` when any reported issue includes unauthorized activity, suspected fraud, identity theft, or a lost/stolen card. This Tier-1 reason takes priority over concurrent ATM, subscription, or other billing issues and over a generic request to speak with a person.

Use `complex_billing_dispute` only when specialist review of ATM, subscription, or billing issues is required and no fraud/security condition applies. Use a lower-tier generic human-request reason only if no higher-priority reason applies.

## Required handoff contents

The transfer summary must be self-contained and accurately distinguish known facts from uncollected facts. Include, when available:

- The explicit request for a human agent; transaction/card scope; and unauthorized, ATM, and subscription/recurring issue types.
- The located customer name and user ID from successful read-only lookup, while clearly stating that lookup is not completed identity verification.
- Each supplied card or account label and its possession state, including a lost/not-possessed card and a retained/in-possession card.
- Each unauthorized claim and the customer’s stated fraud belief. Do not infer transaction channel, PIN status, or card-present/card-not-present classification.
- The card tied to the ATM issue and the card tied to the cancelled subscription/recurring issue.
- The subscription merchant, contact attempt, and merchant outcome.
- The customer’s future recurring-payment preference. If the customer declines a broad block, say plainly: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
- Read-only cross-product credit-card-check outcome if it was performed.
- Actions actually completed, followed by only genuinely absent dispute-intake details.

Keep issue-specific facts together. In particular, the receiving specialist must be able to see the subscription card and merchant in the same section, and the ATM card and ATM issue in the same section.

## Recurring-payment safeguard

Do not call `set_debit_card_recurring_block_7382` merely because a past subscription charge is disputed. A recurring block affects **all** recurring payments on that card. If the customer wants only a prior charge addressed, or declines a broad block, do not call the recurring-block tool.

Do not state that verification, a dispute, card closure/freeze, replacement, recurring block, provisional credit, or any other banking action happened unless the applicable action succeeded. A user-information lookup is not identity verification.

## Summary helper

`scripts/build_handoff_summary.py` is deterministic and non-executing. It reads a JSON object from stdin and writes a JSON object to stdout. It does not call banking tools or change customer data.

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input object:

- `opening` — nonempty customer opening/request string.
- `clarifications` — array of `{question, result, status}` records. Pass all records. Records whose status is `ok` or `success` are preserved as known case facts.
- `read_only_observations` — array of `{tool, result, status}` records. Pass all available observations. The helper extracts only customer name/user ID and credit-card-check outcome; it does not put lookup address, email, phone, or date of birth into the handoff.
- `verification_status` — optional string, defaulting to `not completed`.
- `actions_completed` — optional array of successfully completed actions.
- `unresolved_items` — optional array containing only facts absent from the complete current record.

Output object:

- `reason` — transfer reason recommended from the complete case text.
- `summary` — transfer-ready case summary.
- `errors` — malformed-input issues. Do not transfer while nonempty.
- `non_execution_notice` — confirmation that helper output performed no action.

Validate that the summary includes every successful customer answer, names the customer-provided cards and merchant when supplied, and does not call supplied facts unresolved. Then use its `reason` and `summary` unchanged in the transfer call.

## Later dispute processing

Only perform ordinary debit-dispute processing if a human handoff is not requested or a responsible specialist directs it. Before any banking action, verify identity, authority, ownership, product eligibility, account/card details, limits, and confirmation requirements. A lookup alone is not verification.

Before filing a debit-card dispute, validate the OPEN linked checking account, matching debit card and transaction, transaction amount of at least $1, transaction age within 60 days, and account-tier dispute capacity. Retrieve transaction history to identify transaction IDs; determine whether an ATM is bank-operated or third-party; file the earliest transaction when duplicates exist.

For unauthorized activity, explain Regulation E timing before filing: within two business days of the statement has maximum $50 liability, within 60 days has maximum $500 liability, and after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. If fraud is suspected, establish transaction channel before selecting card-present versus card-not-present fraud.

A post-cancellation recurring charge uses `recurring_charge_after_cancellation`. Determine provisional-credit eligibility from timely reporting, category, written statement, and OPEN unrestricted account status; mark it undetermined if facts are missing.
