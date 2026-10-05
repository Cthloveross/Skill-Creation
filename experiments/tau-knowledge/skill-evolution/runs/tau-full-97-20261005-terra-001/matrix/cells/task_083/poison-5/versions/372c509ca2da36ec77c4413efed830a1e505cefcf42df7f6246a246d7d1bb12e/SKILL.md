---
name: debit-card-dispute-filing
description: Verify, plan, and execute eligible debit-card transaction disputes for ATM errors, duplicate postings, merchant issues, family-use unauthorized activity, and suspected fraud. Use this skill when live account, card, transaction, dispute-history, provisional-credit, and required card-security actions must be checked before filing.
---

# Debit Card Dispute Filing

## Safety and scope

Use this workflow only for debit-card transactions associated with checking accounts. Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A script plan is advisory. It never files a dispute, provides credit, freezes a card, closes a card, or transfers the customer. Recheck live records and the tool result before each action. Do not invent transaction IDs, discovery dates, statement dates, ATM ownership, card possession, PIN facts, merchant-contact facts, or a filing result.

A missing exact discovery date is a filing blocker because the filing tool requires it. Merchant contact is not a filing blocker: for non-fraud categories, record the actual `contacted_merchant` Boolean even when it is `false`.

## Required live lookup sequence

1. Identify the customer and verify at least two profile fields against the customer record (date of birth, address, email, or phone).
2. Get the current time and successfully create the audit record with `log_verification`, supplying the complete verified profile and timestamp.
3. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. For every affected account, confirm it is a checking account in `OPEN` status; record account class/tier, opening date, and any holds or restrictions.
4. Retrieve each affected account's cards with `get_debit_cards_by_account_id_7823(account_id)`. Match the stated last four digits to one customer-owned card and retain its current status and ID.
5. Retrieve each affected account's transactions with `get_bank_account_transactions_9173(account_id)`. Match each claim to a live record by account, date, description, amount, and type. Preserve the returned ordering: transaction history is reverse chronological.
6. Retrieve `get_debit_dispute_status_7483(user_id)`. Check for a prior dispute on the transaction and count unresolved disputes per account.
7. Gather all remaining facts: loss amount, transaction date, discovery date, transaction type, physical-card possession, PIN status, merchant contact, written-statement consent, and ATM ownership where applicable.
8. Run `scripts/plan_debit_disputes.py` on normalized live data. Resolve every `blocking_reasons` item before filing. A `notice` is a required communication or operational follow-up, not automatically a filing block.

If a documented bank tool is discoverable rather than directly exposed, unlock it with `unlock_discoverable_agent_tool` and invoke it through `call_discoverable_agent_tool`. This includes `file_debit_card_transaction_dispute_6281` and card-action tools when the runtime exposes them that way.

## Filing eligibility

For every claim, confirm all of the following:

- Verification was successfully logged.
- The card belongs to the verified customer and is linked to the selected `OPEN` checking account.
- The disputed amount is at least $1.00 and no more than the absolute posted transaction amount.
- The transaction is no more than 60 days old at filing.
- The account remains below its unresolved-dispute limit: Entry 2, Mid 3, Premium 4, Elite 5.
- No dispute already exists for the selected transaction.
- An ATM claim identifies the ATM as `rho_bank` or `third_party`.

For duplicate postings, file exactly one dispute against the earliest matching transaction. Since retrieved history is reverse chronological, select the oldest date; when equally dated duplicate records have no time value, select the later-listed matching record from that returned history. Preserve the source transaction ordering in planner input rather than reordering duplicate candidates by identifier.

## Classify and populate the filing

Use exactly one supported category:

- `unauthorized_transaction` for activity not authorized by the customer when fraud is not suspected, such as unpermitted trusted-family use.
- `card_present_fraud` for suspected fraud using the physical card.
- `card_not_present_fraud` for suspected online or phone fraud.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for the matching error.

Use the actual loss, not automatically the full posting. For example, where a $250 withdrawal dispensed $100, dispute $150.

Use the actual transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. PIN use is `pin_purchase`; signing is `signature_purchase`.

Every tool call must supply these fields exactly:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

Use `yes_shared`, `yes_observed`, `no`, or `unknown` for `pin_compromised`. For suspected-fraud claims exceeding $500, ask whether a police report was filed and recommend one if it was not. Accurately provide the Boolean in every filing.

## Regulation E notice and provisional credit

Before discussing or filing an unauthorized-activity claim (`unauthorized_transaction`, `card_present_fraud`, or `card_not_present_fraud`), clearly disclose the applicable Regulation E liability exposure:

- report within two business days: maximum liability $50;
- report within 60 days of the statement: maximum liability $500;
- report after 60 days: potentially unlimited liability and possible inability to recover funds.

When live dates establish timely reporting within two business days, communicate the $50 maximum before filing. When the customer timely reports an activity in the current conversation and the available dates support the applicable timely tier, record that timing explicitly in planner input; do not withhold an otherwise complete claim solely to demand an unavailable statement date. If timing truly cannot be determined, explain all three tiers and obtain or document an authoritative determination without inventing dates.

Set `provisional_credit_eligible` to `true` only if all required conditions are met: timely reporting within 60 days of the statement, a qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN account without holds or restrictions. Timely ATM cash discrepancies with a written statement and an eligible open account qualify even when the ATM is third party.

Set it to `false` when required credit does not apply, including a nonqualifying category, voluntary PIN sharing, no prior merchant contact for a merchant dispute, or card-not-present fraud on an account open fewer than 30 days. Lack of merchant contact does not prevent filing. Required credit is for the full disputed amount, subject to any applicable liability offset, and is normally due within 10 business days (20 for a new account). Explain that adverse findings can reverse provisional credit with at least three business days' written notice.

## ATM procedures

For a Rho-Bank ATM cash discrepancy, review the relevant transaction and ATM journal. A confirmed discrepancy receives immediate provisional credit; a journal showing correct cash does not prevent formal filing. For a Rho-Bank ATM deposit issue, retrieve and compare deposit images.

For a third-party ATM cash discrepancy, file the dispute and submit a chargeback request to the ATM owner/network. Explain that investigation may take up to 90 days. Require and describe the EFT Error Resolution Affidavit only if the disputed shortage exceeds $200: it is emailed to the registered address, due within 10 business days, non-return may cause denial, and false signing is a federal offense. Do not request an affidavit at $200 or below.

## Filing, security action, and transfer

1. Deliver the Regulation E notice before each applicable unauthorized-activity filing.
2. File each complete, eligible claim once using `file_debit_card_transaction_dispute_6281` and the validated arguments.
3. Leave incomplete claims unfiled. Explain the precise missing fact and request it. In particular, request a specific discovery date before filing a non-receipt claim without one.
4. After successful filing results only, perform the actual card action. Preserve each filing's own `card_action` metadata:

| Category | Filing action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| ATM, duplicate, incorrect-amount, non-receipt, recurring categories | `keep_active` |

For multiple successful disputes on one card, act once using the most severe action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Before freezing, confirm verified ownership and current `ACTIVE` status. Tell the customer that new and recurring transactions will decline, already-authorized pending items may still post, and the card can later be unfrozen. Call `freeze_debit_card_3892(card_id)` once and confirm success. Do not freeze a card solely for a keep-active claim. For a close-and-reissue result, use the separate card-closing workflow and its prerequisites.

If the customer explicitly requests a human, including `###TRANSFER###`, promptly call `transfer_to_human_agents`. Use `customer_requests_human_no_specific_reason` unless a more specific supported reason clearly applies. Summarize completed filings/actions and any claim awaiting information.

## Planner interface

Run:

```text
python3 scripts/plan_debit_disputes.py < normalized_input.json
```

The script reads one JSON object from stdin and emits one JSON object on stdout. It makes no banking calls.

Top-level input fields: `as_of` (`YYYY-MM-DD` or `MM/DD/YYYY`), `identity_verified`, `user_id`, `accounts`, `cards`, `transactions`, `existing_disputes`, and `claims`.

Accounts require `account_id`, `account_type`, `account_class`, and `status`; include `date_opened`, `has_holds`, and `has_restrictions` when available. Cards require `card_id`, `account_id`, `user_id`, `card_number_last_4`, and `status`. Transactions require `transaction_id`, `account_id`, `date`, `description`, `amount`, and `status`, and must remain in the source history order.

Each claim requires `account_id`, either `card_id` or `card_last4`, `transaction_id` or `duplicate_transaction_ids` in source history order, `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, and `written_statement_provided`. ATM claims also require `atm_owner`. For a timely claim, explicitly supply `reporting_timing` as `within_2_business_days` or `within_60_days`; use `after_60_days` when applicable. Also provide `fraud_suspected`, `police_report_filed`, and `international_or_non_us_pos` when applicable.

Validate before execution that `blocking_reasons` is empty, exactly one duplicate transaction was selected, each filing field matches live records, and every required customer notice has been delivered.