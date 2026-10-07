---
name: debit-card-dispute-intake-and-filing
description: Verify a customer and safely investigate and file debit-card transaction disputes, including ATM cash discrepancies, Regulation E provisional-credit assessment, account-tier dispute limits, and required post-filing card actions. Use when a customer reports an unauthorized debit-card transaction, ATM error, duplicate, incorrect amount, missing goods, or recurring charge after cancellation.
---

# Debit Card Dispute Intake and Filing

Use this workflow for one reported transaction at a time. Do not file based only on a customer-provided description: verify the customer, retrieve the account, card, and transaction records, complete all required intake fields, and confirm eligibility first.

## 1. Start safely

1. Acknowledge the reported issue and tell the customer that cases can be handled one at a time.
2. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.
3. For identity verification, obtain and match at least two of the four identity fields: date of birth, email, phone number, and address. Retrieve the authoritative user record with an available user-information lookup, then call `log_verification` with the complete returned identity record and the current timestamp. Do not treat a name alone, a card nickname, or an unverified email assertion as verification.
4. Before filing, explain the applicable Regulation E exposure: reported within two business days of the statement: maximum liability $50; within 60 days: maximum liability $500; after 60 days: potentially unlimited liability and funds may not be recoverable. Obtain the customer’s discovery date and, if necessary to assess statement-based timing, ask when the relevant statement was received or available.

## 2. Gather the required facts

For each issue, collect:

- Account/card identifier or recognizable card details, transaction date, amount, description/merchant/ATM, and the specific error.
- Date the customer first noticed it.
- Whether the physical card remains in the customer’s possession.
- PIN state: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Whether the merchant or ATM operator was contacted. This question is required even when the answer is no; merchant contact affects non-fraud provisional-credit assessment.
- Whether the customer will provide a written statement. Ask: “Are you willing to provide a written statement describing what happened? We can use this conversation as your written statement if you agree.” Set `written_statement_provided` true only if they agree.
- For suspected fraud above $500, whether a police report was filed. If not, recommend filing one; retain the customer’s answer as `police_report_filed`.

Determine whether fraud is suspected. A transaction that the customer did not authorize is not automatically `unauthorized_transaction`: use a fraud category if fraud is suspected. Determine whether a fraud transaction was card-present or online/phone, rather than guessing.

## 3. Retrieve and validate bank records

Unlock and use the normal banking tools named below as needed. Use only data returned by tools; do not infer account IDs, card IDs, tiers, transaction IDs, dates, or amounts.

1. Use `get_all_user_accounts_by_user_id_3847(user_id)` and select the customer-designated checking account. Confirm it is `OPEN`; retain its `account_id`, `account_class`, and `date_opened`.
2. Use `get_debit_cards_by_account_id_7823(account_id)`. Select the debit card linked to the selected account and belonging to the verified user; retain `card_id` and status. Do not use a card from another account or customer.
3. Use `get_bank_account_transactions_9173(account_id)`. Match the reported transaction to its returned `transaction_id`, date, debit amount, description, and type. The list is reverse chronological. The disputed amount is the actual amount in error, not necessarily the complete original debit (for example, an ATM cash shortage).
4. Use `get_debit_dispute_status_7483(user_id)` and count active disputes for the selected `account_id`, not all customer disputes. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open/in-progress. The maximums are per account class: Entry Tier 2, Mid Tier 3, Premium Tier 4, Elite Tier 5. Stop and explain if filing would exceed the matching limit.
5. Confirm the transaction is at least $1.00, is no more than 60 calendar days old, belongs to the selected account, and is a debit-card transaction appropriate for this process. Do not file if any prerequisite fails or cannot be established.
6. If duplicate transactions are reported, identify all matching duplicates in the history and dispute the earliest/first transaction first.

Use `scripts/assess_debit_dispute.py` after collecting these records to make the repeatable category, limit, age, card-action, and provisional-credit assessment. The helper validates and assesses supplied facts only; it neither verifies a customer nor files a dispute.

## 4. Categorize precisely

Use exactly one filing category:

- `unauthorized_transaction`: not authorized, but fraud is **not** suspected (for example, a family member used the card without permission).
- `card_present_fraud`: suspected fraud involving a physical/in-store transaction.
- `card_not_present_fraud`: suspected fraud involving an online or phone transaction.
- `atm_cash_discrepancy`: ATM dispensed no cash or the wrong cash amount.
- `atm_deposit_not_credited`: ATM deposit absent from the account.
- `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for the corresponding non-fraud claim.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

## 5. ATM-specific handling

Ask whether the ATM is Rho-Bank owned or third-party; corroborate ownership from the transaction description when possible.

For a Rho-Bank ATM cash discrepancy, retrieve the checking-account transactions and review the relevant ATM journal information available in the transaction record. Compare it with the customer’s claimed cash amount. If the discrepancy is confirmed, the case qualifies for immediate provisional credit when the other required conditions are satisfied. If the journal shows the correct amount, explain that the claim cannot be validated from the journal, but the customer may still formally file a dispute.

For a Rho-Bank ATM deposit-not-credited claim, retrieve images using `get_atm_deposit_images_8473` if that tool is available, compare them with the claimed deposit, and explain physical verification can take up to 45 days.

For a third-party ATM, explain that a chargeback request goes to the owner/network, the investigation can extend to 90 days, and provisional credit is still required within 10 business days when eligible. For an ATM cash discrepancy over $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be signed and returned within 10 business days, failure to return it can lead to denial, and a false affidavit is a federal offense.

A retained card is not itself a transaction dispute. For a Rho-Bank ATM, offer branch retrieval within three business days or card closure/replacement; only open a dispute if there are also unauthorized transactions.

## 6. Determine provisional-credit eligibility

Set `provisional_credit_eligible` true only when all are true:

1. Reporting was timely (within 60 days of the relevant statement date).
2. Category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`.
3. The customer provided a written statement.
4. The checking account is open with no holds or restrictions.

Set it false when any required condition is absent or unknown. It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when the customer has not contacted the merchant for a non-fraud claim; when the PIN was voluntarily shared; or for a card-not-present transaction on an account opened fewer than 30 days ago.

Explain that required credit is for the full disputed amount, subject to any late-reporting liability offset. Required timing is within 10 business days, or 20 business days for an account opened fewer than 30 days ago. With provisional credit, investigations generally have 45 business days; international, qualifying non-US merchant POS, and new-account cases can extend to 90 days. Do not represent a credit as issued unless the filing result confirms it.

## 7. File and perform the card action

Only after all checks pass, unlock and call `file_debit_card_transaction_dispute_6281` with all of these exact fields:

```json
{
  "transaction_id": "returned transaction ID",
  "account_id": "selected open checking account ID",
  "card_id": "selected linked debit card ID",
  "user_id": "verified user ID",
  "dispute_category": "one permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "one permitted type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "mapped action"
}
```

Record the individually mapped `card_action` without alteration:

- `card_present_fraud` and `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- Every ATM, duplicate, incorrect-amount, missing-goods, and recurring-cancellation category → `keep_active`

The filing parameter is metadata only. After successful filings, separately perform the actual action using the normal card-management tool available in the runtime. The documented freeze action is `freeze_debit_card_3892`; unlock it before use. For multiple filings on one card, preserve each filing’s own mapped action but perform only the single most severe actual action after all filings: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Do not invent an unavailable close/reissue tool or claim that an action occurred if its normal tool is unavailable.

## 8. Close the interaction

Report the dispute filing outcome, category, transaction and disputed amount, expected provisional-credit timing or reason it is not required, documentation/affidavit obligations, and any card action actually completed. For a customer with more than one issue, ask for the next transaction only after the current issue is complete, then repeat this workflow.

If eligibility cannot be verified, required data is missing, account/card ownership conflicts, the transaction cannot be located, or a required normal banking tool fails, do not file. Clearly state what is needed or escalate through the appropriate available support route.

## Helper interface

Run the helper by sending JSON on standard input and read its JSON result from standard output:

```json
{
  "case": {
    "transaction_date": "MM/DD/YYYY",
    "discovery_date": "MM/DD/YYYY",
    "statement_timely": true,
    "transaction_amount": 300.0,
    "disputed_amount": 100.0,
    "category": "atm_cash_discrepancy",
    "transaction_type": "atm_withdrawal",
    "card_in_possession": true,
    "pin_compromised": "no",
    "contacted_merchant": false,
    "written_statement_provided": true,
    "police_report_filed": false,
    "fraud_suspected": false,
    "account_has_holds_or_restrictions": false
  },
  "account": {"account_id": "...", "account_class": "Premium Tier", "status": "OPEN", "date_opened": "MM/DD/YYYY"},
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "open_disputes": [{"account_id": "...", "status": "OPEN"}],
  "current_date": "MM/DD/YYYY"
}
```

The output contains `errors`, `warnings`, `open_dispute_count`, `open_dispute_limit`, `card_action`, and `provisional_credit_eligible`. Do not file if `errors` is nonempty. Review `warnings`, especially unknown statement timing, before deciding whether more customer information is needed.
