---
name: debit-card-fraud-human-handoff
description: Complete an immediate, fact-preserving human-agent handoff for a customer who requests a human agent about unauthorized debit-card activity, a lost or retained card, ATM errors, or cancelled recurring charges. Use it to preserve supplied clarification and lookup facts while avoiding unverified banking actions.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer requests a human agent for debit-card disputes and the case may include unauthorized activity, suspected fraud, or a lost/stolen card.

## Immediate handoff

An explicit request for a human agent permits immediate escalation. Do not delay that transfer to file disputes, retrieve transactions, freeze or close cards, reissue cards, issue provisional credit, or alter recurring-payment settings. Those are banking actions and require completed verification plus their applicable prerequisites.

Before making the one `transfer_to_human_agents` call:

1. Read the opening request, every customer message, every successful clarification, and every successful read-only observation already available in the runtime case record.
2. Treat a successful clarification answer as a known case fact. Do not ask for it again or label it unknown.
3. Run `scripts/build_handoff_summary.py` with the complete raw opening, clarification records, and read-only observations. Do not manually reduce the clarification record to generic counts before calling the helper.
4. Check that the returned `summary` contains the relevant known facts, not merely an assertion that information was collected. Resolve a returned `errors` item before transfer.
5. Call `transfer_to_human_agents` exactly once using the helper's `reason` and `summary`.

If the helper is unavailable, use its same fail-safe method: quote or faithfully reproduce every successful clarification question-and-answer pair in the handoff under a clearly marked known-facts section, then add concise operational routing. Never replace known card labels, possession states, merchant outcomes, or payment preferences with “unknown.”

## Transfer reason selection

Use `fraud_or_security_concern` when any reported issue includes unauthorized activity, suspected fraud, identity theft, or a lost/stolen card. This Tier-1 reason takes priority over simultaneous ATM, subscription, or other billing disputes and over the general desire to speak with a person.

Use `complex_billing_dispute` only if specialist billing/ATM/recurring-charge review is needed and no fraud or security condition applies. Use a lower-tier generic human-request reason only when no higher-tier reason applies.

## Required fact-preserving summary

The transfer summary must be self-contained. It must visibly preserve, where supplied:

- The customer’s explicit human-agent request; reported transaction count and card scope; and the unauthorized, ATM, and subscription issue types.
- A successful customer lookup's name and user ID, if available. State separately that lookup is not completed identity verification.
- Each customer-provided card/account label and its possession state, including which card was lost/not possessed and which remains held.
- Each unauthorized claim and the customer’s stated fraud belief. Do not invent transaction channel, PIN status, or card-present/card-not-present classification.
- The card assigned to an ATM issue and the card assigned to a post-cancellation subscription/recurring issue.
- The recurring merchant, merchant-contact result, and merchant outcome when supplied.
- The customer’s future recurring-payment preference. If the customer declines a broad recurring block, state: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
- Actions actually completed and only genuinely absent filing details.

Keep related facts close together. A receiving specialist must be able to identify the card associated with each issue rather than infer it from a disconnected list. Preserve the successful clarification Q&A in the summary as a data-integrity backstop; this prevents a card label, merchant name, refusal, or limited instruction from being lost during compression.

Do not call `set_debit_card_recurring_block_7382` merely because a customer disputes a previous subscription charge. A block affects all recurring payments on a card. When the customer wants only a past charge addressed or declines a broad block, do not call it.

Do not state that a dispute, card action, payment block, verification, credit-card check, or other action occurred unless the relevant tool action succeeded. A read-only user lookup is not identity verification.

## Summary helper

`scripts/build_handoff_summary.py` reads one JSON object on stdin and writes one JSON object on stdout. It is deterministic and non-executing: it neither calls banking tools nor changes customer data.

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input schema:

- `opening` — required nonempty customer opening/request string.
- `clarifications` — array of records with `question`, `result`, and `status`. Pass all records exactly as available. Every record whose status is `ok` or `success` is preserved in the output.
- `read_only_observations` — array of tool observations with `tool`, `result`, and `status`. Pass all available observations. The helper extracts only a located name/user ID and a credit-card-check outcome; it does not copy lookup PII such as address, email, phone, or date of birth.
- `verification_status` — optional string; defaults to `not completed`.
- `actions_completed` — optional array of actions actually completed successfully.
- `unresolved_items` — optional array containing only facts absent from the complete runtime record.

Output schema:

- `reason` — recommended transfer reason.
- `summary` — transfer-ready, fact-preserving text.
- `errors` — input-validation issues. Do not transfer while nonempty.
- `non_execution_notice` — confirms no action occurred.

## Later debit-dispute processing

Use ordinary dispute processing only if a human handoff is not requested or a responsible specialist directs it. Before any banking action, verify identity, authority, ownership, eligibility, account/card details, limits, and confirmation requirements. A lookup alone is not verification.

Before filing a debit-card dispute, validate the OPEN linked checking account, matching debit card and transaction, transaction amount of at least $1, transaction age within 60 days, and account-tier dispute capacity. Retrieve transaction history to identify transaction IDs; determine whether an ATM is bank-operated or third-party; file the earliest transaction when duplicates exist.

For unauthorized activity, explain Regulation E timing before filing: within two business days of the statement has maximum $50 liability, within 60 days has maximum $500 liability, and after 60 days may mean unlimited liability. Do not infer statement timing from transaction date. If fraud is suspected, establish the transaction channel before selecting card-present versus card-not-present fraud; do not guess.

A post-cancellation recurring charge uses `recurring_charge_after_cancellation`. Provisional-credit eligibility must be determined from timely reporting, category, written statement, and OPEN unrestricted account status. Mark it undetermined when facts are missing rather than inventing them.
