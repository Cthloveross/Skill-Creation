---
name: debit-card-dispute-human-handoff
description: Triage debit-card fraud, unauthorized transactions, lost cards, ATM errors, and recurring charges after cancellation. Use for an explicit human-agent request or for verified debit-card dispute preparation and filing.
---

# Debit-Card Dispute and Human-Handoff Workflow

This Skill separates a prompt human handoff from dispute filing. Packaged scripts prepare and validate a handoff summary only; they never perform banking actions.

## Mandatory safety controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A customer-record lookup is not identity verification. Before filing a dispute, changing a card, or changing recurring-payment settings, have the customer confirm at least two of date of birth, email, phone number, and address, then record success with the runtime verification capability. Do not disclose full card numbers, internal fraud flags, or security-detection details.

Without verification, do not file disputes, freeze or close cards, or enable/disable recurring-payment blocks. A requested human transfer may proceed without verification; clearly state that verification has not been completed.

## Immediate path: explicit human-agent request

When the customer explicitly asks for a human, transfer promptly. Do not delay the transfer merely to collect every filing prerequisite, perform a card action, or file a dispute.

Before calling `transfer_to_human_agents`:

1. Consolidate the opening message, all customer messages, all completed clarification responses, and applicable supplied read-only observations.
2. Treat each answered clarification as a **known current-case fact**. Do not summarize it as unknown, absent, unconfirmed, or still needed.
3. Preserve lookup facts that are appropriate for the receiving agent, such as the located customer name and user ID. State separately that lookup does not establish verification.
4. Create a card-by-card fact map before writing the summary. Retain customer-facing card/account labels even if internal card/account IDs have not been retrieved.
5. Build the structured summary with `scripts/build_handoff_summary.py`, review its `errors`, and use its `reason` and `summary` for exactly one transfer call. If extraction is incomplete, add only genuinely unresolved items; never replace a supplied fact with a gap.

### Transfer reason priority

Use `fraud_or_security_concern` when any issue includes unauthorized activity, suspected fraud, identity theft, a lost/stolen card, or another security concern. This Tier-1 reason takes priority over simultaneous ATM, recurring-charge, billing, or generic human-request reasons.

Use `complex_billing_dispute` only when specialist billing review is needed and no fraud/security concern applies. Do not downgrade a fraud case because it also includes billing issues.

### Required transfer summary

The handoff summary must be self-contained and factual. Include, in a readable card-by-card order:

1. **Scope:** the human request, reported transaction and card count when supplied, and each reported issue type.
2. **Customer and verification:** supplied name and/or user ID; explicitly distinguish a located record from completed verification.
3. **Every named card/account:** its exact supplied label, possession state, unauthorized/fraud claim, and all claims assigned to that card.
4. **Unauthorized claims:** whether the customer believes each is fraud. Do not invent the transaction channel or classify it as card-present versus card-not-present unless supplied.
5. **ATM claim:** its assigned card, the ATM error, and ATM owner/network as unresolved only if not provided.
6. **Recurring claim:** its assigned card, named merchant, charge after cancellation, merchant-contact status, and merchant outcome.
7. **Future-payment preference:** distinguish the past-charge dispute from a broad future recurring-payment block. If the customer declined a card-wide block, say explicitly: `Customer does not want all recurring payments blocked; do not block recurring payments card-wide.`
8. **Actual actions and real gaps:** state only actions actually completed. List transaction IDs, internal account/card IDs, dates, amounts, channel, PIN status, ATM network, statement timing, written-statement consent, and filing eligibility only when they were not supplied.

Never label a known card label, possession state, merchant, merchant-contact outcome, card assignment, customer identity, or recurring-block instruction as unknown. Keep each card label close to its ATM or recurring claim so a receiving specialist can route it correctly.

Do not claim a dispute, freeze, closure, replacement, credit-card offer, or recurring-payment change occurred unless the corresponding action actually succeeded.

### Action limits during immediate transfer

Do not file debit disputes, close/freeze cards, or change recurring-payment settings before this immediate handoff unless the customer is verified and specifically asks for that action.

A recurring-payment block stops **all** recurring payments on a card. A past charge after cancellation is a dispute issue, not permission for a broad future-payment block. If the customer only wants a past merchant charge addressed, or declines the broad block, do not use the recurring-block tool.

A lost or stolen card is a security concern. If verified self-service protection later continues, follow normal card-protection procedure and check for bank credit cards as required. Do not represent a cross-product check or offer as completed unless it occurred.

## Read-only preparation and dispute filing

Use this path only where immediate human transfer is not required, or after the human specialist directs normal processing.

1. Verify identity and ownership.
2. Retrieve customer accounts and choose the linked **OPEN checking** account.
3. Retrieve debit cards and verify card ID, status, account linkage, and cardholder user ID.
4. Retrieve account transactions and identify the actual disputed transaction; results are reverse chronological, so do not assume the first result is the target.
5. Retrieve dispute history and count open disputes per account, not per customer: Entry 2, Mid 3, Premium 4, Elite 5.
6. For an ATM claim, determine whether the ATM is bank-operated or third party. For duplicate transactions, dispute the earliest duplicate.

Do not file unless identity is verified; transaction amount is at least $1; transaction is no more than 60 days old; linked checking account is OPEN; ownership/linkage match; and the checking account has remaining open-dispute capacity.

Collect transaction ID, account ID, card ID, user ID, transaction date, discovery date, amount, transaction type, possession status, PIN-compromise status, merchant-contact status, police-report status where applicable, written-statement consent, and all filing-eligibility facts.

Before filing an unauthorized claim, explain and record Regulation E timing: reporting within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may result in unlimited liability and non-recovery. Do not infer statement timing from transaction date.

## Classification, provisional credit, and card follow-up

Use `unauthorized_transaction` only where the transaction was unauthorized but fraud is not suspected. For suspected fraud, establish channel before filing: use `card_present_fraud` for physical-card/in-store fraud and `card_not_present_fraud` for online/telephone fraud. Do not guess the channel.

Other categories are `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, and `recurring_charge_after_cancellation`. Use exactly one category per filing. Valid transaction types are `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`.

Required provisional credit is established only when timely statement reporting, a qualifying category (unauthorized, either fraud category, ATM cash discrepancy, or duplicate), a written statement, and an OPEN unrestricted account are established. Mark eligibility undetermined if any evidence is missing. It is not required for recurring-cancellation, goods/services, ATM-deposit, or incorrect-amount claims, or applicable policy exclusions.

For filing metadata, use `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` for other categories. After all successful filings on one card, perform only the highest required actual action: close/reissue, then freeze, then keep active. Filing metadata itself does not change the card.

## Handoff-summary helper

`scripts/build_handoff_summary.py` reads one JSON object from stdin and emits one JSON object on stdout. It neither parses customer prose nor calls banking tools; the executor first extracts the conversation and observation facts into the schema below.

Input schema:

- `human_requested` (boolean, required)
- `verification_status` (string, required; for example, `not completed`)
- `customer_identity` (optional string)
- `customer_user_id` (optional string)
- `reported_transaction_count` (optional positive integer)
- `cards` (nonempty array). Each card has:
  - `label` (nonempty string)
  - `possession` (`lost_not_possessed`, `still_possessed`, or `unknown`)
  - `unauthorized_reported` (boolean)
  - `fraud_suspected` (boolean)
  - `atm_issue` (optional string)
  - `recurring` (optional object with `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`)
- `actions_completed` (array of strings)
- `unresolved_items` (array of strings containing only real gaps)

Run it with:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Output schema:

- `reason`: recommended transfer reason or `null`
- `summary`: factual transfer summary
- `errors`: extraction/schema problems that must be resolved before relying on the output
- `non_execution_notice`: confirms that no banking action was performed

Before transfer, verify that the generated summary includes every supplied card label, possession distinction, issue-to-card assignment, known merchant and outcome, and any supplied refusal of a broad recurring-payment block. If a known fact is missing, correct the structured input and regenerate the summary; do not add it to `unresolved_items`.
