---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, file, and follow up on debit-card transaction disputes under the supplied Regulation E and Rho-Bank requirements. Use when a verified customer asks to dispute debit-card purchases, ATM events, duplicates, incorrect amounts, missing goods, cancelled recurring payments, or suspected card fraud.
---

# Debit-card dispute intake and filing

Use this Skill for an interactive bank-support conversation. It separates facts supplied by the customer from facts that must be retrieved, and never treats a lookup by name, email, or user ID as identity verification.

## Inputs and required information

Collect one structured case per disputed transaction:

- customer identity and successful two-field verification;
- account/card identifier or sufficiently specific customer-facing details to look them up;
- transaction merchant/ATM, date, amount, and what occurred;
- date the customer first noticed the problem;
- category and transaction type;
- whether the physical card remains in the customer's possession and PIN-compromise status;
- merchant-contact result for non-fraud cases;
- ATM owner (Rho-Bank or third party) for ATM cases;
- police-report status for suspected fraud over $500;
- agreement to a written statement; and
- the account's status, account tier/product level, card linkage/status, target transaction, and open-dispute count obtained from bank tools.

Do not invent a transaction ID, account ID, card ID, dates, amounts, statement date, transaction type, merchant-contact response, fraud suspicion, or verification facts. If the customer says there are additional disputes but has not described them, invite them to provide the remaining transactions; the already-complete cases may still be processed once their prerequisites are satisfied.

## Conversation and verification

1. Explain before filing that prompt reporting affects unauthorized-activity liability: reported within two business days has a $50 maximum liability; within 60 days of the statement has a $500 maximum; after 60 days recovery may be unavailable. Do not promise a particular liability limit unless the relevant reporting/statement timing supports it.
2. Identify the customer using a provided name or email and retrieve the customer record. Then ask the customer to confirm **two of** date of birth, email, phone number, and address. Compare the customer-provided responses to the record.
3. After two fields match, retrieve the current time and call `log_verification` with every required record field and that timestamp. Do not file before this succeeds.
4. Ask only for still-missing intake facts. Explicitly ask whether the customer agrees to use the conversation as their written statement. Record `written_statement_provided=true` only after agreement.
5. For an unauthorized event, ask whether fraud is suspected. If yes, obtain whether it was physical/in-store or online/phone and classify as card-present or card-not-present fraud. Ask card possession and one exact PIN value: `yes_shared`, `yes_observed`, `no`, or `unknown`.
6. For fraud exceeding $500, ask whether a police report was filed and recommend one if not. This recommendation does not by itself prevent filing.
7. For an ATM issue, identify Rho-Bank versus third-party ATM before applying its applicable process. For non-fraud merchant disputes, ask whether the customer contacted the merchant. Encourage merchant contact where appropriate, but do not falsely say that contact is universally required to file.

## Retrieve and validate bank facts

Unlock and use the named internal tools through the available discoverable-agent-tool mechanism before calling them:

1. `get_all_user_accounts_by_user_id_3847(user_id)` — find the relevant checking account and retrieve account type, tier/product level, status, and opening date.
2. `get_debit_cards_by_account_id_7823(account_id)` — locate the card linked to that account. Match any customer-provided last four digits, and ensure the intended card is usable/current rather than an old closed card.
3. `get_bank_account_transactions_9173(account_id)` — identify the exact posted debit transaction ID, date, amount, description, and type. The response is reverse chronological. Never choose a transaction merely because its description is similar.
4. `get_debit_dispute_status_7483(user_id)` — count only disputes in `OPEN` status for the selected `account_id`.

A filing is eligible only if all of the following hold:

- customer verification has been logged;
- the selected transaction is at least $1.00 and is no more than 60 days old;
- it belongs to the selected linked checking account;
- the checking account is `OPEN`;
- the selected debit card is linked to that account;
- account-specific open-dispute count remains below the applicable tier limit: Entry 2, Mid 3, Premium 4, Elite 5; and
- every required filing field is known and valid.

If any item fails or cannot be established, explain the blocker and do not submit that dispute. Do not use disputes on other accounts when applying a per-account limit. When duplicate transactions are present, select and dispute the earliest transaction first; identify the actual extra duplicate precisely from the transaction list rather than filing both unless the customer requests and facts support separate disputes.

## Classification and filing values

Use exactly one allowed category:

- `unauthorized_transaction` only when the transaction was not authorized **and fraud is not suspected**;
- `card_present_fraud` for suspected fraud involving an in-person/physical-card transaction;
- `card_not_present_fraud` for suspected fraud involving online/phone/card-not-present use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for the corresponding event.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set `disputed_amount` to the amount actually in dispute, not automatically to the full posted charge. For an overcharge, it is normally the difference between the charged amount and the documented expected amount; for one extra duplicate, it is the duplicate charge amount. Use posted debit amounts as positive dispute dollar values.

The filing tool also requires `customer_max_liability_amount`. For a non-unauthorized error dispute, use `0`. For an unauthorized/fraud dispute, establish the report timing and use the lesser of the disputed amount and `$50` when reported within two business days, the lesser of the disputed amount and `$500` when within 60 days, or `-1` when liability is unlimited after 60 days. Do not guess this timing.

Map `card_action` on each individual filing exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other permitted categories | `keep_active` |

Determine `provisional_credit_eligible` conservatively. It is required only when timely reporting within 60 days of the statement is established, the category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, a written statement is provided, and the checking account is OPEN without holds/restrictions. It is not required for the other listed merchant/ATM-deposit/incorrect-amount categories, when a non-fraud merchant has not been contacted, when PIN was voluntarily shared, or for a card-not-present transaction on an account under 30 days old. If needed timing or account-restriction facts are unavailable, do not represent credit as required; seek the missing fact or follow the normal escalation path. Qualifying credit is for the full disputed amount subject to applicable late-reporting liability offset.

## Submit and complete card action

For every eligible transaction, unlock and call `file_debit_card_transaction_dispute_6281` using this exact conceptual object:

```json
{
  "transaction_id": "retrieved transaction ID",
  "account_id": "retrieved checking account ID",
  "card_id": "retrieved linked debit card ID",
  "user_id": "verified user ID",
  "dispute_category": "allowed category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "allowed transaction type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "customer_max_liability_amount": 0.0,
  "card_action": "mapped action"
}
```

Do not treat the decision record as a bank action. After all successful filings for the same card, perform the single actual card action required by the highest severity among that card's successful filings: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Preserve each filing's own mapped `card_action`; do not overwrite it with the aggregate action. Use the declared normal card-action tool/process and only after its prerequisites are confirmed.

Conclude with the filed transaction(s), dispute category, requested amount, card action taken or why none was needed, written-statement status, and applicable provisional-credit expectation. Do not disclose internal fraud/security decline codes.

## Decision record

Before each filing, make a short per-transaction record from live facts containing the matched transaction and card IDs, account status and tier/limit result, open-dispute count, all filing fields, the selected category and transaction type, the individual card-action mapping, the liability value, and the provisional-credit decision. This avoids reusing values from another transaction or account. Re-check the per-account open-dispute count after each successful filing before filing the next case.
