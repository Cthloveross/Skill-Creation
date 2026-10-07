---
name: debit-card-dispute-human-handoff
description: Triage debit-card fraud, unauthorized transactions, lost cards, ATM errors, and recurring charges after cancellation. Use when a customer requests a human agent for debit-card issues or when preparing a verified debit-card dispute.
---

# Debit-Card Dispute and Human-Handoff Workflow

Use this Skill to distinguish an immediate human handoff from debit-dispute filing. The packaged helper creates a handoff recommendation only; it never performs a banking action.

## Mandatory controls

Before **any banking action**, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A record lookup is not identity verification. Before filing a dispute, freezing or closing a card, or changing recurring-payment settings, confirm at least two of the customer's date of birth, email, phone number, and address, then use the runtime verification-record capability. Do not disclose full card numbers, internal fraud flags, or security-detection details.

Without completed verification, do not file disputes, change cards, or set recurring-payment blocks. A requested human transfer may proceed without verification, provided the summary says verification is not completed.

## Immediate path: explicit request for a human

When the customer explicitly requests a human agent, transfer promptly. Do not delay the transfer merely to obtain every dispute-filing prerequisite, retrieve transaction history, perform a card action, or file a dispute.

Before the single `transfer_to_human_agents` call:

1. Read the opening request, all customer messages, every successful clarification response, and all supplied read-only observations.
2. Treat a successful clarification response as a known current-case fact. Do not call it unavailable, unknown, unconfirmed, or outstanding.
3. Retain supplied customer-facing card or account labels even when internal card IDs have not been retrieved.
4. Make a card-by-card fact map. Assign every unauthorized, ATM, and recurring-charge claim to the card identified by the customer.
5. If a customer record was located, include the appropriate name and user ID for the receiving agent, but state separately that lookup does not prove verification.
6. Build and review the structured handoff with `scripts/build_handoff_summary.py`. Correct the structured facts if an available fact is missing. Then use the helper's `reason` and `summary` in the transfer call.

Do not use generic “details unavailable” language as a substitute for reviewing completed clarifications. Only list an item as unresolved when it was genuinely not supplied.

### Reason selection

Use `fraud_or_security_concern` whenever any reported issue includes unauthorized activity, suspected fraud, identity theft, a lost or stolen card, or another security concern. It is Tier 1 and takes priority over simultaneous ATM, recurring-charge, billing, or generic human-request reasons.

Use `complex_billing_dispute` only if billing specialist review is required **and no** fraud/security concern applies. Do not downgrade a fraud case because it also includes a billing dispute.

### Required handoff content

The summary must be self-contained and factual. Include:

- **Scope:** explicit human request; transaction count and card count when supplied; unauthorized, ATM, and subscription/recurring issue types. Spell out supplied small counts as well as including digits where practical.
- **Customer and verification:** known name and/or user ID, and whether identity verification is complete.
- **Card-by-card routing:** each supplied card label; physical possession state; unauthorized/fraud claim; and all issues assigned to that card.
- **Unauthorized claims:** whether the customer believes the transactions are fraudulent. Do not invent transaction channel or classify as card-present/card-not-present unless it was supplied.
- **ATM claim:** card assignment, reported ATM error, and ATM owner/network only when known.
- **Recurring claim:** card assignment, named merchant, charge after cancellation, whether the merchant was contacted, and the reported merchant outcome.
- **Future-payment preference:** distinguish a past-charge dispute from a future card-wide recurring block. If the customer declined the broad block, state: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
- **Actions and genuine gaps:** list only actions that actually succeeded. State real remaining filing information such as transaction/card/account IDs, dates, amounts, transaction channel, PIN status, ATM network, statement timing, written-statement consent, and eligibility facts when absent.

Never label supplied card labels, possession state, card assignment, merchant, merchant-contact outcome, customer identity, or recurring-block preference as unknown. Do not claim a dispute, freeze, closure, replacement, credit-card offer, provisional credit, or recurring-payment change occurred unless it actually succeeded.

### Action limits during immediate handoff

Do not file a debit dispute, close/freeze a card, or change recurring-payment settings before this immediate handoff unless the customer is verified and specifically requests that action.

A recurring-payment block stops **all** recurring payments on a card. A charge after cancellation is a past-charge dispute and does not authorize a broad future-payment block. If the customer wants only a past merchant charge addressed, or declines the broad block, do not call the recurring-block tool.

A lost or stolen card is a security concern. If verified self-service protection later continues, follow the normal card-protection process and check for bank credit cards as required. Do not state that a cross-product check or offer occurred unless it did.

## Read-only preparation and dispute filing

Use this path only when immediate transfer is not required or after the responsible human specialist directs normal processing.

1. Verify identity and ownership.
2. Retrieve customer accounts and select the linked **OPEN checking** account.
3. Retrieve debit cards; verify card ID, status, linked account, and cardholder user ID.
4. Retrieve account transactions and identify the actual transaction. Results are reverse chronological; do not assume the first result is the target.
5. Retrieve dispute history and count open disputes per account: Entry 2, Mid 3, Premium 4, Elite 5.
6. For an ATM issue, determine bank-operated versus third-party ATM. For duplicate transactions, dispute the earliest duplicate.

Do not file unless identity is verified; the transaction is at least $1 and no more than 60 days old; the linked checking account is OPEN; ownership and linkage match; and the account has open-dispute capacity.

Collect transaction ID, account ID, card ID, user ID, transaction date, discovery date, amount, transaction type, possession status, PIN-compromise status, merchant-contact status, police-report status where applicable, written-statement consent, and all eligibility facts.

Before filing an unauthorized claim, explain and record Regulation E timing: within two business days of the statement means maximum $50 liability; within 60 days means maximum $500; after 60 days may mean unlimited liability and non-recovery. Do not infer statement timing from transaction date.

## Classification, credit, and card follow-up

Use `unauthorized_transaction` only for unauthorized activity where fraud is not suspected. When fraud is suspected, establish the channel before filing: use `card_present_fraud` for physical/in-store fraud and `card_not_present_fraud` for online or telephone fraud. Do not guess the channel.

Other categories are `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, and `recurring_charge_after_cancellation`. File one category per dispute. Valid transaction types are `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`.

Required provisional credit requires timely statement reporting, a qualifying category (unauthorized, either fraud category, ATM cash discrepancy, or duplicate), a written statement, and an OPEN unrestricted account. Mark it undetermined if evidence is missing. It is not required for recurring-cancellation, goods/services, ATM-deposit, or incorrect-amount claims, or applicable policy exclusions.

For filing metadata, use `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` for other categories. After all successful filings on one card, perform only the highest required actual action: close/reissue, then freeze, then keep active. Filing metadata does not itself change the card.

## Handoff-summary helper

`scripts/build_handoff_summary.py` reads one JSON object from stdin and writes one JSON object to stdout. It does not parse customer prose and does not call banking tools. The executor must extract the runtime conversation and observations into this schema before running it.

Input schema:

- `human_requested` (boolean, required)
- `verification_status` (string, required; for example, `not completed`)
- `customer_identity` (optional string)
- `customer_user_id` (optional string)
- `reported_transaction_count` (optional positive integer)
- `cards` (nonempty array), each with:
  - `label` (nonempty string)
  - `possession` (`lost_not_possessed`, `still_possessed`, or `unknown`)
  - `unauthorized_reported` (boolean)
  - `fraud_suspected` (boolean when known)
  - `atm_issue` (optional string)
  - `recurring` (optional object with `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`)
- `actions_completed` (array of strings)
- `unresolved_items` (array containing only genuinely missing facts)

Run:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Output schema:

- `reason`: recommended transfer reason, or `null`
- `summary`: transfer-ready factual summary
- `errors`: schema/extraction errors to resolve before relying on the output
- `non_execution_notice`: confirms no action was taken

Before transfer, ensure the generated summary contains every supplied card label, possession distinction, issue-to-card assignment, known merchant/contact outcome, and known broad-block preference. If any supplied fact is absent, correct the structured input and regenerate; do not add the fact to `unresolved_items`.
