---
name: debit-card-dispute-security-handoff
description: Handle debit-card dispute reports by identifying fraud/security escalation, collecting only appropriate dispute intake facts, determining documented dispute categories and card-action metadata, and preparing a complete human-agent handoff when escalation is required.
---

# Debit-card dispute and security handoff

Use this Skill for customers reporting debit-card transactions they did not authorize, lost/stolen cards, ATM cash/deposit errors, duplicate or incorrect charges, goods not received, or recurring charges after cancellation. It is particularly applicable when a user requests a human agent while reporting unauthorized activity or a security concern.

## Safety and escalation priority

1. Review all stated facts and select the highest applicable transfer reason.
2. Transfer with `fraud_or_security_concern` whenever unauthorized transactions, a lost/stolen card, suspected card-number compromise, or another security issue requires specialist handling. This Tier 1 reason takes priority over a general request for a human.
3. Use `complex_billing_dispute` only when that is the highest applicable issue and no fraud/security concern is present. Do not downgrade a fraud-related matter to a generic customer-request reason.
4. Do not disclose internal fraud decline codes or make assurances that a charge will be refunded.
5. If the customer says they never reported a card as stolen after it was marked stolen, transfer to security rather than attempting to resolve it.

A transfer does not require a user ID or account ID. Do not delay a security handoff merely to obtain identifiers that are unavailable.

## Runtime procedure

### 1. Establish the handoff decision

For a request involving both routine disputes and any suspected fraud/security issue, make one human transfer using `transfer_to_human_agents` with:

- `reason`: `fraud_or_security_concern`
- `summary`: a concise but complete factual handoff summary.

Include, when known:

- Every reported transaction: date, amount, merchant or ATM, associated card/account descriptor, and whether it was unauthorized, an ATM discrepancy, or post-cancellation recurring charge.
- The customer's card-possession status and any loss/stolen date or reported compromise.
- For an ATM discrepancy, requested amount, cash actually received (or missing deposit), ATM ownership/location, and receipt/journal detail.
- For a recurring charge, that the customer says cancellation occurred and whether merchant contact is known.
- Facts still missing: identity verification, actual account/card/user IDs, statement/discovery timing, PIN-compromise answer, merchant-contact answer, written-statement consent, account status/tier/open-dispute count, and transaction lookup confirmation.
- Actions not performed before handoff. State that no dispute, freeze, closure/reissue, or recurring-payment block was performed if none was performed.

Use only facts present in the conversation or tool results. Do not infer transaction IDs, identities, card IDs, whether a police report exists, or customer consent.

### 2. Give a brief customer-facing response

After a successful transfer, tell the customer that their security/dispute concern is being routed to the appropriate team. Avoid promising provisional credit, reimbursement, card replacement, or a specific outcome.

### 3. If no Tier 1 security escalation is present and the task instead permits filing

Before filing any debit-card dispute, ensure all documented prerequisites are met:

- customer identity is verified and verification is logged;
- a specific transaction is identified from account transaction history;
- disputed amount is at least $1.00 and the transaction is within 60 days;
- the linked checking account is open and the card is linked to it;
- the account has not reached its tier-specific open-dispute limit;
- ATM ownership is determined for ATM disputes.

Collect the transaction date, discovery date, amount, transaction type, card-possession answer, PIN-compromise answer, merchant-contact answer for non-fraud claims, written-statement consent, and police-report answer for suspected fraud above $500. Inform the customer of applicable Regulation E reporting-time liability limits, but do not calculate statement-based liability without the statement timing.

Map categories as follows:

- Unauthorized and fraud suspected: `card_present_fraud` for physical/in-store use or `card_not_present_fraud` for online/phone use.
- Unauthorized but fraud is not suspected: `unauthorized_transaction`.
- ATM cash wrong/not dispensed: `atm_cash_discrepancy`.
- ATM deposit missing: `atm_deposit_not_credited`.
- Duplicate: `duplicate_charge`.
- Wrong amount: `incorrect_amount`.
- Goods/services missing: `goods_services_not_received`.
- Charge after cancellation: `recurring_charge_after_cancellation`.

The card-action metadata is `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` for the other categories. For multiple filings on a card, retain each filing's own mapped metadata but perform only the single most severe actual action afterward: close/reissue, then freeze, then keep active.

For an ATM cash discrepancy over $200, notify the customer of the affidavit requirement. For third-party ATMs, note the chargeback path and longer investigation timeline. For Rho-Bank ATMs, review the relevant transaction/journal information; a formal dispute can still be filed if the journal does not validate the claim.

For a past recurring charge, file the past-charge dispute first. A recurring-payment block, if separately requested, blocks all recurring payments on the card rather than one merchant; explain this and obtain the required confirmation before using it.

## Optional deterministic helper

`scripts/dispute_plan.py` accepts structured, already-known intake facts and returns category/action recommendations plus missing fields. It never calls bank tools and never performs a bank action.

Input JSON schema:

```json
{
  "issues": [
    {
      "kind": "unauthorized|atm_cash|atm_deposit|duplicate|incorrect_amount|goods_not_received|recurring_after_cancellation",
      "channel": "physical|online_phone|unknown",
      "fraud_suspected": true,
      "amount": 0.0,
      "card_in_possession": true,
      "transaction_date": "MM/DD/YYYY",
      "discovery_date": "MM/DD/YYYY",
      "merchant_contacted": null,
      "written_statement_provided": null,
      "pin_compromised": "yes_shared|yes_observed|no|unknown"
    }
  ]
}
```

Example runnable call:

```sh
python3 scripts/dispute_plan.py <<'JSON'
{"issues":[{"kind":"atm_cash","amount":150,"transaction_date":"01/10/2025","discovery_date":"01/10/2025","card_in_possession":true,"fraud_suspected":false,"channel":"physical","merchant_contacted":null,"written_statement_provided":null,"pin_compromised":"no"}]}
JSON
```

Validate that each returned item has a recognized `category`, mapped `card_action`, and an explicit `missing_fields` list. Treat recommendations as intake support only: confirm prerequisites and use declared banking tools during live execution.

## Immediate-transfer checklist

For a customer who explicitly asks for a human and reports unauthorized debit-card activity or a lost/stolen card, the live execution is complete when these three steps have occurred in order:

1. Call `transfer_to_human_agents` once with `reason` set to `fraud_or_security_concern` and a factual handoff summary.
2. Wait for the transfer result; do not retry the call if it reports an unknown outcome.
3. If successful, give only a short routing confirmation and allow the handoff to proceed.

Do not replace this path with a generic customer-preference transfer. Do not delay it for identity verification or routine filing prerequisites; a brief factual inventory for a multi-transaction handoff is appropriate when the live conversation can continue. The receiving specialist completes verified intake and any card action.

## Multi-transaction handoff intake

When a customer asks a human to handle several debit-card disputes and the live conversation can continue, obtain a concise factual inventory for the receiving specialist before transferring. Ask only for each transaction’s date, amount, merchant or ATM, associated card, and card-possession status. For an ATM issue, ask requested versus received/deposited amount and ATM location or ownership. For a post-cancellation recurring charge, ask when it was cancelled and whether the merchant was contacted. For an unauthorized charge, ask whether it was authorized and whether credentials or PIN may be compromised.

After this inventory, transfer promptly under fraud_or_security_concern if any unauthorized activity, lost/stolen card, or suspected compromise was reported. Do not turn preliminary inventory into identity verification or dispute filing, and do not delay transfer for every filing prerequisite. Include unanswered intake facts in the handoff summary.
