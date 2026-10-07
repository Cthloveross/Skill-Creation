---
name: debit-card-dispute-and-human-transfer
description: Triage debit-card fraud, unauthorized transactions, ATM errors, and recurring-charge disputes; safely prepare a complete human-agent handoff or validate a dispute-filing plan. Use when a customer requests a human agent or reports debit-card transaction problems.
---

# Debit Card Dispute and Human-Transfer Workflow

Use this Skill for debit-card disputes, suspected fraud, lost cards, ATM errors, and recurring charges after cancellation. It tells the executor how to use normal banking tools; packaged scripts are planning aids and never perform banking actions.

## Mandatory controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A database lookup is not identity verification. To verify identity, have the customer confirm at least two of date of birth, email, phone number, and address, then log the successful verification with the runtime's verification-record capability. Do not disclose full card numbers, security flags, or internal fraud-detection information.

If identity or ownership is not verified, do not file a dispute, close/freeze a card, or block recurring payments. A human transfer may still be used to safely route an explicit fraud/security request; state the verification status accurately in its summary.

## Immediate requested-human path

When the customer explicitly asks for a human agent, do not delay the transfer solely to finish dispute filing or to gather every filing prerequisite. First, consolidate **all facts already supplied** in the opening message, prior messages, clarification answers, and read-only observations. Then transfer using the highest-priority applicable reason.

Use `fraud_or_security_concern` when the report includes suspected fraud, unauthorized activity believed fraudulent, a lost/stolen card, identity theft, or another security concern. This Tier-1 reason takes priority over `complex_billing_dispute` and generic human-request reasons. Use `complex_billing_dispute` only if no fraud/security reason applies.

Do not perform debit-dispute filings, card closure/freezing, or recurring-payment changes before an immediate requested-human handoff unless the customer has completed the applicable verification and specifically requests that action. Do not claim that such an action occurred when it did not.

### Handoff-summary completeness rule

The receiving specialist must be able to distinguish each reported dispute. A fact supplied in a clarification is known and **must not** be described as unavailable, unknown, or outstanding. Record unknowns only when they truly were not supplied.

Write a concise, structured summary with these sections:

1. **Request and scope** — the customer requested a human; number of disputed transactions/cards; all issue types reported.
2. **Card-by-card facts** — for each named account/card label, state the label, whether the card is lost/not possessed or still possessed, and every issue assigned to it. A card label is useful routing information even when its internal card ID is not yet known.
3. **Unauthorized activity** — identify each affected card and whether fraud is suspected. Do not infer physical versus online/telephone transaction channel if not supplied.
4. **ATM issue** — identify the affected card and the reported error; separately identify ATM network/operator as unresolved only if it was not provided.
5. **Recurring-charge issue** — identify the affected card, merchant if supplied, that the charge followed cancellation, whether the customer contacted the merchant, and the merchant outcome.
6. **Customer instructions** — distinguish a request to dispute a past charge from a request to stop future recurring payments. Explicitly preserve a refusal of a card-wide recurring-payment block.
7. **Status/open intake** — accurately state verification and actions completed. List only genuinely unresolved transaction IDs, dates, amounts, account/card IDs, card channel, PIN status, ATM network, statement-reporting timing, written-statement consent, and other filing prerequisites.

For example, use this generic structure, replacing every bracketed field with facts actually available at runtime:

```text
Customer explicitly requests a human agent for [count] debit-card disputes across [count] cards. Suspected fraud/unauthorized activity is present.

[Card/account label A]: [lost/not possessed/still possessed]. Unauthorized transaction: [reported status]. [ATM or recurring issue, if assigned].
[Card/account label B]: [possession status]. Unauthorized transaction: [reported status]. [ATM or recurring issue, if assigned].

Recurring claim: [merchant] charge after cancellation on [card label]; customer [did/did not] contact merchant and [outcome]. Customer wants the past charge addressed [and does/does not want] a card-wide block of all recurring payments.

No dispute, card-protection, or recurring-block action completed before handoff. Verification status: [status]. Still needed: [only facts not already supplied].
```

This is a structure, not permission to invent fields. In particular, preserve the association between the card and each non-fraud claim rather than merely listing words in unrelated sentences.

### Lost-card and recurring-payment safeguards

A reported lost or stolen debit card is a security concern. After verification and if the customer requests continued self-service, follow the normal close/freeze procedure and check whether the customer has Rho-Bank credit cards; if so, offer cross-product replacement protection. Do not imply a credit-card replacement was offered or ordered unless that actually happened.

A charge that already occurred after cancellation is a past-charge dispute, not an automatic recurring-payment block. A recurring block affects **all** recurring payments on that card. Offer or apply it only after the customer affirmatively requests that broad future-payment protection and understands its scope. If the customer wants only a particular past merchant charge addressed or declines the broad block, do not invoke the recurring-block tool.

## Read-only preparation and dispute filing

After verification, or for read-only preparation where allowed:

1. Retrieve relevant accounts and select the linked **OPEN checking** account.
2. Retrieve debit cards for the account. Confirm card ID, account ID, cardholder user ID, and status.
3. Retrieve account transactions and select the reported transaction explicitly; transaction lists are reverse chronological and the first result is not necessarily the target.
4. Retrieve dispute history. Count unresolved disputes per account, not per customer: Entry 2, Mid 3, Premium 4, Elite 5.
5. For duplicate charges, dispute the earliest transaction in an established duplicate set.
6. For ATM disputes, determine whether the ATM is Rho-Bank or third party.

Do not file a dispute unless the customer is verified; the transaction is at least $1.00 and no more than 60 days old; the linked checking account is OPEN; card/account/user linkage and ownership match; and the account's open-dispute limit permits the filing.

For every filing, gather transaction ID, account ID, card ID, user ID, transaction and discovery dates, amount, transaction type, card-possession status, PIN-compromise status, merchant-contact status, police-report status for fraud over $500, written-statement consent, and all account/card eligibility facts.

Before proceeding with unauthorized activity, explain and record the applicable Regulation E timing: within 2 business days of the statement means maximum $50 liability; within 60 days means maximum $500; after 60 days may mean unlimited liability and non-recovery. Do not infer statement timing from transaction date.

## Classification, provisional credit, and card action

Use exactly one category per transaction:

- `unauthorized_transaction` only when unauthorized but fraud is not suspected;
- `card_present_fraud` for suspected in-store/physical-card fraud;
- `card_not_present_fraud` for suspected online/telephone fraud;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Establish physical versus online/telephone channel before choosing a suspected-fraud category. Do not guess it. Transaction type must be one of `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Required provisional credit is established only when timely reporting within 60 days of the statement, a qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN unrestricted account are all established. It is not required for recurring-cancellation, goods/services, ATM-deposit, or incorrect-amount claims; where a non-fraud merchant-contact requirement is unmet; where the PIN was voluntarily shared; or for card-not-present claims on accounts opened fewer than 30 days ago. Mark missing facts as undetermined, not false certainty.

Record per-dispute `card_action` as follows:

| Category | Recorded action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other listed categories | `keep_active` |

The recorded action is metadata. After all successful filings on a card, perform only the highest required actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. A lost/stolen/fraud-suspected closure bypasses the minimum card-age requirement only; all other applicable closure requirements remain in force.

## Handoff summary helper

`scripts/build_handoff_summary.py` creates a deterministic transfer recommendation and structured summary from facts already gathered. It does not parse customer prose, call tools, or transfer the customer. The executor must supply the facts it extracted from the runtime conversation.

Input is one JSON object on stdin:

- `human_requested` (boolean), `fraud_or_security_concern` (boolean), and `verification_status` (string);
- `cards` (array), each with `label` (string), optional `possession` (`lost_not_possessed`, `still_possessed`, or `unknown`), `unauthorized_reported` (boolean), optional `fraud_suspected` (boolean), optional `atm_issue` (string), and optional `recurring` object;
- a `recurring` object may contain `merchant`, `after_cancellation`, `merchant_contacted`, `merchant_outcome`, and `declines_cardwide_block`;
- `unresolved_items` (array of strings) and `actions_completed` (array of strings).

It emits JSON containing `reason`, `summary`, `errors`, and `non_execution_notice`. Run it with runtime-provided case JSON:

```sh
python3 scripts/build_handoff_summary.py < handoff_case.json
```

Before calling `transfer_to_human_agents`, check that all named cards and their issue assignments appear in the generated or manually prepared summary, that known merchant contact/outcome and recurring-block instruction are retained, and that only genuinely missing facts are listed as unresolved.
