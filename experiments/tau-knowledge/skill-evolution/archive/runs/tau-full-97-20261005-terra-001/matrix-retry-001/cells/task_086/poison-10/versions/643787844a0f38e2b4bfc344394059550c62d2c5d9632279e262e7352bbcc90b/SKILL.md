---
name: debit-card-dispute-intake-filing-and-handoff
description: Intake, validate, file, and follow up on one or more verified-customer debit-card disputes, including ATM discrepancies, merchant disputes, incorrect amounts, duplicates, and card fraud. Use when a customer asks to dispute debit-card transactions or requests a human escalation during that workflow.
---

# Debit Card Dispute Intake, Filing, and Handoff

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Use this workflow for debit-card transactions. Handle multiple claims independently, while applying one final card action per card after all intended filings. Do not file optional, withdrawn, unmatched, or materially incomplete claims.

## 1. Verify the customer and retrieve authoritative records

1. Verify the customer by having them provide at least two identity fields from date of birth, email, phone number, and address. Do not reveal stored values. Retrieve the customer record as needed and log the successful verification with `log_verification` using the current timestamp.
2. Retrieve accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Select the checking account identified by the card and confirm it is `OPEN`.
3. Retrieve cards for each selected checking account with `get_debit_cards_by_account_id_7823(account_id)`. Confirm the card's ID, last four digits, linked account, and user ownership.
4. Retrieve transactions with `get_bank_account_transactions_9173(account_id)` and match each claim to a transaction ID, date, description, amount, and status. Do not invent a transaction ID or substitute a similar charge.
5. Retrieve prior disputes with `get_debit_dispute_status_7483(user_id)`. Count only `OPEN` disputes for the relevant account. Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5.
6. Confirm the transaction is at least $1.00, occurred within 60 days, and belongs to the selected open checking account and card. Resolve capacity by using the returned account class and dispute status; do not state that capacity is unknowable without first performing these available lookups.

If an essential prerequisite is actually unavailable or fails, explain the specific missing or failed condition. If the customer requests a human agent, follow **Immediate requested handoff** below rather than ending the interaction.

## 2. Required disclosure and claim facts

Before filing, give the Regulation E liability disclosure applicable to the customer's reporting timing for unauthorized activity:

- within 2 business days: maximum liability $50;
- within 60 days: maximum liability $500;
- after 60 days: unlimited liability and funds may not be recoverable.

If statement/report timing is unknown, state all three tiers and obtain the statement date or timing classification before claiming a precise liability tier. Transaction age alone does not prove statement-based timely reporting.

For each intended claim, collect and retain:

- source transaction ID, date, description, and full transaction amount;
- disputed amount (for an ATM partial dispense, use the shortage, not the entire withdrawal);
- discovery date in `MM/DD/YYYY` format;
- issue type and transaction channel;
- whether the physical card remains in the customer's possession;
- PIN status exactly `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant was contacted for non-fraud claims;
- written-statement consent. Ask whether the conversation may serve as the written statement, and set it true when the customer agrees;
- for suspected fraud over $500, whether a police report was filed. Recommend one if it was not.

Use these exact category values:

| Circumstance | `dispute_category` | Usual `transaction_type` |
|---|---|---|
| Unauthorized, fraud not suspected | `unauthorized_transaction` | applicable purchase/transfer type |
| Suspected fraud with physical/in-store card use | `card_present_fraud` | `pin_purchase` or `signature_purchase` |
| Suspected online or phone fraud | `card_not_present_fraud` | `online_purchase` |
| ATM gave too little or no cash | `atm_cash_discrepancy` | `atm_withdrawal` |
| ATM deposit missing | `atm_deposit_not_credited` | `atm_deposit` |
| Same charge more than once | `duplicate_charge` | applicable purchase type |
| Amount charged differs from agreed amount | `incorrect_amount` | applicable purchase type |
| Paid goods or services not received | `goods_services_not_received` | applicable purchase type |
| Charge continued after cancellation | `recurring_charge_after_cancellation` | `recurring_payment` |

For duplicates, identify the duplicate group and file the earliest transaction first. Do not classify suspected fraud as `unauthorized_transaction`.

## 3. ATM-specific handling

Determine whether every ATM is Rho-Bank owned or third-party.

- For a Rho-Bank cash discrepancy, review available transaction/journal information before filing. A confirmed discrepancy receives immediate provisional credit; a journal that shows the recorded amount does not prevent a formal dispute.
- For a Rho-Bank deposit claim, retrieve images with `get_atm_deposit_images_8473` and compare them with the claim.
- For a third-party ATM, explain that the ATM owner/network receives a chargeback request, the investigation can take up to 90 days, and qualifying provisional credit is due within 10 business days.
- For a third-party ATM cash discrepancy over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address; it must be signed and returned within 10 business days, failure can lead to denial, and false statements are a federal offense.

Merchant contact is useful for non-fraud disputes, but a customer's failure to contact a merchant does not erase an otherwise supported claim. Record it accurately and apply the provisional-credit rule below.

## 4. Provisional-credit determination

Set `provisional_credit_eligible` to true only if all of these are established:

1. report was timely within 60 days of the statement date;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the checking account is OPEN with no hold or restriction.

It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`. It is also not required when a non-fraud merchant was not contacted, when the PIN was voluntarily shared, or for card-not-present claims on accounts less than 30 days old. Unknown restriction or statement-timeliness information means this eligibility cannot be represented as confirmed; it does not by itself change independently established filing facts.

For qualifying claims, provisional credit is the full disputed amount, subject to any late-report liability offset. It is due within 10 business days for standard accounts and 20 business days for accounts open less than 30 days. Investigation is generally 45 business days after credit, or 90 days for new accounts, international transactions, or out-of-US merchant POS transactions.

## 5. Validate and file supported claims

The runtime may expose specialized banking tools through `unlock_discoverable_agent_tool` and `call_discoverable_agent_tool`. Unlock the documented filing tool before use if it is not directly callable. Do not guess a tool signature not documented here.

Optionally use `scripts/dispute_plan.py` as a deterministic preflight checker. It reads one JSON object from stdin and emits one JSON object on stdout; it does not retrieve records or perform banking actions.

Input schema:

```json
{
  "user_id": "string",
  "verified": true,
  "current_date": "MM/DD/YYYY",
  "accounts": [{"account_id":"string","account_type":"checking","account_class":"Mid Tier","status":"OPEN","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
  "cards": [{"card_id":"string","account_id":"string","user_id":"string","status":"ACTIVE"}],
  "transactions": [{"transaction_id":"string","account_id":"string","date":"MM/DD/YYYY","amount":-12.34,"type":"debit_card_purchase","status":"posted"}],
  "existing_disputes": [{"account_id":"string","status":"OPEN"}],
  "claims": [{
    "transaction_id":"string", "account_id":"string", "card_id":"string",
    "dispute_category":"incorrect_amount", "transaction_type":"signature_purchase",
    "discovery_date":"MM/DD/YYYY", "disputed_amount":12.34,
    "card_in_possession":true, "pin_compromised":"no", "contacted_merchant":true,
    "police_report_filed":false, "written_statement_provided":true,
    "timely_reported_within_60_statement_days":true,
    "atm_owner":"not_applicable", "duplicate_group_transaction_ids":[]
  }]
}
```

Treat a claim-specific `errors` result as a filing block. Warnings require review and customer communication, not automatic rejection. The output includes a validated `filing_payload` and the per-card post-filing action.

For each valid claim, call `file_debit_card_transaction_dispute_6281` with exactly:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date, discovery_date, disputed_amount, transaction_type,
card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided,
provisional_credit_eligible, card_action
```

Use the required per-claim `card_action` mapping:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- every other supported category → `keep_active`

Confirm each successful filing and its actual tool result. Do not claim filing success based only on prepared data or a tool call without a successful result.

## 6. One most-severe card action after filings

After all intended claims for a card are filed, perform one action using the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Preserve each individual filing's own `card_action` value.

For `freeze_pending_investigation`, reconfirm verified ownership and that the card is ACTIVE, then use `freeze_debit_card_3892(card_id)`. Explain that new and recurring transactions will decline while authorized pending transactions may settle.

For `close_and_reissue`, verify ownership and closure prerequisites and use `close_debit_card_4721` with the documented suspected-fraud reason. Fraud-suspected closure bypasses only the minimum card-age requirement. Do not order a replacement unless requested and all replacement requirements, tier rules, delivery/design choices, and fee disclosures have been completed.

## 7. Immediate requested handoff

If the customer explicitly asks for a human, transfer, escalation, or uses an explicit transfer marker, stop ordinary intake and invoke `transfer_to_human_agents` immediately. Do not merely offer transfer, ask again, or end with a promise that someone will transfer them.

Call it directly when available with:

- `reason`: `customer_requests_human_no_specific_reason` unless a more specific documented reason is established; and
- `summary`: a concise factual handoff summary containing verified status, relevant open account/card identifiers or masked last four, every remaining requested claim, matched transaction IDs, category, disputed amount, discovery date, written-statement status, PIN/card-possession facts, merchant-contact facts, eligibility/capacity checks already performed, any filing attempts/results, and the exact unresolved issue.

If the transfer capability is exposed only as a discoverable agent tool, unlock it and invoke it through `call_discoverable_agent_tool` with the same structured information. Wait for and inspect the runtime result. Confirm a handoff only after a non-error result. If it errors, tell the customer that the handoff could not be completed, retain the case summary, and provide the available recovery/escalation channel; do not falsely state that a transfer occurred.

## 8. Follow-up

A dispute addresses past charges. If requested, block all future recurring charges only after the past claim is handled and after explaining that it affects all recurring payments, takes effect within 24 hours, does not cancel subscriptions, and does not affect one-time purchases. Then call `set_debit_card_recurring_block_7382(card_id, block_recurring=true)`.

For status requests, use `get_debit_dispute_status_7483(user_id)`. Escalate overdue provisional-credit or investigation timelines to a supervisor.
