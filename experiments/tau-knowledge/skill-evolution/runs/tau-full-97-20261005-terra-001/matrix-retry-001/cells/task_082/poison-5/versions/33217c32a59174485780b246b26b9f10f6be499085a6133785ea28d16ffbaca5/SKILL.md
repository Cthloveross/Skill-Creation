---
name: debit-card-fraud-human-handoff
description: Prepare and complete an immediate, fact-preserving human-agent handoff for customers reporting unauthorized debit-card activity, lost cards, ATM errors, and cancelled-subscription charges. Also provides the controlled intake workflow for later debit-card dispute filing.
---

# Debit-Card Fraud and Dispute Human Handoff

Use this Skill when a customer asks for a human agent about debit-card disputes, particularly where unauthorized activity, suspected fraud, or a lost/stolen card is also present.

## Immediate human-handoff workflow

An explicit request for a human agent permits an immediate transfer. Do **not** delay that transfer to file disputes, retrieve transactions, freeze/close a card, or change recurring-payment settings. Those are banking actions and require completed verification and their own prerequisites.

Before the one `transfer_to_human_agents` call, synthesize the handoff from **all** available case material:

1. The opening request and every customer message.
2. Every successful clarification result. A successful clarification is a known case fact; never describe it as unknown, unavailable, or still needed.
3. Successful read-only lookups. A located name/user record may be included in the handoff, but it does not constitute completed identity verification.
4. Only then identify genuinely missing dispute-filing details.

Use `scripts/build_handoff_summary.py` to turn the extracted facts into a transfer-ready summary. Resolve its `errors` before relying on the result. Call `transfer_to_human_agents` with the helper's `reason` and `summary`.

### Transfer reason priority

Use `fraud_or_security_concern` if **any** issue includes an unauthorized transaction, suspected fraud, identity theft, or a lost/stolen card. This Tier-1 reason takes precedence over a simultaneous ATM error, recurring-charge dispute, billing dispute, or generic request for a person.

Use `complex_billing_dispute` only when a billing/ATM/recurring issue requires a specialist and no fraud or security concern applies.

### Mandatory transfer-summary content

Write a self-contained case summary. It must contain:

- The explicit request for a human; the supplied transaction and card scope; and the words/categories **unauthorized**, **ATM**, and **subscription** when those issues were reported.
- The known customer name and user ID, if a successful lookup supplied them, followed by the distinct statement that verification is not completed unless it actually was completed.
- A card-by-card section retaining each customer-provided card/account label. For every named card, preserve its possession state and the claim(s) assigned to it.
- For each unauthorized claim, whether the customer believes it is fraudulent. Do not invent its transaction channel or card-present/card-not-present classification.
- The card associated with the ATM error, and ATM ownership/network only if supplied.
- The card associated with the cancelled subscription charge; the named merchant; that the charge followed cancellation; whether the customer contacted the merchant; and the merchant's stated outcome.
- The customer's future-payment preference. A past cancelled-subscription charge is a dispute, not permission to block future payments. If the customer declines a broad block, preserve this exact operational meaning: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
- Only actual completed actions, followed by genuinely unresolved filing facts (for example transaction IDs, internal card/account IDs, dates, amounts, channel, PIN status, ATM network, statement timing, written-statement consent, and eligibility).

Do not replace known card labels with “two cards,” or known issue assignments with a general issue list. Do not call a known merchant, possession status, customer name, merchant-contact result, or block preference unresolved.

### Limits before this immediate handoff

Do not file a dispute, freeze or close a card, reissue a card, provide provisional credit, or set a recurring-payment block before this immediate transfer unless the customer is verified and specifically requests that particular action.

Never invoke `set_debit_card_recurring_block_7382` merely because a customer wants a past subscription charge disputed. That tool blocks **all** recurring payments on a card. If the customer wants only a prior charge addressed or declines the broad block, do not call it.

Do not claim that a dispute, card action, payment block, credit-card check, credit-card offer, or verification happened unless a corresponding action actually succeeded.

## Summary helper

`scripts/build_handoff_summary.py` reads one JSON object from stdin and writes one JSON object to stdout. It is deterministic and non-executing: it does not call banking tools or alter customer data.

Run it after extracting all supplied facts, for example:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Input object:

- `human_requested` — boolean, required.
- `verification_status` — string, required, such as `not completed`.
- `customer_name` and `user_id` — optional strings from the conversation or successful read-only lookup.
- `reported_transaction_count` — optional positive integer.
- `cards` — nonempty array of card-specific objects:
  - `label` — customer-provided card/account label.
  - `possession` — `lost_not_possessed`, `still_possessed`, or `unknown`.
  - `unauthorized_reported` — boolean.
  - `fraud_suspected` — boolean when supplied.
  - `atm_issue` — optional description.
  - `recurring` — optional object with `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`.
- `actions_completed` — array of actions that actually succeeded.
- `unresolved_items` — array containing only facts genuinely absent from the case record.

The output contains `reason`, `summary`, `errors`, and `non_execution_notice`. Do not transfer using output with extraction/schema errors. Confirm before transfer that each supplied card label, possession distinction, issue-to-card assignment, merchant outcome, and recurring-block preference is visibly present in `summary`.

## Later debit-dispute workflow

Use this only when the customer is not being immediately transferred, or when a responsible specialist directs normal processing.

Before any banking action, verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient/card details, and confirmation requirements. A record lookup alone is not verification. For identity verification, confirm at least two of date of birth, email, phone number, and address, then create the runtime verification record.

Before filing, retrieve and validate the OPEN checking account, associated debit card, actual transaction, and open-dispute capacity for that account tier. Do not file unless the transaction is at least $1, no more than 60 days old, ownership/linkage match, and the account has capacity. Determine whether an ATM is bank-operated or third-party; for duplicates, file the earliest duplicate.

Collect transaction ID, account ID, card ID, user ID, transaction date, discovery date, amount, transaction type, possession status, PIN-compromise status, merchant-contact result, police-report status where applicable, written-statement consent, and provisional-credit eligibility facts.

For unauthorized activity, explain Regulation E timing before filing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and non-recovery. Do not infer statement timing from transaction date.

Use `unauthorized_transaction` only when fraud is not suspected. If fraud is suspected, establish channel before filing: use `card_present_fraud` for physical/in-store use and `card_not_present_fraud` for online/phone use. Do not guess the channel. A post-cancellation subscription charge uses `recurring_charge_after_cancellation`.

For filing metadata, fraud categories require `close_and_reissue`, non-fraud unauthorized activity requires `freeze_pending_investigation`, and other listed dispute categories require `keep_active`. After successful filings on one card, perform at most the most severe required actual card action. Filing metadata does not itself take that action.

Required provisional credit depends on timely statement reporting, a qualifying category, written statement, and an OPEN unrestricted account. If any required fact is missing, mark eligibility undetermined rather than inventing it.
