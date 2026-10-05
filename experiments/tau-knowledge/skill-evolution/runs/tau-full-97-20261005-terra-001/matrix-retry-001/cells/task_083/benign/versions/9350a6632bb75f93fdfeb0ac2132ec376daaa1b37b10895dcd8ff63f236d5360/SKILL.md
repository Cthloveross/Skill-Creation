---
name: debit-card-transaction-dispute
version: 1.0.0
description: Safely investigate and file one or more debit-card transaction disputes, including Regulation E disclosures, provisional-credit assessment, ATM-specific handling, dispute-limit checks, and the required post-filing card action. Use when a verified customer reports an unauthorized debit-card charge, ATM error, duplicate, incorrect amount, missing goods/services, or a recurring charge after cancellation.
---

# Debit Card Transaction Dispute

Use this Skill to process disputes transaction by transaction. Do not file a dispute, freeze a card, or close a card merely because this Skill identifies a recommendation. Those are execution-agent actions that require the corresponding banking tools and successful prerequisite checks.

## Required runtime tools

Unlock and use these internal tools as needed:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `get_debit_dispute_status_7483(user_id)`
- `file_debit_card_transaction_dispute_6281(...)`
- `freeze_debit_card_3892(card_id)` when the final per-card action is freeze
- `close_debit_card_4721(card_id, reason)` when the final per-card action is close
- `get_atm_deposit_images_8473(...)` for Rho-Bank ATM deposit-not-credited investigation, if available

Use `unlock_discoverable_agent_tool` before calling an internal tool through `call_discoverable_agent_tool`. Do not invent a tool or arguments for an ATM-network chargeback process: follow the available operational workflow after filing or escalate if no supported workflow exists.

## 1. Verify identity before account or card actions

A name or email lookup identifies a record but is **not** identity verification. Obtain confirmation of at least two of date of birth, email, phone number, and address. Retrieve the user record as needed, then call `get_current_time` and `log_verification` with all required returned identity fields and the verification timestamp. Do not proceed with filing or card actions unless verification is successfully logged.

If identity cannot be verified, do not disclose account activity or file the claim. Transfer when specialist handling is needed, using `account_ownership_dispute` for an identity/ownership failure that requires a specialist; use `fraud_or_security_concern` when circumstances indicate fraud or account compromise.

## 2. Give required Regulation E notice

Before proceeding on an unauthorized-activity report, explain the customer’s maximum liability based on when they noticed it relative to their statement:

- within 2 business days: $50;
- within 60 days: $500;
- after 60 days: potentially unlimited and funds may not be recoverable.

Determine the applicable bracket from the statement date and notice date; do not treat calendar-day arithmetic as business-day arithmetic. Record the reporting/timeliness assessment. Prompt reporting is relevant to provisional-credit eligibility. The customer may provide multiple issues gradually; honor a request to handle one transaction at a time.

## 3. Discover and validate the relevant account, card, and transaction

1. Retrieve all accounts. Select a checking account only after confirming it is the account tied to the reported card/transaction. It must be `OPEN` to file.
2. Retrieve cards for that account. Match the customer’s card last four digits when provided, then confirm the selected card’s `account_id` and `user_id` match the case. Retain the actual `card_id` rather than relying on a nickname or last four digits.
3. Retrieve the account transactions and match the date, amount, description, and transaction type. Use the returned `transaction_id`, transaction date, and the absolute value of the debit amount. Do not use a customer-supplied amount or an assumed year when the posted transaction does not confirm it.
4. Retrieve dispute status and count non-final disputes for the same `account_id`. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open; do not count resolved or closed statuses. The maximum open disputes is per account: Entry Tier 2, Mid Tier 3, Premium Tier 4, Elite Tier 5.
5. Check that the disputed amount is at least $1.00, the transaction is within 60 days old, the transaction is not already disputed, and the applicable account limit has not been reached.

If information does not match exactly or a prerequisite fails, explain the specific issue and do not file. If the customer describes repeated duplicates, identify the earliest transaction in that duplicate set and file that transaction first. Do not file later duplicates first.

## 4. Gather a complete case record for each transaction

Collect these fields separately for every claim; do not apply answers from one card or transaction to another without confirmation:

- exact posted transaction, date, disputed amount, and account/card;
- `discovery_date` (MM/DD/YYYY);
- whether fraud is suspected and how the transaction occurred;
- whether the physical card remains in the customer’s possession;
- PIN state: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant/ATM operator was contacted (required input for all filings and especially important for non-fraud claims);
- whether a written statement was provided. Ask whether the customer agrees to use the conversation as the written statement; set the field true only on agreement;
- for fraud claims over $500, whether a police report was filed. If not, recommend one, while retaining the customer’s actual answer;
- whether the customer reported within 60 days of the statement showing the transaction; and
- account opening date and whether there are holds/restrictions, for provisional-credit assessment.

Use only these dispute categories:

- `unauthorized_transaction`: not authorized but fraud is **not** suspected (for example, a family member used the card without permission);
- `card_present_fraud`: suspected fraud with a physical/in-store card-present transaction;
- `card_not_present_fraud`: suspected fraud for online/phone/card-not-present use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Ask rather than guess when classification is ambiguous.

## 5. ATM handling

Ask whether the ATM was Rho-Bank branded or third-party. Record the answer before filing.

- **Rho-Bank ATM cash discrepancy:** review the corresponding account transactions/journal information and compare it with the claim. If the discrepancy is confirmed, provisional credit is immediate. If records show the correct amount, explain that the claim cannot be validated but the customer may still formally dispute it.
- **Rho-Bank ATM deposit not credited:** retrieve deposit images and compare the envelope/check evidence with the stated amount. Explain physical verification can take up to 45 days.
- **Card retained at a Rho-Bank ATM:** offer branch retrieval within 3 business days or card closure/replacement. A dispute is not needed unless there are also unauthorized transactions.
- **Third-party ATM:** file the dispute and submit the required chargeback request through the supported ATM owner/network process. Explain that investigation can take up to 90 days and provisional credit is still due within 10 business days when required. For a cash discrepancy whose **disputed amount exceeds $200**, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be returned within 10 business days, may be required to avoid denial, and false signing is a federal offense.

## 6. Determine provisional credit without overpromising

Set `provisional_credit_eligible` to true only when all are true:

1. reporting was timely (within 60 days of the statement date);
2. category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the checking account is OPEN and has no holds or restrictions.

Set it false if eligibility is disproved or one of these exclusions applies: ineligible category, a non-fraud customer has not contacted the merchant, PIN was voluntarily shared (`yes_shared`), or the account is under 30 days old and the case is card-not-present. If a required fact is unknown, obtain it rather than claiming eligibility.

For a qualifying case, provisional credit is the full disputed amount, reduced only by the applicable late-report liability offset. It is due within 10 business days after filing, or 20 business days for accounts opened less than 30 days ago. With provisional credit, the usual investigation period is 45 business days, extended to 90 days for international transactions, POS transactions outside the US, or new accounts. Explain that an adverse outcome can reverse credit after at least 3 business days’ written notice and supporting documentation may be requested.

## 7. File and perform the card action

Build the filing arguments exactly with the recorded values:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

The metadata `card_action` for each filing is fixed by category:

| Category | Filing card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other supported categories | `keep_active` |

After all desired disputes for a particular card are filed, perform just one actual action for that card: the most severe action among that card’s filings (`close_and_reissue` > `freeze_pending_investigation` > `keep_active`). Do not overwrite the individual filing metadata to make it match the aggregate action.

Before freezing, recheck verified ownership and that the card is `ACTIVE`; explain new and recurring charges will decline while pending transactions can still settle. Before closing/reissuing, confirm ownership, `ACTIVE` or `PENDING` status, and no pending transactions/refunds unless the customer provides the required written refund acknowledgement. The 14-day age rule is bypassed for fraud-suspected closure. Close with the applicable reason (normally `fraud_suspected` for fraud categories), explain closure is permanent and recurring payments must be updated, and complete replacement through the supported process. If a required card-action prerequisite fails, do not perform the action; preserve the filed dispute and explain/escalate as appropriate.

## Planner helper

`scripts/dispute_planner.py` performs deterministic checks for one prepared case. It reads one JSON object from stdin and emits one JSON object to stdout. It does not call bank tools or file anything.

Input schema (all IDs and facts must come from runtime lookups):

```json
{
  "now_date": "MM/DD/YYYY",
  "verified": true,
  "account": {"account_id": "...", "account_type": "checking", "account_class": "Entry Tier", "status": "OPEN", "date_opened": "MM/DD/YYYY", "has_holds_or_restrictions": false},
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "user_id": "...",
  "transaction": {"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -10.0, "type": "debit_card_purchase", "status": "posted"},
  "existing_disputes": [{"account_id": "...", "transaction_id": "...", "status": "OPEN"}],
  "case": {"category": "duplicate_charge", "transaction_type": "signature_purchase", "discovery_date": "MM/DD/YYYY", "disputed_amount": 10.0, "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "timely_reported_within_60_statement_days": true, "duplicate_candidates": []}
}
```

The output identifies hard filing blockers, missing facts, provisional-credit result/reasons, mandatory customer notices, the per-filing `card_action`, and `filing_arguments` only when the filing is ready. `timely_reported_within_60_statement_days` must be explicitly supplied as `true` or `false`; do not substitute transaction age for statement-based timeliness. Inspect output before execution and complete any ATM and aggregate-card-action steps described above.
