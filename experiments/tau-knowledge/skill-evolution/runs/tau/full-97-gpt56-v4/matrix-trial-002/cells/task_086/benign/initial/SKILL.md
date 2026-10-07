---
name: debit-card-dispute-intake-and-filing
description: Handle a verified customer's debit-card transaction disputes end to end: gather a complete staged intake, find the correct checking account/card/transaction, enforce Regulation E and account eligibility, file each eligible dispute, and perform the single most-severe required card action. Use when a customer reports unauthorized debit-card activity, ATM errors, duplicate charges, incorrect amounts, missing goods, or post-cancellation recurring charges.
---

# Debit-card dispute intake and filing

Use this Skill for debit-card disputes only. Do not confuse debit-card transactions with credit-card transactions. Do not file, freeze, or close a card until identity has been verified and the relevant prerequisites below have been checked. Never invent a transaction ID, account status, customer answer, statement date, card status, tool result, or a tool that is not available.

## 1. Establish identity and customer scope

1. Locate the user by the supplied name or email with `get_user_information_by_name` or `get_user_information_by_email`.
2. Verify the caller by asking them to confirm **two of four** profile fields: date of birth, email, phone number, and address. Do not reveal answers first.
3. On successful verification, call `get_current_time` and then `log_verification` with all returned profile fields and the timestamp.
4. Explain the applicable unauthorized-activity liability exposure before proceeding:
   - reported within 2 business days of the statement: maximum $50;
   - within 60 days: maximum $500;
   - after 60 days: potentially unlimited and recovery may not be possible.
   This is an explanation of the reported timing, not a conclusion that a claim will be denied.
5. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`. A candidate account must be a checking account and `OPEN`. Retain its account class/tier for the per-account dispute limit.
6. For every candidate checking account, retrieve cards using `get_debit_cards_by_account_id_7823` and match the card number last four digits, linked `user_id`, and card/account relationship. Do not select a closed historical card when an active card is the card the customer identifies.

These specialized banking tools are discoverable. Before using a specialized tool named in this Skill, unlock it with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` with a JSON argument string. The required specialized tools are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `get_bank_account_transactions_9173`
- `get_debit_dispute_status_7483`
- `get_atm_deposit_images_8473` when an ATM deposit image is needed
- `file_debit_card_transaction_dispute_6281`
- `freeze_debit_card_3892` when the final action is a freeze
- `close_debit_card_4721` when the final action is close and reissue

## 2. Conduct a complete, customer-friendly staged intake

A customer may ask to work through cards or charges one at a time. Honor that request, but keep a separate intake record for every alleged transaction and do not silently treat omitted issues as withdrawn. After each answer, ask only for the missing facts for that charge/card, then continue to the next charge and the next card.

For each alleged transaction obtain:

- merchant/ATM/recipient, transaction date, charged amount, and what happened;
- when the customer first noticed the error;
- whether it is debit card activity and its payment channel (in-store PIN, in-store signature, online/phone, ATM withdrawal, ATM deposit, recurring, or P2P);
- whether it is unauthorized and, if so, whether fraud is suspected. For fraud, determine physical/card-present versus online/phone/card-not-present;
- whether the customer still physically possesses the card;
- PIN state: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- for non-fraud merchant disputes, whether they attempted to resolve it with the merchant and the result;
- for fraud over $500, whether a police report was filed; if not, recommend filing one;
- whether the customer agrees that this conversation can be used as their written statement. Set `written_statement_provided` true only upon agreement.

For ATM matters, explicitly identify the ATM as Rho-Bank or third-party. For a third-party cash discrepancy over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, must be signed and returned within 10 business days, failure to return may result in denial, and false signing is a federal offense. Record/document the need for it according to the available workflow; do not claim that an email was sent without a successful tool/workflow result.

For a Rho-Bank ATM cash discrepancy, retrieve the corresponding account transactions to review the journal-related record and compare it with the claim. If confirmed, follow the available provisional-credit workflow immediately; if records show the stated amount, explain that it cannot currently be validated but a formal dispute may still be filed. For an ATM deposit-not-credited claim, retrieve deposit images with `get_atm_deposit_images_8473` when the transaction can be identified.

## 3. Match and preflight every proposed filing

For each implicated checking account, call `get_bank_account_transactions_9173(account_id)`. Transactions are newest first. Match the customer-provided date, amount, description, and type; do not rely on description alone. A debit has a negative transaction amount, so use its absolute value as the disputed amount. Ask for clarification if more than one transaction matches.

If the customer identifies duplicate copies of the same charge, identify all matching copies and dispute the **earliest/first transaction**, not every duplicate merely because it appears in history.

Call `get_debit_dispute_status_7483(user_id)` before filing. Count only disputes with status `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED` for the matched `account_id`. The maximum is per account: Entry 2, Mid 3, Premium 4, Elite 5. Existing disputes associated with another account do not consume this account's limit. If new filings would exceed the limit, explain the blocker and do not file the excess claims.

Each filing must satisfy all of the following:

- verified customer/card owner;
- matching transaction with a disputed amount of at least $1.00;
- transaction no more than 60 days old at filing;
- linked checking account is OPEN and the card is linked to it;
- available open-dispute capacity on that account;
- all required intake facts are known and truthful.

Use `scripts/preflight_disputes.py` to make date/limit/category/action checks repeatable. It supports decision support only; live banking-tool results and the customer's actual answers remain authoritative.

### Category and transaction-type mapping

Use an exact supported category:

- `unauthorized_transaction` only if unauthorized activity is **not** suspected fraud;
- `card_present_fraud` for suspected fraud where the physical card was used;
- `card_not_present_fraud` for suspected online/phone/card-not-present fraud;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use the exact transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Do not classify a family member's unapproved use as fraud merely because it was unauthorized; ask whether fraud is suspected.

## 4. Decide and disclose provisional-credit eligibility

Set `provisional_credit_eligible` true only when all of these are established: timely report within 60 days of the statement showing the transaction, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement agreed/provided, and an OPEN checking account with no holds or restrictions.

It is not required for goods/services not received, recurring charges after cancellation, ATM deposits not credited, or incorrect amount claims. It is also not required where the applicable non-fraud merchant dispute was not first raised with the merchant, where the PIN was voluntarily shared, or for a new account (under 30 days) with a card-not-present transaction. If statement timing, account age, holds/restrictions, or a required customer response is unavailable, do not represent the claim as eligible; obtain the fact or state it cannot yet be determined.

Where required, provisional credit is the full disputed amount, subject to any applicable $50/$500 late-reporting liability offset. Standard accounts have a 10-business-day deadline; accounts open less than 30 days have 20 business days. Third-party ATM disputes have a 90-day investigation and still require provisional credit within 10 business days when eligible. With provisional credit, investigations are generally 45 business days, or 90 days for international, foreign-merchant POS, or new-account cases. Do not say credit has been issued unless a successful credit action is returned by an available banking workflow.

## 5. File and then perform one card action per card

For every eligible, fully documented claim, call `file_debit_card_transaction_dispute_6281` with exactly these values:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (`MM/DD/YYYY`), `discovery_date` (`MM/DD/YYYY`), `disputed_amount` (positive float), `transaction_type`, `card_in_possession` (boolean), `pin_compromised`, `contacted_merchant` (boolean), `police_report_filed` (boolean), `written_statement_provided` (boolean), `provisional_credit_eligible` (boolean), and `card_action`.

Record the per-dispute `card_action` exactly as follows:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other supported categories → `keep_active`

After all disputes for the same card are successfully filed, take the single most severe actual action across those filings: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. Do not alter the action recorded in any individual filing because of another filing.

For a required freeze, verify the card is ACTIVE and use `freeze_debit_card_3892(card_id)`. Tell the customer that new and recurring transactions will decline, pending authorizations may still settle, and it may later be unfrozen. If it is already frozen or cannot be frozen, do not repeat or falsely confirm success.

For a required close/reissue, the available close operation is `close_debit_card_4721(card_id, reason="fraud_suspected")`. Before closing, check the card is ACTIVE or PENDING and check its transactions for pending/processing transactions or pending refunds. Fraud-suspected closure bypasses the 14-day card-age rule but not the stated pending-item checks. Close only after those requirements are met. A close is permanent; recurring payments need updating and closed-card refunds go to the linked checking account. Do not claim a replacement was ordered unless a documented, available ordering workflow succeeds; offer/perform that separately only if such a tool is available.

## 6. Completion and failure handling

Give a concise per-claim recap: matched transaction, category, amount, dispute result/ID if returned, documentation/affidavit needs, provisional-credit status as determined (not assumed), and actual card action result. State investigation timing appropriate to the claim. If a prerequisite fails, explain the precise blocker and what information/action is needed. Never submit a partial or guessed filing simply to finish an intake.

If an action returns `UNKNOWN`, do not repeat it. Explain that its outcome must be checked/escalated. Use a human transfer only when the issue cannot be completed safely through the available process, with a factual summary of verified identity, card/account, attempted checks, and unresolved blocker.

## Helper script

Run `python scripts/preflight_disputes.py` by sending JSON on stdin. It emits one JSON object on stdout. Input schema:

```json
{
  "as_of": "MM/DD/YYYY",
  "account_class": "Entry|Mid|Premium|Elite",
  "open_disputes": 0,
  "account_open": true,
  "account_has_holds_or_restrictions": false,
  "account_age_days": 100,
  "items": [
    {
      "transaction_date": "MM/DD/YYYY",
      "amount": 10.0,
      "category": "duplicate_charge",
      "transaction_type": "signature_purchase",
      "written_statement_provided": true,
      "timely_statement_report": true,
      "contacted_merchant": true,
      "pin_compromised": "no",
      "is_first_duplicate": true
    }
  ]
}
```

`timely_statement_report` must be supplied from actual statement/report facts; the script does not infer it from a transaction date. The output lists item-specific blockers, category card actions, provisional-credit determinations, and account-capacity results. Validate all `blockers` are empty before filing; independently check live card ownership/status, the matched transaction ID, and all filing answers.
