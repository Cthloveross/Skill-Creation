---
name: debit-card-security-dispute-handoff
description: Use when a customer asks for a human while reporting unauthorized debit-card activity, a lost or stolen card, suspected card compromise, ATM error, or other debit-card dispute. Select the highest-priority transfer reason and produce a factual security/dispute handoff without making unsupported bank actions.
---

# Debit-card security and dispute handoff

## Primary decision: immediate security transfer

When the customer requests a human and reports **any** unauthorized transaction, lost/stolen debit card, suspected card-number/PIN compromise, or comparable security concern, immediately use `transfer_to_human_agents`. Set `reason` to exactly `fraud_or_security_concern`.

This is the Tier 1 operational reason and takes precedence over `complex_billing_dispute` and a generic request for a person. A post-cancellation subscription or ATM discrepancy does not reduce the priority of a concurrent fraud/security report.

Do not wait for identity verification, account/card/user IDs, transaction lookup, discovery date, PIN answers, merchant-contact answers, or written-statement consent before this transfer. Do not file disputes, freeze a card, close/reissue a card, set a recurring-payment block, or claim provisional credit before the handoff unless the live task explicitly separately authorizes and provides the required tools and prerequisites. A human transfer itself needs no identity verification.

Call the transfer once, with a concise factual `summary`. Include only facts actually supplied by the customer or by live tool results:

- their request for a human and the security trigger (unauthorized activity, lost/stolen card, or suspected compromise);
- for each known transaction, date, amount, merchant/ATM, card or account descriptor, and reported issue;
- for an ATM cash issue: requested cash, actual cash received, ATM identity/ownership if known, and relevant receipt detail;
- for a recurring charge: claimed cancellation timing and merchant-contact status if known;
- card-possession status and loss timing, if known; and
- material intake facts not obtained and the statement that no dispute/card/recurring-block action was performed, when true.

Never invent IDs, transaction records, a fraud channel, discovery/statement timing, verification, consent, police-report status, PIN compromise, merchant contact, or a promised outcome. Do not disclose internal fraud codes. After a successful transfer, send a short customer-facing confirmation that the security/dispute concern has been routed to the appropriate team; do not promise reimbursement, provisional credit, or replacement.

## Transfer-reason selection when no security trigger exists

Use the highest applicable reason:

1. `complex_billing_dispute` for specialist billing/dispute review (such as recurring charges, statement errors, or fee reversals) where no fraud/security concern exists.
2. `customer_requests_human_no_specific_reason` only when the request is merely a preference for a human and no more specific reason applies.

If a customer says a card marked stolen was not reported stolen by them, treat it as a major security concern and transfer with `fraud_or_security_concern`; do not try to reactivate it.

## Only if the live task does not require a handoff and provides filing capability

Before a debit-card dispute filing, verify and log identity; identify the transaction from account history; confirm amount is at least $1, transaction is within 60 days, linked checking account is open, account dispute limit is available, and ATM ownership is known for ATM claims. Collect transaction and discovery dates, amount, transaction type, card possession, PIN-compromise response, written-statement consent, merchant contact for non-fraud disputes, and police-report status for suspected fraud above $500. Explain Regulation E reporting-time liability limits before proceeding when statement timing is available.

Use these categories: suspected physical-card fraud `card_present_fraud`; suspected online/phone fraud `card_not_present_fraud`; non-fraud unauthorized use `unauthorized_transaction`; ATM wrong/no cash `atm_cash_discrepancy`; ATM deposit missing `atm_deposit_not_credited`; duplicate `duplicate_charge`; wrong amount `incorrect_amount`; goods absent `goods_services_not_received`; and a charge after cancellation `recurring_charge_after_cancellation`.

Record `close_and_reissue` for either fraud category, `freeze_pending_investigation` for `unauthorized_transaction`, and `keep_active` for all other categories. For several filings on a card, preserve each filing's mapped value, then perform only the most severe actual action afterward: close/reissue, then freeze, then keep active. For ATM cash discrepancies above $200, give the affidavit notice. For a Rho-Bank ATM, review the transaction/journal record; a formal dispute remains possible if it does not validate the claim. A future recurring-payment block is separate from a past-charge dispute and blocks all recurring payments on the card.

## Optional deterministic intake helper

`scripts/dispute_plan.py` only prepares intake recommendations; it calls no bank tool and performs no action. Run it with JSON on stdin:

```sh
python3 scripts/dispute_plan.py <<'JSON'
{"issues":[{"kind":"atm_cash","amount":150,"transaction_date":"01/10/2025","discovery_date":"01/10/2025","card_in_possession":true,"fraud_suspected":false,"channel":"physical","merchant_contacted":null,"written_statement_provided":null,"pin_compromised":"no"}]}
JSON
```

Input is `{"issues":[... ]}`. Each issue may have `kind` (`unauthorized`, `atm_cash`, `atm_deposit`, `duplicate`, `incorrect_amount`, `goods_not_received`, or `recurring_after_cancellation`), `channel` (`physical`, `online_phone`, or `unknown`), `fraud_suspected`, `amount`, `card_in_possession`, `transaction_date`, `discovery_date`, `merchant_contacted`, `written_statement_provided`, `pin_compromised`, plus ATM amounts/owner and `police_report_filed` where applicable. It emits `{"plans":[...],"has_security_concern":boolean}`. Validate each plan has a recognized category/action and inspect its explicit `missing_fields`; recommendations never replace live prerequisites or a required security handoff.
