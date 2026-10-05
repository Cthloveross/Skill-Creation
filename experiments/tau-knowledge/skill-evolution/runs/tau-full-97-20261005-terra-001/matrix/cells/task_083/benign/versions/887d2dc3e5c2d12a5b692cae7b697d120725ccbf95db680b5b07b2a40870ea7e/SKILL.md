---
name: debit-card-dispute-case-manager
description: Verify, qualify, file, and post-process one or more debit-card transaction disputes. Use for unauthorized, fraud, ATM, duplicate, amount, goods/services, and recurring debit-card disputes, including account-level open-dispute limits, Regulation E provisional-credit screening, and per-card action aggregation.
---

# Debit Card Dispute Case Manager

Use this Skill when a verified customer asks to dispute debit-card transactions. It supports batch cases across multiple accounts/cards without hardcoding customer, account, card, transaction, or date values.

## Safety and execution boundary

The Python helper only evaluates structured facts and produces proposed filing arguments. It does **not** call banking tools or make account/card changes. The execution agent must perform every retrieval, filing, card action, and customer communication with the normal banking tools.

Do not file a case with an unresolved blocker. A customer may provide information gradually; file independent eligible cases only after all required pre-filing checks for those cases pass, and leave the remaining cases pending.

## Required customer conversation

Before filing, explain the applicable Regulation E liability exposure for unauthorized activity:

- Reported within 2 business days: maximum liability $50.
- Reported within 60 days of the statement: maximum liability $500.
- Reported after 60 days: funds may not be recoverable.

Collect, confirm, and record for every proposed dispute:

- Transaction, transaction date, account/card, discovery date, and disputed amount. A partial amount is permitted only when it is no greater than the transaction debit amount.
- What happened and the correct category/transaction type.
- Whether fraud is suspected. For suspected fraud, determine whether it was card-present or online/phone/card-not-present.
- Whether the card is still in the customer's possession and the exact PIN-compromise state: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Merchant-contact result for merchant disputes. Merchant contact is required for non-fraud merchant disputes; do not substitute an unanswered question for contact. ATM cases do not require a merchant-contact attempt.
- Whether the customer agrees to a written statement (the conversation can be that statement).
- For fraud disputes over $500, whether a police report was filed. If not, recommend one, but retain the supplied boolean filing field.
- Timeliness relative to the statement for provisional-credit screening. Do not assume statement timeliness merely because the transaction date is recent.

For a duplicate group, identify every matching debit and file the **earliest** duplicate transaction first. If a merchant has not yet been contacted where required, ask the customer to contact the merchant and wait for the result before filing that case.

## Identity verification and retrieval workflow

1. Resolve the customer identity using the available profile lookup. Verify at least two of date of birth, email, phone, and address against the profile.
2. Obtain the current timestamp and call `log_verification` only after successful verification, supplying all fields required by that tool.
3. Unlock and use `get_all_user_accounts_by_user_id_3847`. Retain only the relevant OPEN checking accounts and identify their tiers/classes.
4. For each relevant account, unlock and use `get_debit_cards_by_account_id_7823`. Confirm the specified card belongs to the customer and is linked to that OPEN checking account.
5. Unlock and use `get_bank_account_transactions_9173` for each account. Match transaction ID, date, debit amount, description, and posted/pending state; never rely only on merchant wording supplied by the customer.
6. Unlock and use `get_debit_dispute_status_7483` for the user. Count active disputes per account, not per customer. Active statuses are `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`.
7. Apply account dispute limits: Entry 2, Mid 3, Premium 4, Elite 5. Determine the tier from returned account data. Known account-class mapping includes Light Blue, Light Green, and Green Fee-Free as Entry; Blue and Green checking as Mid; Evergreen as Premium; and Bluest as Elite. If the returned class cannot be mapped reliably, stop and obtain the tier rather than guessing.

Use `scripts/build_dispute_plan.py` after gathering the facts. It checks deterministic eligibility and emits exact `file_debit_card_transaction_dispute_6281` arguments for only ready cases.

## Filing rules

A filing requires all of the following:

- verified customer;
- known transaction belonging to the linked OPEN checking account;
- debit-card ownership matches the customer;
- dispute amount is at least $1.00;
- transaction is no more than 60 calendar days old at filing;
- the account remains within its tier's active-dispute limit after the proposed filing;
- required merchant contact, customer statement, and category-specific facts are known.

Use these exact dispute categories:

- `unauthorized_transaction` only when no fraud is suspected (for example, unauthorized use by a family member);
- `card_present_fraud` when suspected fraud used a physical card;
- `card_not_present_fraud` when suspected fraud was online or phone/card-not-present;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

For an ATM cash shortfall, set `disputed_amount` to the loss (requested amount minus cash actually received), not automatically to the withdrawal amount. Ensure that loss is positive and does not exceed the debit transaction amount.

For each ready case, unlock and call `file_debit_card_transaction_dispute_6281` with the helper's `filing_arguments`. Preserve each case's own mapped `card_action` in that filing:

| Category | Filing `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other supported categories | `keep_active` |

## Provisional-credit assessment and notices

Set `provisional_credit_eligible` true only when all required conditions are known to hold: timely reporting within 60 days of the statement; category is unauthorized, either fraud category, ATM cash discrepancy, or duplicate charge; written statement is provided; account is OPEN with no hold/restriction; and no exclusion applies.

Do not mark it required when the category is goods/services not received, recurring after cancellation, ATM deposit not credited, or incorrect amount; when required merchant contact did not occur; when the PIN was voluntarily shared; or for card-not-present on an account opened fewer than 30 days ago. Unknown statement timeliness or account restrictions means eligibility is not established; do not represent it as guaranteed.

Tell eligible customers that the full disputed amount, reduced by any applicable late-reporting liability, is the potential provisional-credit amount. Standard accounts have a 10-business-day deadline; accounts open fewer than 30 days have a 20-business-day deadline. With provisional credit, investigation is generally 45 business days, extending to 90 for international transactions, non-US merchant POS transactions, or new accounts.

## ATM-specific handling

Ask whether the ATM is Rho-Bank branded or third-party.

- For Rho-Bank cash discrepancy, review the account transaction/journal evidence. If the journal confirms the discrepancy, issue immediate provisional credit through the normal banking process; if it shows a correct dispense, explain that the claim cannot be validated but offer formal filing.
- For Rho-Bank deposit-not-credited cases, unlock and use `get_atm_deposit_images_8473`; physical verification can take up to 45 days.
- For third-party ATM cash discrepancy, explain that a chargeback is submitted to the operator/network, investigation can take up to 90 days, and provisional credit remains due within 10 business days where required.
- For an ATM cash-discrepancy **disputed amount** over $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be returned within 10 business days, may lead to denial if not returned, and false signing is a federal offense.

## Actual card action after filing

After filing the cases being processed, aggregate the actual action once per card: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. Do not alter the individual filing metadata while aggregating.

- `keep_active`: no card action is needed.
- `freeze_pending_investigation`: before calling `freeze_debit_card_3892`, ensure the card is ACTIVE and customer-owned. Explain that new and recurring transactions will decline, authorized pending transactions may still settle, and the card can later be unfrozen. Do not freeze an already frozen, pending, or closed card.
- `close_and_reissue`: follow the debit-card closure procedure using `close_debit_card_4721` with the appropriate fraud reason, then the replacement-card process. Confirm closure/replacement prerequisites and disclose applicable replacement fees before ordering. Fraud/lost/stolen closure handling supersedes a minimum-age restriction, but handle pending transactions as required by the closure process.

If action prerequisites prevent the indicated action, explain the specific limitation, retain the filed dispute, and escalate or follow the applicable card procedure rather than falsely confirming an action.

## Helper input/output

Run:

```sh
python3 scripts/build_dispute_plan.py < task_state.json
```

The input is one JSON object with:

- `current_date`: ISO `YYYY-MM-DD` or `MM/DD/YYYY` filing date;
- `user_id` and `customer_verified`;
- `accounts`: account objects with `account_id`, `account_type`, `status`, optional `tier`/`account_class`, optional `has_holds_or_restrictions`, and optional `date_opened`;
- `cards`: objects with `card_id`, `account_id`, `user_id`, and optional `status`;
- `open_disputes`: returned dispute objects;
- `cases`: objects containing `case_id`, `account_id`, `card_id`, a matched `transaction` (`transaction_id`, `date`, `amount`), category or `issue_kind`, `transaction_type`, `discovery_date`, `disputed_amount` (or ATM requested/cash values), `card_in_possession`, `pin_compromised`, `contacted_merchant` when applicable, `written_statement_provided`, and provisional-credit facts. Add `duplicate_candidates` for duplicate-charge cases.

The script emits JSON with `ready_filings`, `blocked_cases`, `notices`, `card_actions`, and `global_blockers`. Each `ready_filings[].filing_arguments` object is directly shaped for `file_debit_card_transaction_dispute_6281`. Validate that no blocked case is filed, every filing argument uses exact enum values, all required account/card/transaction matches were confirmed from tool output, and the actual per-card action is performed only after its associated filings succeed.
