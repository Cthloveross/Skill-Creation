---
name: debit-card-dispute-human-handoff
description: Safely triage debit-card fraud, unauthorized transactions, lost cards, ATM errors, and recurring charges after cancellation. Use for a requested human-agent transfer or for validated preparation and filing of debit-card disputes.
---

# Debit-Card Dispute and Human-Handoff Workflow

This Skill distinguishes an immediate human handoff from dispute filing. Scripts only prepare text and validate structured facts; they never perform banking actions.

## Mandatory safety controls

Before **any banking action**, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A database lookup is not verification. Verify the customer by having them confirm at least two of date of birth, email, phone number, and address, then record successful verification using the runtime verification capability. Do not disclose full card numbers, internal fraud flags, or security-detection details.

Without verification, do not file a dispute, freeze or close a card, or change recurring-payment settings. An explicit request for a human agent may still be transferred safely; accurately state that verification has not been completed.

## Priority path: customer explicitly requests a human

When a customer explicitly asks for a human agent, complete the handoff promptly. Do **not** delay solely to collect every dispute-filing prerequisite or perform card/dispute actions.

Before the transfer call, perform this short, required preparation:

1. Review the opening message, every prior customer message, every clarification answer, and supplied read-only observations.
2. Make a fact table of all supplied facts. A response to a clarification is a **known fact**, not an open intake item.
3. Build one factual, card-by-card transfer summary. Preserve card/account labels even if internal IDs are unknown.
4. Call `transfer_to_human_agents` once with the highest-priority applicable reason and that summary.

### Transfer-reason selection

Use `fraud_or_security_concern` if any reported issue includes unauthorized activity, suspected fraud, identity theft, a lost/stolen card, or another security concern. This Tier-1 reason takes priority over concurrent ATM, subscription, or billing issues and over generic human-request reasons.

Use `complex_billing_dispute` only where specialist billing review is needed and no fraud/security concern applies. Do not downgrade a fraud case merely because it also includes a billing dispute.

### Required handoff-summary content

The transfer summary must preserve all facts available at the time of handoff and distinguish known facts from unresolved intake. Use clear labeled sentences in this order:

1. **Request and scope:** human request, reported number of transactions and cards, and all issue types.
2. **Customer/verification:** customer name or user ID if supplied; verification status. A lookup is not verification.
3. **Each named card/account:** label, possession status, and every issue attached to that card.
   - For a lost card, state that it is lost and the customer no longer has it.
   - For a retained card, state that the customer still has it/in possession.
4. **Unauthorized claims:** identify the card for each and whether the customer believes it is fraud. Do not guess card-present versus online/telephone channel.
5. **ATM claim:** identify its card and the reported ATM problem. Mark ATM owner/network unresolved only if absent.
6. **Recurring claim:** identify its card and merchant, state that the charge followed cancellation, whether merchant contact occurred, and the actual merchant outcome.
7. **Limited future-payment instruction:** distinguish a dispute of an already-posted charge from a request to block future payments. If the customer declined a card-wide recurring block, say so plainly.
8. **Actions and genuine gaps:** state only actions actually completed. List only facts not supplied, such as transaction IDs, dates, amounts, internal card/account IDs, channel, PIN status, ATM network, statement timing, written-statement consent, and filing eligibility.

Never describe a known card label, possession state, merchant, merchant-contact outcome, or recurring-block instruction as unknown. Never replace a known merchant with “merchant unknown.” Keep the named card and its assigned ATM or recurring claim near each other in the summary.

A generic structure is:

```text
Customer requests a human agent for [scope]. Fraud/security concern is present.
Customer: [known identity if supplied]. Verification: [status].
[Card label]: [possession]. Unauthorized claim: [known status]. [Assigned ATM or recurring claim].
[Other card label]: [possession]. Unauthorized claim: [known status]. [Assigned ATM or recurring claim].
Recurring claim: [merchant] on [card], charged after cancellation; merchant contact: [outcome]. Customer wants the past charge addressed and [does/does not] want a card-wide block of all recurring payments.
Actions completed: [actual actions only]. Still needed: [genuine unknowns only].
```

This template is a fact-preservation aid, not permission to invent missing details.

### Immediate-handoff action limits

Do not file debit disputes, close/freeze cards, or enable/disable recurring-payment blocks before this immediate handoff unless the customer is verified and specifically requests the action. Do not claim an action happened when it did not.

A recurring-payment block stops **all** recurring payments on a card. A past charge after cancellation is a dispute issue, not authorization for a broad future-payment block. If the customer wants only a past merchant charge addressed, or declines the broad block, do not call the recurring-block tool.

A lost/stolen card is a security concern. After verification, if self-service continues and protection is requested, follow normal card-protection procedures and check for bank credit cards as required by policy. Do not claim an offer, replacement, closure, or freeze occurred unless it did.

## Read-only preparation and dispute filing

For a customer who does not require immediate handoff, or after a handoff directs normal processing:

1. Verify identity and ownership.
2. Retrieve accounts and select the linked **OPEN checking** account.
3. Retrieve debit cards; verify card ID, status, linked account, and cardholder user ID.
4. Retrieve transactions and identify the actual reported transaction. Transaction results are reverse chronological; do not assume the first result is the disputed transaction.
5. Retrieve dispute history and count open disputes per account, not per customer: Entry 2, Mid 3, Premium 4, Elite 5.
6. For an ATM issue, determine whether the ATM is bank-operated or third party. For duplicates, dispute the earliest transaction in the duplicate set.

Do not file unless the customer is verified; transaction amount is at least $1; transaction is no more than 60 days old; linked checking account is OPEN; ownership/linkage match; and the account has remaining open-dispute capacity.

Collect transaction ID, account ID, card ID, user ID, transaction date, discovery date, amount, transaction type, possession status, PIN-compromise status, merchant-contact status, police-report status where applicable, written-statement consent, and all eligibility facts.

Before filing an unauthorized claim, explain and record Regulation E reporting timing: within two business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may result in unlimited liability and non-recovery. Do not infer statement timing from transaction date.

## Classification and follow-up

Use `unauthorized_transaction` only when the transaction was unauthorized but fraud is not suspected. For suspected fraud, establish channel before classification: use `card_present_fraud` for physical-card/in-store fraud and `card_not_present_fraud` for online/telephone fraud. Do not guess the channel.

Other supported categories include `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, and `recurring_charge_after_cancellation`. Use exactly one category per filing.

Use one of these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Required provisional credit is established only when timely statement reporting, qualifying category (unauthorized, either fraud category, ATM cash discrepancy, or duplicate), written statement, and OPEN unrestricted account are all established. Mark missing facts as undetermined; do not claim eligibility without evidence. It is not required for recurring-cancellation, goods/services, ATM-deposit, or incorrect-amount claims, or in other policy exclusions.

Record filing `card_action` as `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` for other categories. After all successful filings for one card, take only the highest required actual action: close/reissue, then freeze, then keep active. Filing metadata does not itself alter the card.

## Summary helper

Use `scripts/build_handoff_summary.py` when structured facts have been extracted from the conversation. It reads one JSON object from stdin and emits one JSON object on stdout. It does not parse customer prose, invoke tools, or execute transfers.

Input schema:

- `human_requested` (boolean)
- `verification_status` (string)
- `customer_identity` (optional string)
- `reported_transaction_count` (optional integer)
- `cards` (nonempty array). Each card has `label` (string), optional `possession` (`lost_not_possessed`, `still_possessed`, `unknown`), optional `unauthorized_reported` (boolean), optional `fraud_suspected` (boolean), optional `atm_issue` (string), and optional `recurring` object.
- Each `recurring` object may have `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`.
- `actions_completed` and `unresolved_items` (arrays of strings).

Example invocation using a runtime-created JSON file:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

The output includes `reason`, `summary`, `errors`, and `non_execution_notice`. Before transfer, confirm the summary names every supplied card and maps known claims to it; retains supplied merchant contact/outcome and broad-block preference; uses `fraud_or_security_concern` when unauthorized/security facts are present; and lists only genuine gaps.
