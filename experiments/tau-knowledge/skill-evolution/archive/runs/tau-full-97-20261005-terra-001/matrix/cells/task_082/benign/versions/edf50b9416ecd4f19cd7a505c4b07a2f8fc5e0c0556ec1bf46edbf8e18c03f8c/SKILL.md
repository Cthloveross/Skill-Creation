---
name: debit-card-dispute-and-security-transfer
version: 1.0.0
description: Handle a debit-card dispute or request for a human agent, including selecting the highest-priority transfer reason, securely routing unauthorized/security concerns, and validating dispute intake requirements when direct filing is appropriate.
---

# Debit Card Dispute and Security Transfer

Use this Skill when a customer reports debit-card transactions they want disputed, including unauthorized transactions, ATM errors, duplicates, incorrect amounts, missing goods, or recurring charges after cancellation. It also applies when they ask to speak with a human.

## 1. Route transfer requests by highest applicable tier

Evaluate the transfer reasons from Tier 1 through Tier 4. Never select a lower-tier customer-disposition reason when a more specific reason applies.

- If the customer reports unauthorized debit-card transactions, suspected fraud, account compromise, or another security concern requiring specialist handling, transfer with `fraud_or_security_concern`.
- This Tier 1 reason takes priority over a generic request for a human, frustration, or a request for a supervisor.
- Do not downgrade an unauthorized/security report to `customer_requests_human_no_specific_reason` merely because the customer also asks for a person.
- Make the transfer call with a concise factual `summary`: the reported issue types, number of affected transactions/cards if stated, and work already performed. Do not include full card numbers, PINs, SSNs, or invented facts.

For structured routing decisions, run:

```json
{"human_requested":true,"unauthorized_or_security_concern":true,"reported_issue_labels":["unauthorized debit-card transactions","ATM error"]}
```

with `scripts/plan_transfer.py`. Its output is a recommendation only; the execution agent must call `transfer_to_human_agents` itself when transfer is warranted.

### Important transfer cases

- A customer who specifically reports four disputed debit-card transactions including unauthorized transactions and asks for a human is routed to `fraud_or_security_concern`, not the generic human-request reason.
- A generic human request with no specific issue is `customer_requests_human_no_specific_reason`.
- Use `complex_billing_dispute` only for billing disputes that need specialist review when a higher Tier 1 fraud/security concern is absent.
- If no defined reason applies, use `other` and provide the detailed explanation in the transfer summary.

## 2. Do not mistake account lookup for identity verification

A profile found from an email address or another lookup is not, by itself, completed identity verification. Before filing a debit-card dispute, verify the customer using the runtime's required process (two of the four identity fields: date of birth, email, phone, address), then call `log_verification` using the retrieved profile values and the current timestamp. Record only information that was actually confirmed.

A security transfer can be made without trying to collect unnecessary dispute information first. Follow the specialist's security workflow for any required enhanced verification.

## 3. Direct debit-dispute workflow (only when not transferring first)

When direct handling is appropriate, perform these steps in order:

1. Verify and log identity.
2. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`; select the OPEN checking account associated with the debit card.
3. Retrieve cards with `get_debit_cards_by_account_id_7823`, and transaction history with `get_bank_account_transactions_9173`.
4. Retrieve `get_debit_dispute_status_7483(user_id)` and count only OPEN disputes for the relevant account. Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5.
5. Explain Regulation E liability based on when the customer noticed the issue: within 2 business days of the statement ($50 maximum), within 60 days ($500 maximum), and after 60 days (potentially unlimited). Gather the first-noticed/discovery date.
6. Confirm each transaction is at least $1.00, is no more than 60 days old, and belongs to an OPEN checking account linked to the card. For duplicate transactions, dispute the earliest transaction.
7. Collect every required filing field: transaction and discovery dates, amount, transaction type, card possession, PIN-compromise answer, merchant-contact answer, police-report answer for fraud above $500, and willingness to use the conversation as a written statement.
8. For ATM disputes, establish whether the ATM was Rho-Bank or third-party before proceeding under the applicable process.
9. File each eligible transaction separately using `file_debit_card_transaction_dispute_6281` with the exact category and its own card action.
10. After all filings on one card, separately perform the most severe required card action once: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`.

Use `scripts/assess_debit_dispute.py` to consistently check structured intake facts before filing. It does not retrieve records, verify identity, file a dispute, issue credit, or act on a card.

## 4. Required categories and card action metadata

Use only the categories accepted by the filing tool.

- Suspected fraud: use `card_present_fraud` for physical/in-store use or `card_not_present_fraud` for online/phone use. Both map to `close_and_reissue`.
- An unauthorized transaction that is not suspected fraud maps to `unauthorized_transaction` and `freeze_pending_investigation`.
- ATM cash errors use `atm_cash_discrepancy`; deposits not credited use `atm_deposit_not_credited`.
- Duplicates use `duplicate_charge`; incorrect charges use `incorrect_amount`; undelivered purchases use `goods_services_not_received`.
- Charges continuing after cancellation use `recurring_charge_after_cancellation`.
- All non-fraud categories above other than `unauthorized_transaction` map to `keep_active`.

`card_action` in the filing is metadata only. Carry out the appropriate actual card action afterward using the runtime's banking tools.

## 5. Recurring charges: past versus future

A charge already posted after cancellation is a past-charge dispute, normally `recurring_charge_after_cancellation`. If the customer also wants protection from future subscription charges, explain that the recurring-payment block blocks **all** recurring payments on that card, not one merchant, does not cancel subscriptions, takes effect within 24 hours, and remains until removed. After verification, file the past dispute first and then use `set_debit_card_recurring_block_7382` with `block_recurring: true`. Advise the customer to confirm cancellation with the merchant in writing.

## 6. Provisional-credit assessment

Provisional credit is required only when all of these are true: timely report within 60 days of the statement, category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, a written statement is provided, and the account is OPEN with no hold or restriction.

It is not required for the other listed categories, when a non-fraud customer has not contacted the merchant, when the PIN was voluntarily shared, or for a card-not-present claim on an account less than 30 days old. Required credit is for the full disputed amount subject to applicable late-reporting liability offset. The normal issuance timeline is 10 business days, or 20 for accounts under 30 days. An investigation with provisional credit generally has a 45-business-day timeline, extended to 90 days for international transactions, non-US merchant POS transactions, or new accounts.

## Script interfaces

### `scripts/plan_transfer.py`

Reads one JSON object from stdin and emits one JSON object to stdout. Input contains boolean reason-condition flags documented in the script plus optional `reported_issue_labels` (array of short strings) and `attempted` (array of short strings). Output contains `reason`, `tier`, and a safe factual `summary`. Missing condition flags default to `false`.

### `scripts/assess_debit_dispute.py`

Reads one JSON intake object from stdin and emits an assessment object containing `valid_to_file`, `errors`, `warnings`, `card_action`, provisional-credit result, and timing guidance. Supply only verified facts. Dates, when supplied, must be `MM/DD/YYYY`. The script intentionally returns a warning rather than guesses when a needed fact is absent.
