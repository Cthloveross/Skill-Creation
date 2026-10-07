---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, and file one or more debit-card transaction disputes under Regulation E. Use for unauthorized/fraud, ATM, duplicate, amount, merchant, and recurring debit-card claims requiring account, card, transaction, dispute-limit, provisional-credit, and card-action checks.
---

# Debit-card dispute intake and filing

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required intake and verification

1. Identify the customer, then verify identity by confirming **two of four** profile fields (date of birth, email, phone number, address). Retrieve the profile using an available user lookup, obtain the confirmations from the customer rather than treating lookup output as confirmation, get the current time, and call `log_verification` with all returned profile fields and the verification timestamp. Do not file, freeze, close, or reissue anything before this succeeds.
2. Tell the customer their Regulation E exposure before proceeding with an unauthorized/fraud claim: reported within 2 business days of the statement has maximum liability of $50; within 60 days has maximum liability of $500; after 60 days liability may be unlimited and funds may not be recoverable. Record the statement/reporting timing needed to support this conclusion.
3. Work through multiple claims one at a time, while retaining the information for all claims so the final physical-card action can be selected across the batch. Obtain, for every transaction:
   - merchant/ATM, date, amount, what happened, discovery date, and card last four digits;
   - whether fraud is suspected and, if so, whether the use was physical/in-store or online/phone; ATM and recurring circumstances where applicable;
   - transaction type, card possession, PIN-compromise value, merchant-contact result for non-fraud claims, police-report status for suspected fraud over $500, and consent for the conversation to be a written statement.
4. Ask exactly as needed to establish the required fields: “Do you still have your physical debit card in your possession?”; “Do you believe your PIN may have been compromised?”; “Have you attempted to resolve this directly with the merchant?”; and “Are you willing to provide a written statement describing what happened? We can use this conversation as your written statement if you agree.” Set `written_statement_provided` true only on agreement. For non-fraud merchant disputes, advise the customer to contact the merchant; record their answer. For suspected fraud over $500, ask about a police report and recommend one if none exists.

## Retrieve and validate bank records

1. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Select the claimed **OPEN checking** account. Its `account_class` supplies the checking tier and its `date_opened` supports new-account review.
2. Retrieve cards for that account with `get_debit_cards_by_account_id_7823`. Match the claimed last four digits, `card_id`, `account_id`, and `user_id`; confirm a usable card status before any later card action.
3. Retrieve account transactions using `get_bank_account_transactions_9173(account_id)`. Match the actual debit transaction ID, exact date and amount, and relevant merchant/ATM description. Transactions are reverse chronological. For a duplicate claim, identify all same-charge candidates and dispute the **earliest (first)** transaction, not a later duplicate.
4. Retrieve `get_debit_dispute_status_7483(user_id)` and count only OPEN disputes by the selected account. The maximum open-dispute count is per account: Entry Tier 2, Mid Tier 3, Premium Tier 4, Elite Tier 5. Include disputes accepted earlier in the same batch when checking the limit.
5. Do not file unless the transaction is at least $1.00, no more than 60 days old, the checking account is OPEN, the card is linked to it, and the account's open-dispute limit permits the filing. For an ATM claim, determine whether the ATM is a Rho-Bank ATM or a third-party ATM and follow the applicable process before filing.

Use `scripts/validate_dispute_batch.py` after gathering the facts to consistently check dates, per-account limits, category/type vocabularies, mappings, and provisional-credit conditions. The script validates supplied facts; it does not retrieve records, establish identity, make banking calls, or authorize filing.

## Classification and filing fields

Use only these dispute categories:

- `unauthorized_transaction` only when the transaction was not authorized **and fraud is not suspected**.
- `card_present_fraud` for suspected fraud involving physical/in-store card use.
- `card_not_present_fraud` for suspected fraud involving online/phone use.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for their literal circumstances.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Use exactly one PIN value: `yes_shared`, `yes_observed`, `no`, or `unknown`.

For each validated claim, call `file_debit_card_transaction_dispute_6281` with every required argument: `transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), `disputed_amount` (float), `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`. Never manufacture an ID, date, amount, or missing customer answer. Explain and resolve missing data, failed eligibility, or ambiguous transaction matching before filing.

Record the per-dispute `card_action` exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation` | `keep_active` |

The filed field is metadata only. After all filings for a card, perform the one most-severe actual action across that card's successfully filed claims: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Use only a normal banking tool actually available in the runtime. When freezing is indicated and the documented `freeze_debit_card_3892` tool is available, use it once after the batch; do not invent a close/reissue tool or claim an action completed without a successful tool result.

## Provisional-credit determination and completion

Set `provisional_credit_eligible` true only when all required conditions are evidenced: timely report within 60 days of the statement, category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`; written statement is provided; and the checking account is OPEN with no holds or restrictions. It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when the customer did not contact the merchant for a non-fraud dispute; when PIN was voluntarily shared; or for a card-not-present claim on an account under 30 days old. Document any missing account hold/restriction information as unresolved rather than assuming eligibility.

Required provisional credit is for the full disputed amount subject to any supported liability offset. It must issue within 10 business days for standard accounts or 20 business days for accounts open under 30 days. With provisional credit, investigation is generally 45 business days, extended to 90 for international, qualifying non-US merchant POS, or new-account transactions. Tell the customer that an adverse investigation can reverse provisional credit with at least three business days’ written notice and that they may request supporting documentation.

Confirm each successful filing, claim amount, category, expected timeline, and any actual card action. If checking an existing claim, use `get_debit_dispute_status_7483`; escalate apparent timeline overruns rather than silently treating them as resolved.

## Validator invocation

The validator receives JSON on stdin and writes one JSON object to stdout. Example (replace every value with retrieved/current facts):

```json
{
  "reference_date": "MM/DD/YYYY",
  "tier_by_account": {"ACCOUNT_ID": "Entry Tier"},
  "open_disputes_by_account": {"ACCOUNT_ID": 0},
  "disputes": [
    {
      "account_id": "ACCOUNT_ID",
      "transaction_id": "TRANSACTION_ID",
      "card_id": "CARD_ID",
      "user_id": "USER_ID",
      "transaction_amount": 10.0,
      "disputed_amount": 10.0,
      "transaction_date": "MM/DD/YYYY",
      "discovery_date": "MM/DD/YYYY",
      "category": "duplicate_charge",
      "transaction_type": "pin_purchase",
      "card_in_possession": true,
      "pin_compromised": "no",
      "contacted_merchant": true,
      "police_report_filed": false,
      "written_statement_provided": true,
      "reported_within_60_days_of_statement": true,
      "account_open": true,
      "account_has_holds_or_restrictions": false,
      "account_age_days": 90,
      "card_linked_to_open_checking": true,
      "transaction_confirmed": true,
      "is_earliest_duplicate": true
    }
  ]
}
```

Run as `python3 scripts/validate_dispute_batch.py < input.json`. The output contains per-claim errors/warnings, fileability, required card-action metadata, provisional-credit determination, and the actual action recommendation by card. It is a review aid; the executor must still perform the required live lookups and banking calls.
