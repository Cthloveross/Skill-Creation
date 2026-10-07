---
name: debit-card-dispute-filing
description: Verify a customer and file eligible debit-card purchase or ATM disputes using authoritative account, card, transaction, and dispute-history records. Applies Regulation E intake, exact dispute classifications, provisional-credit assessment, duplicate selection, and required card security action.
---

# Debit-card dispute filing

Use only for debit-card/linked checking-account transactions. Never substitute credit-card data, customer recollection, or a close merchant-name match for authoritative transaction and card records.

## 1. Verify and collect complete facts

1. Identify the customer from a supplied account field. Confirm **two** of date of birth, email, phone, and address against the retrieved user record. Obtain the current time and call `log_verification` with the retrieved record values and that timestamp before any filing.
2. Before proceeding, give the Regulation E unauthorized-activity disclosure: report within 2 business days—maximum liability $50; within 60 days—maximum $500; after 60 days—potentially unlimited/no recovery. This is an exposure limit, not a promise of recovery.
3. For every claim obtain the card identifier/last four, merchant or ATM, transaction date, first-noticed date, transaction method, whether the physical card is still held, PIN status (`yes_shared`, `yes_observed`, `no`, or `unknown`), merchant-contact result when applicable, fraud facts, and written-statement consent. If agreed, the conversation is the written statement.
4. Distinguish the **posted transaction amount** from the **amount actually disputed**. For a partially authorized family transaction, dispute only the unauthorized excess (for example, posted amount minus the amount the customer authorized). For an ATM cash shortage, obtain amount requested/debited and amount actually dispensed, and dispute only the shortage. Do not silently turn a partial claim into a claim for the entire transaction.
5. For suspected fraud over $500, ask whether a police report was filed and recommend one if not. Do not label a family-member overage as fraud merely because it was unauthorized.
6. For every ATM claim identify Rho-Bank versus third-party. For a third-party cash-discrepancy claim over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, must be signed and returned within 10 business days, failure may cause denial, and a false affidavit is a federal offense. Do not claim it was sent unless a declared tool confirms sending it.

## 2. Retrieve records and eligibility facts

Unlock and use these normal banking tools:

- `get_all_user_accounts_by_user_id_3847(user_id)`: identify the linked checking account, OPEN status, opening date, and any tier/level data.
- `get_debit_cards_by_account_id_7823(account_id)`: match the claimed card, confirm its `user_id` and linked account, and record its current status.
- `get_bank_account_transactions_9173(account_id)`: match date, exact debit amount, and merchant/ATM description to obtain `transaction_id` and posted status.
- `get_debit_dispute_status_7483(user_id)`: count active disputes by **account**, not customer. Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`.

A filing requires verified identity, a matched debit of at least $1, a transaction no more than 60 days old, an OPEN linked checking account, valid card/customer linkage, and room under the account limit (Entry 2, Mid 3, Premium 4, Elite 5). Count the whole requested batch plus existing active disputes. If the returned account label cannot be mapped to those tiers, do not invent a mapping; filing a total of two or fewer is known to fit every documented tier, but otherwise obtain an authoritative limit or stop that filing.

## 3. Select the exact claim and amounts

Use these exact categories:

- `atm_cash_discrepancy`: wrong/no ATM cash; `atm_deposit_not_credited`: missing ATM deposit.
- `goods_services_not_received`: paid but item/service never arrived.
- `duplicate_charge`: same purchase charged multiple times.
- `incorrect_amount`: merchant charged a wrong amount.
- `recurring_charge_after_cancellation`: canceled subscription continued.
- `unauthorized_transaction`: no fraud suspected (including a family member exceeding the permission given).
- `card_present_fraud` or `card_not_present_fraud`: fraud suspected, for physical or online/phone use respectively.

Set `transaction_type` from the actual method: PIN in-store is `pin_purchase`; signature in-store is `signature_purchase`; online/phone is `online_purchase`; ATM withdrawal/deposit is `atm_withdrawal`/`atm_deposit`; subscription is `recurring_payment`; and P2P is `person_to_person`.

For a duplicate, match the duplicate group and file **only its earliest transaction**. Transaction history is reverse chronological: when no more granular timestamp is returned, the oldest matching item is the one later in that returned list. Do not file the later duplicate.

Use the exact matched date for `transaction_date`, and the customer’s first-noticed date for `discovery_date`. `disputed_amount` is the supported disputed portion from the customer’s claim, never more than the matched debit.

## 4. Determine provisional credit and liability metadata

Set `provisional_credit_eligible` true only when the report is timely within 60 days of the statement, the account is OPEN and unrestricted, the customer supplied a written statement, and the category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, subject to these exclusions: non-fraud merchant dispute not first raised with the merchant, voluntarily shared PIN, or card-not-present transaction on an account under 30 days. The specific third-party ATM cash-discrepancy rule still requires qualifying provisional credit within 10 business days.

It is not required for missing goods/services, canceled-recurring, ATM-deposit, or incorrect-amount categories. If statement timing, holds/restrictions, or another required fact is unavailable, do not represent provisional credit as required; obtain the fact or use false and explain the limitation. Do not issue credit except through a declared banking tool.

State 10 business days normally (20 for an account under 30 days); third-party ATM investigations may take up to 90 days.

The filing tool also requires `customer_max_liability_amount`. For unauthorized activity, use the applicable timely-report cap, limited to the disputed amount: `min(disputed_amount, 50)` within 2 business days, `min(disputed_amount, 500)` through 60 days, and `-1` after 60 days. For transaction-error/merchant claims that are not unauthorized activity, use `0`. Keep the disclosure and this tool field consistent.

## 5. File and secure

Unlock `file_debit_card_transaction_dispute_6281` and make one call for each eligible supported claim with **all** required arguments:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date, discovery_date, disputed_amount, transaction_type,
card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided,
provisional_credit_eligible, customer_max_liability_amount, card_action
```

Map per-filing `card_action` exactly: fraud → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; every other category → `keep_active`. Never invent a merchant contact, police report, written statement, statement date, or fraud conclusion.

After successful filings, take one action per affected card at the highest severity: close/reissue > freeze > keep active. For a freeze, reconfirm verified ownership and ACTIVE status; tell the customer new and recurring transactions decline but pending authorizations may post and that it can be unfrozen; then call `freeze_debit_card_3892(card_id)`. If reissue is needed but no declared banking tool can do it, do not simulate it—transfer for completion. Never take a card action for a failed filing.

Conclude with each filed transaction, disputed portion, provisional-credit status/timing, needed affidavit/documentation, and actual card action.

## Planning helper

`scripts/plan_disputes.py` is a local deterministic preflight only; it never calls tools or files a dispute. It reads one JSON object from stdin and emits JSON. Supply authoritative values in `account_limits` and `items`. Item fields include `account_id`, `card_id`, `amount`, `matched_debit_amount`, `age_days`, `category`, `verified`, `transaction_matched`, `linked_account_open`, `written_statement_provided`, `statement_timely`, `account_open_unrestricted`, `merchant_contact_required`, `contacted_merchant`, `pin_compromised`, `new_account_card_not_present`, plus optional `duplicate_group` and `duplicate_rank` (1 is earliest). The output reports errors, mapped action, provisional-credit decision, per-account totals, and highest per-card action. Review errors before filing; runtime records and tool requirements control.
