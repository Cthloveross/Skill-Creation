---
name: debit-card-dispute-filing
description: Safely handle and file debit-card transaction disputes, including ATM cash/deposit issues, Regulation E verification and provisional-credit assessment, account/card/transaction validation, dispute-capacity checks, and required card actions. Use when a verified customer reports a debit-card transaction error, unauthorized activity, duplicate, incorrect amount, merchant issue, recurring charge, or ATM discrepancy.
---

# Debit Card Dispute Filing

Use this Skill to complete a debit-card dispute through the declared banking tools. Do not file from a customer description alone: validate the customer, account, card, transaction, timing, existing disputes, required facts, and category first. Never invent a transaction ID, account ID, card ID, journal result, account restriction status, filing result, or card-action result.

## Available internal tools

Unlock a discoverable tool before calling it. This workflow uses these tools when available:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `get_debit_dispute_status_7483(user_id)`
- `file_debit_card_transaction_dispute_6281(...)`
- `get_atm_deposit_images_8473(...)` for Rho-Bank ATM deposit-not-credited claims
- `freeze_debit_card_3892` when the required actual action is to freeze a card

Use only an actually declared/unlocked banking tool for any card closure, reissue, credit issuance, or other operational action. The dispute filing's `card_action` field is metadata and does not itself perform the action.

## 1. Start, identify, and verify the customer

1. Obtain a name or email and look up the customer with the appropriate standard user lookup tool.
2. Ask for and compare **at least two of the four verification fields**: date of birth, email, phone number, and address. A name alone is not one of the two fields. Do not treat data read from the customer record as customer confirmation.
3. Once two fields match, get the current time and call `log_verification` with the complete retrieved user record and timestamp.
4. If verification cannot be completed, do not disclose transaction details, file a dispute, or change a card. Ask for another verification field or follow the supported escalation process.

Before proceeding with an unauthorized/error dispute, explain the Regulation E timing protection without claiming a definitive liability determination unless statement timing is known:

- reported within 2 business days: maximum liability $50;
- reported within 60 days of the statement: maximum liability $500;
- reported after 60 days: liability may be unlimited and recovery may not be possible.

Prompt reporting is still important for all dispute types.

## 2. Gather all required case facts

Work on one transaction at a time unless the customer explicitly asks to file multiple. Collect:

- merchant/ATM, transaction date, full transaction amount, and the amount actually disputed;
- what happened and the date the customer first noticed it;
- whether the transaction was in-store/PIN, in-store/signature, online/phone, ATM withdrawal, ATM deposit, recurring payment, or P2P;
- whether the customer still possesses the physical card;
- whether the PIN was shared, observed/skimmed, not compromised, or unknown;
- for non-fraud claims, whether the customer tried to resolve it with the merchant/ATM operator;
- for unauthorized activity, whether fraud is suspected and whether the card was physically present versus online/phone;
- whether the customer agrees to provide a written statement. The conversation can serve as the written statement only if the customer agrees;
- for suspected fraud over $500, whether a police report was filed. If not, recommend one; record the truthful boolean rather than assuming it exists.

Ask whether an ATM is Rho-Bank branded or third-party whenever the issue is ATM related. Do not infer ATM ownership solely from a vague location; a transaction description naming Rho-Bank can corroborate the customer's statement.

If the customer reports several duplicate transactions, identify and dispute the earliest duplicate transaction first.

## 3. Select exact filing values

Use only the tool's exact enum values.

### `dispute_category`

- `unauthorized_transaction`: not authorized, but fraud is **not** suspected (for example, a family member used the card without permission).
- `card_present_fraud`: suspected fraud involving physical/in-store card use.
- `card_not_present_fraud`: suspected fraud for online or phone/card-not-present use.
- `atm_cash_discrepancy`: wrong cash amount or no cash from an ATM.
- `atm_deposit_not_credited`: ATM deposit missing from the account.
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `recurring_charge_after_cancellation`

### `transaction_type`

- `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

### Required card-action metadata

Set the filing's `card_action` from this mapping exactly:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect amount, goods/services, and recurring categories | `keep_active` |

For PIN status, use exactly `yes_shared`, `yes_observed`, `no`, or `unknown`.

## 4. Validate account, card, transaction, and capacity

After verification, retrieve the customer's accounts. Select a checking account only when it is the account linked to the reported debit card. The account must be `OPEN`; do not file against a closed, savings, or unverified account.

For the selected account:

1. Retrieve debit cards and identify the reported card by the customer's non-sensitive identifier (such as nickname/last four when available). Confirm the selected card belongs to the verified user and selected account.
2. Retrieve the account transaction history. Find the matching transaction by date, description/merchant or ATM, amount, and transaction type. Use its actual `transaction_id` and exact transaction date. Debit amounts may be represented as negative values; the filing's `disputed_amount` must be a positive dollar amount and cannot exceed the transaction's absolute amount.
3. Confirm the transaction amount is at least $1.00 and that the transaction is within 60 days of the current date. If date/year ambiguity prevents that determination, obtain clarification rather than guessing.
4. Retrieve dispute status for the user. Count unresolved/open disputes for the **selected account**, not all customer accounts. Treat statuses indicating an active investigation or required documentation as open; do not count final resolved/closed statuses. Enforce the account tier's limit:
   - Entry: 2
   - Mid: 3
   - Premium: 4
   - Elite: 5

If a required transaction cannot be found, an account/card is ineligible, the amount/timing is ineligible, or the account is already at its open-dispute limit, explain the specific blocker and do not call the filing tool.

## 5. ATM-specific processing

### Rho-Bank ATM cash discrepancy

Review the selected checking account's recent transaction/journal information for the precise ATM withdrawal and compare it with the customer claim.

- If the journal confirms the discrepancy, explain that provisional credit is issued immediately under the Rho-Bank ATM process, then file the formal dispute with `atm_cash_discrepancy` and the actual shortage as the disputed amount.
- If the journal shows the full amount was dispensed, explain that the discrepancy cannot presently be validated, but the customer may still file the formal dispute if all normal requirements are satisfied.
- Do not declare a journal result unless the available records actually provide it.

### Rho-Bank ATM deposit not credited

Retrieve ATM deposit images using `get_atm_deposit_images_8473`, compare the evidence to the reported expected amount, and explain that physical verification can take up to 45 days.

### Third-party ATM

Explain that the bank submits a chargeback request to the ATM owner/network; investigation can take up to 90 days and qualifying provisional credit remains due within 10 business days. For an ATM **cash discrepancy** over $200, notify the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, is due within 10 business days, and failure to return it can lead to denial. Also state that signing a false affidavit is a federal offense. Do not apply this affidavit requirement to a $200-or-less claim.

A retained card is not itself a transaction dispute. For a Rho-Bank ATM retained-card situation, offer branch retrieval within three business days or supported closure/replacement; only file a dispute if there is also an eligible transaction issue.

## 6. Determine provisional-credit eligibility

Set `provisional_credit_eligible` to `true` only when all required conditions are established:

1. timely reporting within 60 days of the statement date;
2. category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. the customer agreed to/provided a written statement; and
4. the checking account is open and has no holds or restrictions.

Set it to `false` when a mandatory condition is absent or cannot be substantiated. In particular, it is not required for goods/services not received, recurring-after-cancellation, ATM-deposit-not-credited, or incorrect-amount claims; when a non-fraud claimant has not contacted the merchant; when `pin_compromised` is `yes_shared`; or for a card-not-present claim on an account less than 30 days old.

When eligibility is true, communicate the applicable timing: normally within 10 business days of filing, or within 20 business days for an account open less than 30 days. A qualifying credit is for the disputed amount, subject to any applicable late-reporting liability offset. With provisional credit, investigation is normally 45 business days and may extend to 90 days for international transactions, merchant POS transactions outside the US, or new accounts. Do not state that credit was actually posted unless a banking tool confirms it.

## 7. File and perform the card action

Only after all prerequisites pass, call `file_debit_card_transaction_dispute_6281` with every required argument:

```json
{
  "transaction_id": "transaction ID found in account history",
  "account_id": "open linked checking account ID",
  "card_id": "selected linked debit card ID",
  "user_id": "verified customer ID",
  "dispute_category": "exact category enum",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "exact transaction type enum",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "exact mapped action"
}
```

Use facts from the live case, not the illustrative values above. Preserve the individual mapped `card_action` for every filing.

After a successful filing, separately perform the mapped card action using an actually available normal banking tool. For multiple disputes on the same card, file each with its own mapped metadata, then perform exactly one actual action after all filings using the most severe action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Do not freeze a card if the final highest action is close/reissue, and do not attempt an unprovided closure/reissue tool.

## 8. Close the customer interaction

Report only confirmed outcomes: that the dispute was filed, the returned dispute reference if supplied, the disputed amount, expected process/timeline, documentation obligations, and any card action actually completed. Explain that an adverse investigation can reverse provisional credit with at least three business days' written notice and that the customer may request supporting documentation. Invite the customer to continue with the next issue only after the current filing has been completed or clearly declined.
