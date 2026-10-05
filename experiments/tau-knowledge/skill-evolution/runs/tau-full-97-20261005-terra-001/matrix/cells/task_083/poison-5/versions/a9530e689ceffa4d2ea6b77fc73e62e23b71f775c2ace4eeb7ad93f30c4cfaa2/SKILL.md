---
name: debit-card-dispute-filing
description: Prepare and execute eligible debit-card transaction disputes, including ATM errors, duplicate charges, merchant claims, unauthorized family-use claims, and fraud claims. Use after identity verification to map live account, card, transaction, dispute-history, provisional-credit, and card-security requirements.
---

# Debit Card Dispute Filing

## Scope and safety controls

Use this workflow for debit-card transactions tied to checking accounts. Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A planner result is advisory only. It does not file, freeze, close, credit, or transfer anything. Compare every proposed ID, date, amount, and status to current live tool results immediately before the related action.

Do not invent missing transaction IDs, discovery dates, statement dates, ATM ownership, card facts, or merchant-contact facts. A claim with a missing discovery date cannot be filed because the filing tool requires that date.

## Live lookup and verification sequence

1. Identify the customer and verify at least two profile fields (date of birth, address, email, or phone) against the customer record.
2. Obtain the current time and successfully call `log_verification` with the complete verified profile and timestamp.
3. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. For each affected account, confirm it is a checking account, `OPEN`, and identify its class/tier, opening date, holds, and restrictions.
4. Retrieve cards for each affected account with `get_debit_cards_by_account_id_7823(account_id)`. Match the stated last four digits to exactly one customer-owned card and retain its `card_id` and live status.
5. Retrieve transactions for every affected account with `get_bank_account_transactions_9173(account_id)`. Match the claim to a live transaction by account, date, description, amount, and type. Never derive an ID from the narrative.
6. Retrieve `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes per affected account and ensure the selected transaction has not already been disputed.
7. Gather missing filing facts. Required facts include the actual loss amount, transaction date, discovery date, category, transaction type, card possession, PIN-compromise value, merchant-contact value for non-fraud claims, written-statement answer, and ATM ownership for ATM claims.
8. Run `scripts/plan_debit_disputes.py` with normalized live data. Resolve every listed blocking item before filing. Treat a planner notice as a customer communication or operational follow-up, not automatically as a filing block.

If the filing tool is available through the discoverable-agent mechanism rather than directly, unlock `file_debit_card_transaction_dispute_6281` and call it through `call_discoverable_agent_tool`. Likewise unlock any documented retrieval tool before calling it when required by the runtime.

## Filing eligibility

For each individual claim, confirm:

- Identity verification was successfully logged.
- The card belongs to the verified user and is linked to the selected `OPEN` checking account.
- The disputed amount is at least $1.00 and no greater than the absolute posted transaction amount.
- The transaction is not more than 60 days old at filing.
- The account has fewer unresolved disputes than its per-account tier limit: Entry 2, Mid 3, Premium 4, Elite 5.
- No dispute already exists for that transaction.
- ATM claims identify the ATM as Rho-Bank or third party.

`contacted_merchant` is a required Boolean filing field for every non-fraud dispute, but a `false` value is **not** a pre-filing blocker. Record the customer’s actual answer. Do not delay an otherwise complete ATM, duplicate, or other non-fraud filing merely because the merchant was not contacted. Merchant non-contact can affect whether provisional credit is required.

When two records are the same duplicate purchase, file exactly one claim against the earliest matching transaction. Do not file both postings as separate duplicate claims.

## Claim classification and filing fields

Use one supported category:

- `unauthorized_transaction` only where fraud is not suspected, including unpermitted use by a trusted family member.
- `card_present_fraud` for suspected fraud using a physical card.
- `card_not_present_fraud` for suspected online or phone fraud.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for the corresponding error.

Use the actual customer loss, rather than automatically disputing the whole posted debit. For example, if an ATM withdrawal posts for $250 but dispenses $100, the cash-discrepancy amount is $150.

Select the actual transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Every filing must include these exact fields:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (`MM/DD/YYYY`), `discovery_date` (`MM/DD/YYYY`), `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised` (`yes_shared`, `yes_observed`, `no`, or `unknown`), `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

For suspected-fraud claims over $500, ask whether a police report was filed and recommend one if it was not. A missing police report is not itself a listed filing prohibition, but the required Boolean tool field must be accurate.

## Regulation E notice and provisional-credit treatment

Before discussing or filing an unauthorized-activity claim, clearly tell the customer the applicable liability exposure based on reporting timing:

- Reported within 2 business days: maximum liability of $50.
- Reported within 60 days of the statement: maximum liability of $500.
- Reported after 60 days: potentially unlimited liability and the customer may not recover funds.

When the live facts establish timely reporting within two business days, state the $50 maximum before filing; do not unnecessarily block the claim by demanding an unavailable statement date. If timing cannot be determined, explain the three tiers and obtain or document an authoritative timing determination without inventing a date.

Mark `provisional_credit_eligible` true only when all required conditions are satisfied: timely reporting within 60 days of the statement, a qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an open unrestricted account. Do not mark required provisional credit for excluded circumstances, including voluntary PIN sharing, a merchant dispute where required merchant contact did not occur, or a card-not-present fraud claim on an account less than 30 days old. Merchant-contact noncompliance does not disqualify filing.

For required credit, it is for the full disputed amount subject to the applicable liability offset and may not exceed the disputed amount. Explain the normal issuance deadline: 10 business days, or 20 business days for an account open under 30 days. A qualifying investigation is normally 45 business days and may be extended to 90 days for international, non-US merchant POS, or new-account cases. A later adverse finding can reverse credit after at least three business days’ written notice.

## ATM procedures

For a Rho-Bank ATM cash discrepancy, review the appropriate transaction and ATM journal record. If the discrepancy is confirmed, provisional credit is immediate; if the journal shows correct dispensing, explain that the claim cannot be validated while still allowing formal filing. For a Rho-Bank ATM deposit issue, retrieve deposit images and compare them to the claimed deposit.

For a third-party ATM cash discrepancy, file the claim and submit the needed chargeback request to the owner or network. Explain that investigation can take up to 90 days. Only when the **disputed shortage** exceeds $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be returned within 10 business days, may lead to denial if not returned, and is a federal offense if falsely signed. Do not require an affidavit at $200 or below.

## Filing and required card action

1. Deliver required Regulation E notices before the applicable unauthorized-activity filing.
2. File every independently complete and eligible claim once with `file_debit_card_transaction_dispute_6281` using its exact planned fields.
3. Leave incomplete claims unfiled, explain only the precise missing fact, and request it. In particular, request a specific discovery date for a non-receipt claim if none was supplied.
4. Only after confirming successful filing results, calculate the actual action for each card across all successful filings:

| Category | Filing `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| All ATM, duplicate, incorrect-amount, non-receipt, and recurring categories | `keep_active` |

Preserve each filing’s own action field. For actual action on a card, perform only the most severe successful-filing action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Before freezing, confirm the card is customer-owned and currently `ACTIVE`. Explain that new and recurring transactions will decline, already-authorized pending transactions may still post, and the card can be unfrozen later. Then call `freeze_debit_card_3892(card_id)` once and confirm success. Do not freeze a card merely because a keep-active claim was filed.

For a required close-and-reissue outcome, follow the separate card-closing workflow, including status, pending transaction/refund, ownership, and age checks. Do not assume a replacement was ordered.

## Human-transfer requests

If the customer explicitly requests a human agent, including a control response such as `###TRANSFER###`, promptly call `transfer_to_human_agents`. Use `customer_requests_human_no_specific_reason` unless a more specific supported reason clearly applies. Include a concise summary of completed filings/actions and any claim awaiting information. Do not ignore or merely offer a transfer after an explicit request.

## Planner script interface

Run:

```text
python3 scripts/plan_debit_disputes.py < normalized_input.json
```

The script reads one JSON object from stdin and emits one JSON object on stdout. It calls no banking tools.

Required top-level fields are `as_of` (`YYYY-MM-DD` or `MM/DD/YYYY`), `identity_verified`, `user_id`, `accounts`, `cards`, `transactions`, `existing_disputes`, and `claims`.

Accounts need `account_id`, `account_type`, `account_class`, and `status`; provide `date_opened`, `has_holds`, and `has_restrictions` whenever available. Cards need `card_id`, `account_id`, `user_id`, `card_number_last_4`, and `status`. Transactions need `transaction_id`, `account_id`, `date`, `description`, `amount`, and `status`.

Each claim needs `account_id`, either `card_id` or `card_last4`, a `transaction_id` (or ordered `duplicate_transaction_ids`), `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, and `written_statement_provided`. ATM claims also need `atm_owner` (`rho_bank` or `third_party`). Provide `reporting_timing` (`within_2_business_days`, `within_60_days`, or `after_60_days`) when known, plus `fraud_suspected`, `police_report_filed`, and `international_or_non_us_pos` where applicable.

Before executing a plan, validate that `blocking_reasons` is empty, `filing_arguments` is present, dates are formatted correctly, the selected duplicate is singular, and every planned field matches live records. Follow every returned notice and `post_filing` instruction.