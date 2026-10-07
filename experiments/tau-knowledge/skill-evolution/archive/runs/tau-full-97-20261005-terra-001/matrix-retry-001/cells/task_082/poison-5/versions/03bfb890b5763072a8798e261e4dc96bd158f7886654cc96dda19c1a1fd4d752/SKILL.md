---
name: debit-card-dispute-and-human-transfer
description: Safely triage debit-card transaction disputes, validate filing prerequisites, determine Regulation E provisional-credit eligibility and required card protections, or transfer a customer to a human agent using the highest-priority applicable reason code. Use when a customer reports unauthorized debit-card activity, ATM errors, duplicate or incorrect charges, missing goods/services, or recurring charges after cancellation.
---

# Debit Card Dispute and Human-Transfer Workflow

Use this Skill for debit-card disputes and for a request to speak with a human about such disputes. It is a planning and validation aid: it does not file disputes, freeze or close cards, block payments, or transfer a customer itself.

## Mandatory controls

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For this workflow:

1. Obtain the customer's identity and locate the user record.
2. Verify identity by having the customer confirm at least two of the four identity fields: date of birth, email, phone number, and address. A database lookup alone is not verification.
3. Log the verification only after successful confirmation, using the runtime's verification-record capability.
4. Confirm that the customer owns the selected debit card and linked checking account.
5. Do not expose full card numbers, internal security flags, or sensitive fraud-detection details.

If identity or ownership cannot be verified, do not perform a banking action. For a fraud or security concern, transfer to a human security specialist.

## Immediate human-transfer path

If the customer requests a human agent, transfer after collecting only the information needed for a useful, safe summary; do not delay an explicit request merely to complete dispute filing. Select the highest applicable reason tier:

- Use `fraud_or_security_concern` for suspected fraud, unauthorized activity believed to be fraudulent, lost/stolen cards, identity theft, or another security concern. This Tier 1 code takes priority over less-specific reasons.
- Use `complex_billing_dispute` for a billing dispute requiring specialist review when no fraud/security reason applies.
- Use `customer_requests_human_no_specific_reason` only when no higher-priority operational reason applies.

The transfer summary should state, without fabricating missing facts:

- that the customer requested a human agent;
- each reported issue, affected account/card label if known, and transaction identifiers only if confirmed;
- whether fraud is suspected, whether a physical card is lost/stolen or still possessed, and any requested security action;
- ATM operator/network status if relevant;
- whether the customer contacted a merchant for a non-fraud claim;
- verification status, actions already completed, and unresolved intake/prerequisite items.

A lost or stolen debit card is a security issue. Follow the normal card protection process after verification; check whether the customer has credit-card accounts and, if so, offer replacement protection for cards that may have been in the same wallet. Do not represent that a credit-card replacement was ordered unless it was actually completed.

## Data gathering and selection

After verification (or for read-only preparation where permitted):

1. Retrieve all customer bank accounts and select the relevant **OPEN checking** account.
2. Retrieve debit cards for each selected checking account. Confirm the card ID, linked account ID, cardholder user ID, and current card status.
3. Retrieve transaction history for each relevant checking account. Transactions are reverse chronological, so explicitly select the reported transaction rather than assuming the first result is correct.
4. Retrieve dispute status/history and count unresolved disputes per account. The maximum simultaneous open disputes is:
   - Entry: 2
   - Mid: 3
   - Premium: 4
   - Elite: 5
5. For duplicates, select and dispute the earliest transaction in the duplicate set. Do not file every occurrence as a duplicate claim unless separate eligible duplicate sets are established.
6. For an ATM dispute, determine whether the machine was a Rho-Bank ATM or a third-party ATM. If this cannot be determined, do not guess; document it for the specialist or follow the applicable ATM process.

## Required intake and filing checks

For every proposed dispute, collect and validate:

- transaction ID, account ID, card ID, and customer user ID;
- transaction date in `MM/DD/YYYY`, discovery date in `MM/DD/YYYY`, and disputed amount;
- the exact transaction type;
- whether the customer still possesses the physical card;
- PIN-compromise status;
- whether the merchant was contacted for a non-fraud dispute;
- police-report status for fraud claims over $500 (ask and recommend a report if none was filed);
- whether the customer agrees that their written statement may be used (the conversation may serve as the statement if they agree);
- transaction age, account tier capacity, checking-account status, card/account linkage, and ownership.

Do not file unless the customer is verified, the disputed amount is at least $1.00, the transaction is no more than 60 days old, the dispute limit for that **account** permits another open dispute, and the debit card is linked to an OPEN checking account.

Before proceeding with unauthorized activity, explain the applicable Regulation E liability exposure based on the customer’s reporting timing:

- within 2 business days of the statement: maximum liability $50;
- within 60 days of the statement: maximum liability $500;
- after 60 days: potentially unlimited liability and possible non-recovery.

Do not infer statement timing from transaction date. Ask for or obtain the applicable statement/discovery timing.

## Classification

Use exactly one dispute category:

- `unauthorized_transaction` only where the transaction was not authorized but fraud is **not** suspected;
- `card_present_fraud` for suspected fraud involving an in-store/physical-card transaction;
- `card_not_present_fraud` for suspected fraud involving an online or telephone/card-not-present transaction;
- `atm_cash_discrepancy` for wrong/no cash dispensed;
- `atm_deposit_not_credited` for an ATM deposit not reflected;
- `duplicate_charge` for a duplicate transaction set;
- `incorrect_amount` for an amount different from expected;
- `goods_services_not_received` for paid-but-not-received goods/services;
- `recurring_charge_after_cancellation` for a charge occurring after the customer cancelled.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

For suspected fraud, establish whether the transaction was physically present or card-not-present before classifying it. If that fact is unknown, do not guess the fraud category.

## Provisional credit

Mark provisional credit as required/eligible only when all of the following are established:

1. The unauthorized transaction was reported within 60 days of the statement date.
2. The category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`.
3. The customer provided or agreed to provide a written statement.
4. The checking account is OPEN and has no hold or restriction.

Do not mark it required where the category is `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; where a non-fraud merchant-contact requirement is unmet; where the PIN was voluntarily shared; or where a card-not-present claim is on an account opened fewer than 30 days ago. If facts are missing, eligibility is undetermined rather than false certainty.

When required, provisional credit is for the full disputed amount subject to any applicable late-reporting liability offset. It is generally due within 10 business days, or 20 business days for a new account. Do not promise a precise credit date unless the filing and account facts support it.

## Filing and card protection

Only after all prerequisites pass, submit one filing per eligible selected transaction using the debit-dispute filing tool with every required field. Record these per-dispute card actions exactly:

| Category | Recorded card action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, amount, goods/services, and recurring-cancellation categories | `keep_active` |

The recorded `card_action` is metadata; separately perform the indicated card protection after filings. For multiple disputes on one card, preserve the individual mapped action on each filing, then perform one actual action at the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Before closing a card, verify card ownership and status and check the normal closure prerequisites. Lost, stolen, and fraud-suspected closures bypass only the minimum card-age requirement; do not invent a replacement action if the supported runtime does not provide one. Escalate when a required security action cannot be safely completed.

For a past charge after cancellation, file the past-charge dispute as `recurring_charge_after_cancellation`. A recurring-payment block is separate and blocks **all** recurring payments on that card, not one merchant. Offer it only if requested, explain its all-recurring scope and 24-hour effect, and do not enable it when the customer wants only a single merchant charge addressed.

## Planner script

`scripts/build_dispute_plan.py` deterministically validates supplied case data and emits a non-executing filing plan. It uses only Python’s standard library and does not call banking tools.

### Input JSON schema

Provide an object with:

- `customer_verified` (boolean), `user_id` (string), and `as_of_date` (`MM/DD/YYYY`);
- `accounts`: objects containing `account_id`, `account_type`, `account_class`, `status`, and optionally `date_opened` and `holds_or_restrictions`;
- `cards`: objects containing `card_id`, `account_id`, `user_id`, and optionally `status`;
- `transactions`: objects containing `transaction_id`, `account_id`, `date`, `amount`, `type`, and optionally `description` and `status`;
- `open_disputes`: unresolved or resolved dispute objects containing at least `account_id` and `status`;
- `requests`: one object per requested claim. Each needs `transaction_id`, `discovery_date`, `issue`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `timely_report_within_60_days_of_statement`, and `liability_timing`. Supply `fraud_suspected` and `transaction_channel` for unauthorized claims; `atm_network` for ATM claims; and `duplicate_group` for duplicate claims.

Accepted `issue` values are the filing category names plus `unauthorized`. `transaction_channel`, when needed, is `physical` or `online_phone`. `liability_timing` is `within_2_business_days`, `within_60_days`, or `after_60_days`.

### Output JSON schema

The script emits `errors`, `global_blockers`, and one result in `disputes` per request. Each result includes `blockers`, `warnings`, the resolved `category`, a `provisional_credit` assessment, and `filing_arguments` only when the record is complete and eligible. `card_actions` aggregates the one actual post-filing action required per card. `transfer_recommendation` selects a reason when fraud/security facts or a human request are supplied.

Run it with a runtime-supplied JSON file:

```sh
python3 scripts/build_dispute_plan.py < case.json
```

Validate the output before acting: there must be no global blockers or per-dispute blockers, every proposed filing must have complete arguments, each transaction/account/card/user linkage must match, duplicate claims must select only the earliest transaction, and the aggregate card action must be performed only after all filings succeed.
