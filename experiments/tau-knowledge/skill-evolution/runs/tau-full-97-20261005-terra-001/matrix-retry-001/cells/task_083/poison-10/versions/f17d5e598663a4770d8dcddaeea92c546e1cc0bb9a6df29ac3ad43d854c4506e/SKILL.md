---
name: debit-card-dispute-intake-and-filing
description: Verify a customer, locate debit-card transactions, collect the facts required for each dispute, determine Regulation E and ATM handling, and file eligible debit-card disputes one transaction at a time. Use for ATM cash errors, missing goods or services, duplicate charges, incorrect amounts, recurring charges, fraud, and non-fraud unauthorized use.
---

# Debit Card Dispute Intake and Filing

Use current runtime lookup results and customer statements. Never reuse a user ID, account ID, card ID, transaction ID, tier, or filing result from another conversation.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before a filing or card action, complete the runtime identity-verification procedure. A lookup, name, or email alone is not verification. Confirm two appropriate identity fields from the customer against the user record, create the required `log_verification` audit record, and confirm that the customer owns the affected card/account.

## Interaction rules

1. For an unauthorized-activity matter, explain the Regulation E reporting timing before proceeding: within 2 business days may limit liability to $50; within 60 days may limit it to $500; after 60 days may result in unlimited liability and no recovery.
2. Respect a request to address one transaction at a time. Do not require facts for every reported transaction before filing the current fully supported one.
3. Once lookup, eligibility, and required facts for the current transaction are complete, file it promptly. Do not defer it for unrelated intake questions or give a generic inability response without a specific blocker.
4. Confirm a successful filing only after the filing tool returns successfully. Then collect only the missing facts for the next transaction.
5. For duplicates, identify and dispute the earliest duplicate transaction first.

## Lookup and preflight

Use ordinary banking tools directly when available. For a discoverable banking tool, unlock it before calling it through `call_discoverable_agent_tool` with JSON arguments.

For the account and card involved in each current matter:

1. Call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the linked checking account and retain its ID, class/tier, status, opening date, balance, and restrictions/holds.
2. Call `get_debit_cards_by_account_id_7823(account_id)`. Match the relevant active card, including its last four digits when provided. Confirm the returned card account and user IDs match the selected account and verified customer.
3. Call `get_bank_account_transactions_9173(account_id)` for each potentially relevant account. Match the exact transaction by date, amount, and description, and retain its transaction ID and date. Inspect all account-history responses, not only the final response, when the customer has several accounts.
4. Call `get_debit_dispute_status_7483(user_id)`. Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes per account. Maximum open disputes are Entry 2, Mid 3, Premium 4, and Elite 5.

Before filing, establish:

- verified identity, authority, and account/card ownership;
- exact transaction record, transaction date, and amount, with amount at least $1.00 and no more than 60 days old;
- an OPEN linked checking account and the matched customer-owned card;
- available per-account dispute capacity, including filings already made in this interaction;
- discovery date, card-possession status, PIN status, required merchant-contact status, and written-statement agreement;
- ATM ownership for ATM matters; and
- police-report status for fraud above $500.

Resolve a missing, conflicting, unmatched, or ineligible fact before filing that transaction. Missing facts for another transaction are not a blocker for the current eligible transaction.

## Intake facts

For the current transaction, collect the customer’s description, transaction date and amount, merchant or ATM details, discovery date, whether they retain the physical card, and one PIN value: `yes_shared`, `yes_observed`, `no`, or `unknown`.

Also collect:

- whether the customer contacted the merchant for non-fraud merchant disputes;
- whether the customer agrees that this conversation can serve as their written statement;
- whether a police report was filed for fraud over $500, and recommend one when it was not; and
- whether an ATM is Rho-Bank owned or third-party.

An explicit agreement to use the conversation as a written statement sets `written_statement_provided` to `true`. For a confirmed online/card-not-present order, use `online_purchase`; PIN is not used in that transaction, so use `pin_compromised: "no"` only if the customer confirms no PIN compromise.

## Classification and filing metadata

Select exactly one category:

- `unauthorized_transaction` for unauthorized use when fraud is **not** suspected, including a trusted person using the card without permission;
- `card_present_fraud` for suspected fraudulent physical/in-store use;
- `card_not_present_fraud` for suspected fraudulent online or phone use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when the facts match.

Select exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Use this filing `card_action` mapping:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation` | `keep_active` |

A missing-goods case remains `goods_services_not_received` when the customer says the goods did not arrive and a merchant contact attempt failed. A merchant refusing a refund does not by itself make the case fraud.

## ATM-specific procedure

For a Rho-Bank ATM cash discrepancy, review the corresponding account/journal information. If the discrepancy is confirmed, credit is immediate. If the journal shows the charged amount was dispensed, explain that the claim is not validated but a formal dispute may still be filed. For a Rho-Bank ATM deposit issue, obtain and compare deposit images through `get_atm_deposit_images_8473`.

For a third-party ATM, submit the dispute/chargeback and explain that the investigation can extend to 90 days. A qualifying provisional credit remains due within 10 business days.

### Affidavit threshold

For an ATM cash discrepancy, calculate the **disputed shortage** first:

`disputed shortage = amount charged or debited − cash actually dispensed`

Apply the affidavit threshold to that shortage, never to the gross ATM withdrawal/request amount. Only if the third-party ATM cash-discrepancy **disputed amount exceeds $200** must the customer be told that an Electronic Fund Transfer Error Resolution Affidavit will be sent to their registered email, must be returned within 10 business days, may lead to denial if not returned, and is subject to federal penalties if false.

When the shortage is $200 or less, do **not** request, require, promise, or say that an affidavit will be emailed or must be returned. File the supported claim without that disclosure.

## Provisional-credit decision

Set `provisional_credit_eligible` to true only when all applicable requirements are established:

- timely reporting within 60 days of the statement date;
- category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
- the customer provided a written statement;
- the checking account is OPEN without holds or restrictions;
- required merchant-resolution information is documented; and
- the PIN was not voluntarily shared.

Do not claim eligibility when timing or account standing is unknown. Set it false for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, and `incorrect_amount`; these are not required provisional-credit categories. Also set it false for a card-not-present transaction on an account opened fewer than 30 days ago and where the PIN was voluntarily shared. Qualifying credit is generally due within 10 business days, or 20 business days for a new account, and is for the disputed amount subject to an applicable late-reporting liability offset.

## Filing and actual card actions

When the current case is ready, call `file_debit_card_transaction_dispute_6281` once with:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

Use MM/DD/YYYY dates and a numeric disputed amount. The filing `card_action` is metadata and does not change the card state.

For multiple filings on the same card, preserve each filing’s mapped action. After all supported filings for that card are complete, perform only the most severe actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

- Before `freeze_debit_card_3892`, recheck verified ownership and ACTIVE status. Explain that new and recurring transactions will decline, while already-authorized pending transactions can still settle.
- Before `close_debit_card_4721`, recheck ownership, eligible card status, pending transactions/refunds, and closure conditions. Fraud-suspected closure bypasses the minimum-card-age condition but not applicable safeguards.
- Order a replacement only after checking tier replacement limits, waiting periods, exact fees, available balance, and customer confirmation.
- If a separate freeze or closure safeguard is unmet, explain that precise blocker; do not treat it as a reason to abandon an otherwise eligible dispute filing.

## Deterministic planning helper

`scripts/plan_disputes.py` performs a local preflight only. It does not invoke banking tools, file disputes, or change cards. It reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "identity_verified": true,
  "user_id": "verified-user-id",
  "existing_disputes": [{"account_id": "...", "status": "OPEN"}],
  "disputes": [
    {
      "account": {"account_id": "...", "account_type": "checking", "account_class": "Premium", "status": "OPEN", "date_opened": "MM/DD/YYYY", "has_hold_or_restriction": false},
      "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
      "transaction": {"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -1.0},
      "dispute_category": "...",
      "discovery_date": "MM/DD/YYYY",
      "disputed_amount": 1.0,
      "transaction_type": "...",
      "card_in_possession": true,
      "pin_compromised": "no",
      "contacted_merchant": false,
      "police_report_filed": false,
      "written_statement_provided": true,
      "timely_reporting": true
    }
  ]
}
```

ATM cases additionally require `atm_owner` (`rho_bank` or `third_party`). A cash-discrepancy case may supply `charged_amount` and `cash_dispensed`; when supplied, the helper verifies that their difference equals `disputed_amount`. A third-party case over $200 additionally requires `affidavit_disclosure_given: true`.

Run it with current runtime data, then use `filing_args` only when `ready_to_file` is true. Treat `errors` as blockers, complete any required disclosure before filing, and recheck live lookup information immediately before the banking action.

```sh
python3 scripts/plan_disputes.py <<'JSON'
{"as_of_date":"<MM/DD/YYYY>","identity_verified":true,"user_id":"<user-id>","existing_disputes":[],"disputes":[<current-case-objects>]}
JSON
```
