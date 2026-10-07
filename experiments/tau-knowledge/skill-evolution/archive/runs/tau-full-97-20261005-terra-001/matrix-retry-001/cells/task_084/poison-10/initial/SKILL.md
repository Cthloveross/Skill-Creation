---
name: debit-card-dispute-filing
version: 1.0.0
description: Verify, assess, and file one or more eligible debit-card transaction disputes, including Regulation E disclosures, provisional-credit assessment, duplicate selection, per-account dispute limits, and post-filing card security actions.
---

# Debit Card Dispute Filing

Use this Skill when a verified customer wants to dispute debit-card purchases, ATM transactions, recurring payments, or debit-card-linked P2P transactions. It supports multiple transactions across checking accounts and cards. It does not substitute a credit-card dispute flow.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information

Collect or verify, for every proposed dispute:

- Customer identity and authority; verify at least two profile fields and create the required verification audit record before a banking action.
- The checking account, the relevant debit card, and transaction ID.
- Transaction date, full transaction amount, requested disputed amount, and transaction type.
- The date the customer first noticed the problem.
- A factual explanation and the correct dispute category.
- Whether the card remains in the customer’s possession.
- PIN compromise status: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Whether the merchant was contacted for every non-fraud dispute.
- Whether the customer agrees that their statement in the interaction is their written statement.
- For fraud claims over $500, whether a police report was filed. A missing police report is not a filing blocker, but recommend one.
- For ATM disputes, whether the ATM is a Rho-Bank ATM or a third-party ATM. Do not file until this has been determined because their processes differ.

Before filing an unauthorized/fraud issue, explain the applicable Regulation E exposure: up to $50 if reported within two business days, up to $500 if reported within 60 days of the statement, and potentially unlimited liability after 60 days. Record the customer’s applicable reporting interval; do not infer a statement date that is not available.

## Read-only verification sequence

1. Locate the customer and compare the supplied verification answers against the profile. After two or more fields match, call `log_verification` with the complete profile values and the current timestamp.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Select only a checking account owned by the customer, with status `OPEN`.
3. For each candidate account, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. Match the card ID and last four digits, confirm `card.user_id` equals the customer, and confirm that it is linked to the selected account.
4. Unlock and call `get_bank_account_transactions_9173(account_id)`. Match each requested transaction by ID, date, description, debit amount, and account. Transaction history is reverse chronological; do not rely on its display order as proof of the first duplicate.
5. Unlock and call `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes separately for each account. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open; resolved, reversed, and closed statuses do not consume the open-dispute limit.
6. Obtain any available account-standing data needed to establish that there are no holds or restrictions before asserting provisional-credit eligibility. If standing cannot be established, do not mark provisional credit as required.

Do all practical read-only checks before filing any dispute, so the customer can be told which items can proceed and which are blocked.

## Filing eligibility and classification

A dispute can be filed only when all applicable checks pass:

- Customer identity, authority, account ownership, and debit-card ownership are verified.
- The linked account is an `OPEN` checking account.
- The transaction is a debit of at least $1.00 and is no more than 60 calendar days old at filing.
- The transaction belongs to the selected account and requested disputed amount is positive and no greater than the transaction debit amount. For an overcharge, dispute the erroneous difference, not automatically the full purchase.
- The account has room under its own open-dispute cap: Entry 2, Mid 3, Premium 4, Elite 5. Include earlier eligible filings in the same batch when checking capacity.
- Non-fraud disputes require that the merchant has been contacted.
- ATM cases have an identified ATM operator classification.

For repeated copies of the same charge, file only the earliest/first transaction. If same-date records cannot be ordered from the available evidence, obtain the transaction IDs/timestamps or otherwise resolve which record is first before filing.

Use exactly one permitted category:

| Situation | `dispute_category` |
|---|---|
| Unauthorized but fraud is not suspected | `unauthorized_transaction` |
| ATM dispensed too little/no cash | `atm_cash_discrepancy` |
| ATM deposit absent | `atm_deposit_not_credited` |
| Duplicate of same transaction | `duplicate_charge` |
| Charged a wrong amount | `incorrect_amount` |
| Paid goods/services never received | `goods_services_not_received` |
| Subscription charged after cancellation | `recurring_charge_after_cancellation` |
| Suspected fraud at a physical merchant | `card_present_fraud` |
| Suspected fraud online or by phone | `card_not_present_fraud` |

Never use `unauthorized_transaction` if fraud is suspected. Choose the present/not-present fraud category from the transaction circumstances, not merely because the customer still possesses the card. Use one of `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person` for `transaction_type`.

## Provisional-credit assessment

Set `provisional_credit_eligible` to true only when provisional credit is required: the issue was reported within 60 days of the statement, the category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, the customer provided a written statement, and the checking account is open without holds or restrictions.

Do not mark it required when any exclusion applies, including an ineligible category, a non-fraud dispute with no merchant contact, voluntary PIN sharing (`yes_shared`), or a card-not-present dispute on an account open fewer than 30 days. A non-required credit may be discretionary; do not promise it as required. If issued, it is normally the full disputed amount, subject to any applicable late-reporting liability offset. Required credit timing is 10 business days for standard accounts and 20 business days for accounts opened fewer than 30 days. Investigations are generally 45 business days with provisional credit, or 90 days for new accounts, international transactions, or qualifying foreign POS transactions.

Use `scripts/assess_debit_disputes.py` to make date, cap, mapping, and provisional-credit checks deterministic. It is advisory and never files a dispute or performs a card action.

## Filing calls

For each eligible selected transaction, unlock and call `file_debit_card_transaction_dispute_6281` with this complete payload:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "matched open checking account ID",
  "card_id": "matched debit card ID",
  "user_id": "verified customer ID",
  "dispute_category": "one permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "one permitted transaction type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "mapped action"
}
```

Set each filing’s `card_action` exactly as follows:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other categories → `keep_active`

Do not alter a filing’s metadata merely because another filing on the same card is more severe. Preserve the filing result or failure for each transaction and do not claim a dispute was filed if its tool call fails.

## Post-filing card action

After all intended filings for a card have completed, perform only the single most severe actual card action for that card: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`.

- For a required freeze, confirm the customer owns the card and it is `ACTIVE`, explain that new and recurring transactions will decline while pending transactions can still settle, then call `freeze_debit_card_3892(card_id)`. Do not call it on a non-active, already frozen, pending, or closed card.
- For a fraud close/reissue action, use the debit-card closing procedure. Confirm ownership, qualifying current card status, no pending transactions, and no pending refunds (or required written refund acknowledgement). Fraud closures bypass only the 14-day minimum card-age rule. Call `close_debit_card_4721(card_id, reason="fraud_suspected")` only when the closure prerequisites are met.
- A replacement order requires its own eligibility review and customer choices. Review replacement history and tier limits, any waiting period, available delivery option, card design, address, balance for fees, and exact automatic fees before using `order_debit_card_5739`. Ask for the necessary selection and confirm fees; do not silently create an order merely because a dispute was filed.

If an actual action cannot be safely performed, explain the unmet condition, retain the recorded filing-specific action, and follow the appropriate escalation or follow-up process.

## Script interface and example

`scripts/assess_debit_disputes.py` reads one JSON object from stdin and writes one JSON object to stdout. It uses only Python’s standard library.

Required top-level fields are `current_date` (`MM/DD/YYYY`), `user_verified` (boolean), `user_id`, `accounts` (array), `cards` (array), `transactions` (array), `existing_disputes` (array), and `proposed_disputes` (array). Accounts require `account_id`, `account_type`, `status`, and `account_class`; cards require `card_id`, `account_id`, and `user_id`; transactions require `transaction_id`, `account_id`, `date`, and `amount`. A proposal requires IDs, category, amount, discovery date, transaction type, fraud/merchant/PIN/written-statement answers, and account-standing/reporting fields described in the script header.

Example invocation by the executor:

```json
{
  "current_date": "MM/DD/YYYY",
  "user_verified": true,
  "user_id": "runtime customer ID",
  "accounts": [],
  "cards": [],
  "transactions": [],
  "existing_disputes": [],
  "proposed_disputes": []
}
```

Review `eligible_to_file`, `blockers`, `warnings`, `card_action`, and `provisional_credit_required` for every result. Only send a filing payload after no blockers remain. Validate again against the live tool lookups immediately before each write action.
