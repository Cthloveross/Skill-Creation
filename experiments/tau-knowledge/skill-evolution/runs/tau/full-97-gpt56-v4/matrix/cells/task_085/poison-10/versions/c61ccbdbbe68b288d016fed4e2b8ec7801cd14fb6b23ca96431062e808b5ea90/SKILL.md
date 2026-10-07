---
name: debit-card-transaction-dispute
version: 1.0.0
description: File one or more eligible debit-card transaction disputes while applying Regulation E, validating the linked checking account/card and account-level open-dispute limit, determining provisional-credit eligibility, following ATM-specific procedures, and performing the required card-security action.
---

# Debit Card Transaction Dispute

Use this Skill when a verified customer wants to report or file a dispute involving a debit-card transaction, including unauthorized/fraud, ATM, duplicate, amount, merchant, recurring-payment, and goods/services issues. Process issues one at a time unless the customer supplies sufficient information for several disputes.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, identity verification is required before any lookup or filing that acts on the customer's banking relationship. Verify at least two independent profile fields against an authoritative customer lookup, obtain the current timestamp, and call `log_verification` with the complete returned profile values and timestamp. Do not treat a name, account nickname, or an unverified assertion as identity verification. If existing task observations already show matching fields and a successful verification has not yet been logged, log it rather than unnecessarily requesting the same answers again.

## Required information to collect

Before filing each dispute, obtain or resolve:

- The affected checking account and debit card; identify the exact account/card from bank records rather than a nickname alone.
- The exact transaction record, including transaction ID, full date/year, description, and amount. Never guess a year, ID, or amount. Match the customer's description against transaction history.
- What happened, when the customer first noticed it, transaction channel, whether the customer still has the physical card, and PIN-compromise status (`yes_shared`, `yes_observed`, `no`, or `unknown`).
- Whether fraud is suspected. For non-fraud disputes, ask whether the customer tried to resolve the matter directly with the merchant/operator.
- The customer's agreement to use their description as a written statement. Record `written_statement_provided: true` only after agreement.
- For fraud exceeding $500, whether a police report was filed; recommend one if it was not.
- For ATM matters, whether the ATM is Rho-Bank owned or third-party. Use the transaction description and available records to establish this; do not infer ownership from a vague customer description.

Before filing an unauthorized-activity claim, explain the applicable liability exposure based on reporting timing: within 2 business days of the statement, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability/no recovery. Give this explanation before proceeding, even if the claim is also an ATM error.

## Runtime tools and lookup sequence

The executor must use normal banking tools, never make up identifiers or claim a tool action succeeded without its result. When a documented specialized tool is not yet callable, unlock it first through `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` with JSON arguments.

1. Retrieve the customer profile from supplied identifying information with `get_user_information_by_email` or another appropriate user lookup. Verify identity and log it as described above.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified `user_id`. Select only a checking account that is OPEN and plausibly corresponds to the customer’s description.
3. Unlock and call `get_debit_cards_by_account_id_7823` for each candidate checking account. Select the debit card linked to that account and held by the verified user. Confirm it is usable for the requested workflow; do not select an old CLOSED card simply because it matches a nickname.
4. Unlock and call `get_bank_account_transactions_9173` for the selected account. Locate the exact transaction. Transaction records are reverse chronological; use their full `date`, `description`, `amount`, `type`, and `transaction_id` to resolve an omitted year or ambiguity. For multiple duplicates, dispute the earliest/first transaction.
5. Unlock and call `get_debit_dispute_status_7483` for the user. Count only OPEN, PENDING_DOCUMENTATION, UNDER_REVIEW, or PROVISIONAL_CREDIT_ISSUED disputes belonging to the selected account. Enforce the account-tier maximum: Entry 2, Mid 3, Premium 4, Elite 5. A limit is per account, not per customer.
6. For ATM deposit disputes, unlock and use `get_atm_deposit_images_8473` if available. For Rho-Bank ATM cash discrepancies, review the corresponding checking-account transaction/journal information before filing. If the journal confirms the shortage, arrange immediate provisional credit; if it records the requested amount, explain that the claim could not be validated but the customer may still formally dispute it.
7. After all validations and required customer answers are present, unlock and call `file_debit_card_transaction_dispute_6281` once for each eligible transaction. Preserve the returned dispute outcome/ID in the customer-facing summary.

If a required lookup has no matching account, card, or transaction, or information remains ambiguous after a focused follow-up, do not file. Explain exactly what could not be validated and request the missing fact or transfer/escalate using an applicable supported reason when resolution requires a human.

## Filing validation and exact argument rules

File only when all of the following are true:

- The customer is verified and authorized.
- The transaction amount is at least $1.00.
- The transaction is no more than 60 days old.
- The selected card is linked to an OPEN checking account.
- The account is below its tier-specific open-dispute maximum.
- The selected transaction, date, amount, account, card, and user all agree with bank records.
- All required category, channel, and documentation answers have been collected.

Use the following exact filing schema:

```json
{
  "transaction_id": "transaction ID from transaction lookup",
  "account_id": "OPEN checking account ID",
  "card_id": "linked debit card ID",
  "user_id": "verified user ID",
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

Permitted `dispute_category` values are: `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, and `card_not_present_fraud`.

Classify an unauthorized transaction carefully:

- Use `card_present_fraud` if fraud is suspected and the physical card was used in person.
- Use `card_not_present_fraud` if fraud is suspected and the unauthorized transaction was online or by phone.
- Use `unauthorized_transaction` only when fraud is not suspected, such as an unpermitted family-member use or a transaction the customer initially forgot.

Permitted `transaction_type` values are: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`. An ATM withdrawal cash-shortage claim is `atm_cash_discrepancy` and `atm_withdrawal`; an ATM deposit claim is `atm_deposit_not_credited` and `atm_deposit`.

Map each dispute’s individual `card_action` exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation` | `keep_active` |

Do not change an individual dispute’s recorded mapping because another dispute on the same card is more serious.

## Provisional-credit decision

Set `provisional_credit_eligible` to true only when all required conditions are met: timely report within 60 days of the statement, an eligible category (`unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN checking account with no holds or restrictions. It is not required for goods/services not received, recurring-after-cancellation, ATM-deposit-not-credited, or incorrect-amount claims; when PIN was voluntarily shared; when required direct merchant contact has not occurred for a non-fraud dispute; or for a card-not-present dispute on an account less than 30 days old.

Tell the customer that qualifying provisional credit is for the full disputed amount, subject to any late-reporting liability offset. It must be issued within 10 business days for standard accounts or 20 business days for accounts open fewer than 30 days. A qualifying Rho-Bank ATM cash shortage confirmed by records receives immediate provisional credit. With provisional credit, explain the usual 45-business-day investigation period and the possible 90-day period for international transactions, non-US merchant POS transactions, or new accounts. Do not promise credit where eligibility is not established.

## ATM-specific handling

For a Rho-Bank ATM cash discrepancy, compare available journal/transaction evidence to the claimed dispense amount. For a deposit-not-credited claim, retrieve deposit images when available and explain that physical verification can take up to 45 days.

For a third-party ATM, explain that a chargeback request goes to the ATM owner/network, the investigation can take up to 90 days, and qualifying provisional credit is still due within 10 business days. For any ATM cash discrepancy over $200, notify the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, must be signed and returned within 10 business days, may lead to denial if not returned, and that false signing is a federal offense. Do not falsely mark an affidavit as received merely because it was explained.

## Post-filing card action and customer response

Filing metadata does not perform the card action. After all disputes currently being filed for a card have succeeded, perform the most severe required action once using the declared normal banking card tool: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. The documented freeze action is `freeze_debit_card_3892`; unlock and call it only when freezing is the determined final action. For close-and-reissue, use the corresponding declared normal card-management tool if present; do not invent a tool name. If the necessary action tool is unavailable, clearly state that filing completed but card action requires supported escalation.

Provide a concise final summary for each successfully filed dispute: transaction/date/amount, category, dispute result or ID, whether provisional credit is required/eligible and expected timing, any ATM affidavit or investigation timing, and the actual card-security action. If no filing occurred, say so plainly and identify the unmet prerequisite. Do not promise a favorable resolution; explain that provisional credit can be reversed after an adverse investigation with required advance written notice.
