---
name: debit-card-fraud-human-handoff
description: Prepare and complete an immediate, fact-preserving human-agent handoff for customers reporting unauthorized debit-card activity, lost cards, ATM errors, and cancelled-subscription charges. Also provides the controlled intake workflow for later debit-card dispute filing.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer asks for a human agent about debit-card disputes, particularly where unauthorized activity, suspected fraud, or a lost/stolen card is also present.

## Immediate human-handoff workflow

An explicit request for a human agent permits an immediate transfer. Do **not** delay the transfer to file disputes, retrieve transactions, freeze or close a card, or change recurring-payment settings. Those are banking actions and require completed verification plus their own prerequisites.

Before the single `transfer_to_human_agents` call, create the summary from the complete runtime case record, in this order:

1. Read the opening request and every customer message.
2. Read every clarification whose status is successful. Its result is a known case fact, not an open question.
3. Read successful read-only observations. If a user lookup identified a customer name and user ID, include those as a located record, while accurately stating that lookup is not completed identity verification.
4. Separate facts into card-specific claims. Do not collapse named cards into a generic count of cards.
5. List only facts actually absent from the record as unresolved intake items.
6. Review the proposed summary against the pre-transfer checklist below, then make the transfer.

A later clarification supersedes an earlier ambiguous statement only where it directly addresses the same fact. Never say a fact is unknown, unconfirmed, unavailable, or still needed if a successful clarification or read-only observation supplied it.

Use `scripts/build_handoff_summary.py` after extracting all runtime facts. It produces a deterministic transfer recommendation but performs no banking action. Resolve returned `errors` before using its output. Call `transfer_to_human_agents` exactly once with the helper's `reason` and `summary`.

## Transfer reason priority

Use `fraud_or_security_concern` if **any** issue includes an unauthorized transaction, suspected fraud, identity theft, or a lost/stolen card. This Tier-1 reason takes precedence over a simultaneous ATM error, cancelled recurring charge, other billing dispute, or generic request for a person.

Use `complex_billing_dispute` only when a billing, ATM, or recurring-charge issue needs specialist review and no fraud or security concern applies. Use lower-tier generic human-request reasons only if no applicable Tier-1 or Tier-2 reason exists.

## Required summary structure and pre-transfer checklist

The transfer summary must be self-contained, accurate, and useful to the receiving specialist. Before transfer, confirm it visibly includes all applicable items below:

- The explicit request for a human agent; the reported transaction and card scope; and the terms **unauthorized**, **ATM**, and **subscription** for those reported issue types.
- Known customer name and user ID from a successful lookup, if available. State separately whether identity verification is complete; a lookup alone is not verification.
- A `Card-by-card routing` section that retains every customer-provided card or account label exactly enough to distinguish cards.
- For each named card, whether it is lost/not possessed, retained/still possessed, or genuinely unknown.
- Each unauthorized claim and whether the customer believes it is fraud. Do not invent transaction channel, PIN compromise, or a card-present/card-not-present classification.
- The specific card assigned to the ATM error. Include the ATM network/operator only if it was supplied.
- The specific card assigned to the cancelled subscription charge, the merchant name, that the charge was after cancellation, whether the customer contacted the merchant, and the reported merchant outcome.
- The customer’s future-payment instruction. A request to dispute a prior subscription charge is not consent to block future recurring payments. Where the customer declines the broad block, use this operationally unambiguous statement: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
- Actions actually completed before transfer, followed by only truly unresolved filing information.

A useful final review asks: “Can the specialist tell which named card is lost, which one remains held, where each unauthorized claim belongs, which card has the ATM issue, which card has the subscription issue, what the merchant did, and whether a broad future-payment block was declined?” If not, fix the summary before transferring.

Do not replace known card labels with “two cards,” list issues in a disconnected general sentence, or put a known assignment into the unresolved section. Do not put customer PII beyond the located name and user ID into the summary unless necessary for the handoff and authorized by the runtime policy.

### Summary wording pattern

Use card-local sentences so claims remain unambiguous, for example:

- `[card label]: [possession state]. Unauthorized transaction reported; [fraud belief].`
- `[card label]: ATM issue: [reported error].`
- `[card label]: Subscription/recurring claim: [merchant]; charge occurred after cancellation; customer contacted the merchant; merchant outcome: [outcome].`
- `Customer wants the past charge addressed only. Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`

These are templates, not facts. Populate them only from the current runtime record.

## Limits before immediate handoff

Do not file a dispute, freeze or close a card, reissue a card, provide provisional credit, or set a recurring-payment block before this immediate transfer unless the customer has been verified and specifically requests that action.

Never invoke `set_debit_card_recurring_block_7382` merely because a customer wants a past subscription charge disputed. It blocks **all** recurring payments on the card. If the customer wants only a prior charge addressed or declines the broad block, do not call it.

Do not claim a dispute, card action, payment block, credit-card check, credit-card offer, verification, or other action occurred unless the corresponding tool action actually succeeded. A successful read-only lookup may be reported as a located record, but is not a banking action or verification.

## Summary helper

`scripts/build_handoff_summary.py` reads one JSON object from stdin and writes one JSON object to stdout. It is deterministic and non-executing: it does not call banking tools or alter customer data.

Run it after extracting all supplied facts:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input object schema:

- `human_requested` — boolean, required and must be `true` for a transfer recommendation.
- `verification_status` — nonempty string, required, such as `not completed`.
- `customer_name`, `user_id` — optional strings from a successful customer lookup or the conversation.
- `reported_transaction_count` — optional positive integer from the opening request.
- `cards` — nonempty array of card-specific objects. Each object contains:
  - `label` — customer-provided card/account label.
  - `possession` — `lost_not_possessed`, `still_possessed`, or `unknown`.
  - `unauthorized_reported` — boolean.
  - `fraud_suspected` — boolean if supplied.
  - `atm_issue` — optional description.
  - `recurring` — optional object with `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`.
- `actions_completed` — array of actions that actually succeeded; use an empty array when none occurred.
- `unresolved_items` — array of details genuinely absent from the complete case record.

Output object fields:

- `reason` — recommended transfer reason.
- `summary` — transfer-ready text.
- `errors` — schema or extraction problems. Do not transfer using a result with errors.
- `non_execution_notice` — confirms that the helper did not perform an action.

After generating the output, compare it to every successful clarification and lookup. In particular, verify each supplied card label, possession distinction, issue-to-card assignment, merchant/contact outcome, and recurring-block preference occurs in `summary`, rather than in `unresolved_items`.

## Later debit-dispute workflow

Use this workflow only when the customer is not being immediately transferred, or when a responsible specialist directs ordinary processing.

Before any banking action, verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient/card details, and confirmation requirements. A record lookup alone is not verification. For identity verification, confirm at least two of date of birth, email, phone number, and address, then create the runtime verification record.

Before filing, retrieve and validate the OPEN checking account, associated debit card, actual transaction, and open-dispute capacity for that account tier. Do not file unless the transaction is at least $1, no more than 60 days old, ownership and linkage match, and the account has capacity. Determine whether an ATM is bank-operated or third-party; for duplicates, file the earliest duplicate.

Collect transaction ID, account ID, card ID, user ID, transaction date, discovery date, amount, transaction type, possession status, PIN-compromise status, merchant-contact result, police-report status where applicable, written-statement consent, and provisional-credit eligibility facts.

For unauthorized activity, explain Regulation E timing before filing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and non-recovery. Do not infer statement timing from transaction date.

Use `unauthorized_transaction` only when fraud is not suspected. If fraud is suspected, establish channel before filing: use `card_present_fraud` for physical/in-store use and `card_not_present_fraud` for online/phone use. Do not guess the channel. A post-cancellation subscription charge uses `recurring_charge_after_cancellation`.

For filing metadata, fraud categories require `close_and_reissue`, non-fraud unauthorized activity requires `freeze_pending_investigation`, and other listed dispute categories require `keep_active`. After successful filings on one card, perform at most the most severe required actual card action. Filing metadata does not itself take that action.

Required provisional credit depends on timely statement reporting, a qualifying category, written statement, and an OPEN unrestricted account. If any required fact is missing, mark eligibility undetermined rather than inventing it.
