---
name: debit-card-dispute-intake
version: 1.0.0
description: Safely conduct one-at-a-time intake, eligibility review, filing, and follow-up card handling for debit-card transaction disputes, including fraud, ATM, duplicate, merchant, and amount-error claims.
---

# Debit Card Dispute Intake and Filing

Use this Skill when a verified customer wants to report or file a debit-card transaction dispute. It supports multiple claims across cards, but each transaction must be reviewed and filed independently. Do not use it for credit-card disputes.

## Safety and control requirements

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, identity verification means confirming two of the four identity fields (date of birth, email, phone, address) against the customer record and logging the successful verification with `log_verification`. Do not treat knowing a name, email address, card last four, or account nickname alone as verification.

Do not file a dispute, freeze a card, or close a card until verification and the relevant prerequisites below are complete. Scripts in this package only assess supplied data and recommend actions; they never perform banking actions.

## Conversation method

1. Acknowledge the request and say that you will handle one issue at a time.
2. Locate the customer only from customer-provided identifying information, then complete the two-field verification and log it.
3. Explain Regulation E liability before proceeding with an unauthorized activity report:
   - reported within 2 business days of the statement: maximum liability $50;
   - within 60 days of the statement: maximum liability $500;
   - after 60 days: potentially unlimited liability and funds may not be recoverable.
   Ask for, or review when available, the relevant statement date; do not claim a liability tier when it cannot be determined.
4. Work through one claim at a time. Ask concise, single questions rather than a large questionnaire. Resolve the current claim before beginning another unless information must be shared.
5. For every claim, collect the transaction date, amount, merchant/ATM description, discovery date, card, what happened, card possession, and PIN-compromise response. For non-fraud claims, ask whether the customer tried resolving with the merchant. Ask whether the customer agrees to provide a written statement; the conversation can serve as that statement if they agree.
6. Identify the exact transaction from account history; never infer a transaction ID solely from a narrative. For duplicate charges, find the matching duplicates and dispute the earliest transaction first.

## Required lookups and prerequisite checks

Unlock and use the documented banking tools as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)` to find the account, its class/tier, status, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` to match the card to the customer, account, last four digits, and current card status.
- `get_bank_account_transactions_9173(account_id)` to identify the transaction, its date, amount, description, and status.
- `get_debit_dispute_status_7483(user_id)` to count only `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes for the same account.

Before filing, confirm all of the following:

- the customer is verified and owns the card and linked account;
- the linked account is a checking account and is `OPEN`;
- transaction amount is at least $1.00;
- transaction occurred no more than 60 days ago;
- the account has fewer than its permitted open disputes: Entry 2, Mid 3, Premium 4, Elite 5;
- the selected card is linked to that open checking account; and
- all required dispute facts are known.

If a requirement fails or cannot be established, explain the blocker and do not file. A pending transaction should be identified clearly; do not silently substitute a different transaction.

## Categorization and filing data

Choose exactly one category:

- `unauthorized_transaction`: not customer-authorized, but fraud is not suspected (for example, a family member used the card without permission).
- `card_present_fraud`: suspected fraud with a physical/in-store card-present transaction.
- `card_not_present_fraud`: suspected fraud for online or phone/card-not-present use.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`, according to the facts.

Use the matching transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Obtain the required `pin_compromised` value exactly as one of `yes_shared`, `yes_observed`, `no`, or `unknown`. For suspected fraud over $500, ask whether a police report was filed; if not, recommend filing one, while recording the truthful boolean.

Set the per-dispute metadata action as follows:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, amount, goods/services, and recurring categories | `keep_active` |

After all disputes for the same card have been filed, perform at most one actual card action at the greatest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Retain each dispute's own mapped `card_action` in its filing.

Use `file_debit_card_transaction_dispute_6281` only with this complete argument set:

```json
{
  "transaction_id": "string",
  "account_id": "string",
  "card_id": "string",
  "user_id": "string",
  "dispute_category": "string",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "string",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

Use values obtained in the live case only. Do not invent a date, transaction ID, card ID, customer confirmation, or merchant-contact response.

## Provisional credit

Mark provisional credit eligible only if all applicable facts support it: timely reporting within 60 days of the statement date, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an open checking account without holds or restrictions. It is not required for goods/services not received, recurring charges after cancellation, ATM deposits not credited, or incorrect amount. It is also not required when merchant contact is missing for a non-fraud claim, where PIN was voluntarily shared, or for a card-not-present claim on an account less than 30 days old.

For a qualifying claim, provisional credit is for the full disputed amount subject to any applicable late-reporting liability offset. Standard accounts require credit within 10 business days; accounts open less than 30 days require it within 20 business days. Do not calculate a liability offset without the statement/discovery facts.

## ATM-specific handling

Ask whether the ATM was Rho-Bank branded or third party.

- For a Rho-Bank ATM cash discrepancy, review account activity/journal information and compare it with the claim. If confirmed, provisional credit is immediate; if the journal is consistent with the debit, explain that the claim could not be validated but the customer may still file.
- For a Rho-Bank ATM deposit issue, retrieve and compare deposit images using `get_atm_deposit_images_8473` when available. Physical verification can take up to 45 days.
- For a third-party ATM, tell the customer a chargeback request to the owner/network is needed, the investigation can take up to 90 days, and qualifying provisional credit remains due within 10 business days.
- For every ATM cash discrepancy exceeding $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address; it must be signed and returned within 10 business days, failure may lead to denial, and a false affidavit is a federal offense. Record any documentation follow-up according to the tool result.

## Actual card action after filing

For `freeze_pending_investigation`, verify the card belongs to the customer and is `ACTIVE`, explain that new and recurring transactions will decline while pending transactions may still settle, then use `freeze_debit_card_3892(card_id)`.

For `close_and_reissue`, comply with card-closure controls before calling `close_debit_card_4721(card_id, reason)`: confirm ownership and eligible status, identify pending transactions and refunds, and use the truthful closure reason. Fraud-suspected closure bypasses only the 14-day minimum card-age condition; it does not remove other stated checks. Do not claim a replacement was ordered unless the runtime supplies and successfully completes an appropriate replacement workflow.

For `keep_active`, no card status action is required.

## Quality check helper

Run the helper after live facts and lookups are assembled and before filing:

```sh
python3 scripts/assess_dispute.py <<'JSON'
{"now":"MM/DD/YYYY","identity_verified":true,"account":{"account_type":"checking","status":"OPEN","account_class":"Entry","has_holds_or_restrictions":false,"date_opened":"MM/DD/YYYY"},"card":{"linked":true,"owned_by_customer":true,"status":"ACTIVE"},"transaction":{"transaction_id":"...","date":"MM/DD/YYYY","amount":25.0,"status":"posted"},"open_dispute_count":0,"claim":{"category":"duplicate_charge","transaction_type":"signature_purchase","discovery_date":"MM/DD/YYYY","reported_within_60_days_of_statement":true,"card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"fraud_suspected":false}}
JSON
```

The script emits JSON with `ready_to_file`, blocking `errors`, non-blocking `warnings`, a safe filing draft when ready, the mapped card action, and provisional-credit assessment. Review warnings and the source records; the output is not authorization to bypass controls.

After each tool result, accurately summarize what was filed or what is still needed, including document deadlines and the expected investigation/provisional-credit timeline. Continue with the next claim only after asking the customer whether they are ready to do so.
