---
name: credit-card-transaction-dispute
version: 1.0.0
description: Safely authenticate a customer, collect and validate complete claim-specific information, determine provisional-credit eligibility, and file one or more credit-card transaction disputes using the designated discoverable banking tool.
---

# Credit Card Transaction Dispute

Use this Skill when a customer wants to dispute one or more credit-card transactions, including fraud, duplicate charges, billing errors, delivery issues, cancelled subscriptions, or missing refunds. Treat every disputed transaction as a separate claim and never combine multiple transactions in one filing.

## Required tools and records

Use normal banking tools to identify the customer, cards, and transactions. The required filing tool is `file_credit_card_transaction_dispute_4829`; unlock it before the first filing and invoke it through `call_discoverable_agent_tool` with a JSON-string `arguments` value.

When required by the runtime, unlock and call `get_user_dispute_history_7291` with the customer `user_id` to obtain dispute history. Use the documented last-four-digits procedure: after the relevant card account is known, give the customer `get_card_last_4_digits` with `{"credit_card_account_id":"<account id>"}` via the user-tool mechanism, or record the four digits if the customer provides them directly. Do not guess card digits.

## Workflow

1. **Authenticate before account disclosure or filing.**
   - Identify the user through an approved lookup.
   - Confirm at least two of date of birth, registered email, registered phone number, and registered address against the customer.
   - Get the current timestamp and call `log_verification` with all required registered identity fields and that timestamp. Do not continue with account-specific details or filing until verification succeeds.

2. **Establish the transaction and associated card.**
   - Retrieve the user’s card accounts and transaction history after verification.
   - Match the customer’s description to one specific completed transaction. Confirm merchant, amount, purchase date, card type, and especially the `transaction_id` when matches could be ambiguous (for example, duplicates or recurring merchants).
   - Associate the transaction with exactly one card account and obtain that card’s last four digits. The digits must be exactly four characters/digits; never infer them from an account ID.
   - For each claim, determine whether the card remains active (`keep_active`) or is cancelled and replaced (`cancel_and_reissue`). Explicitly honor a request for replacement/cancellation. If the customer has not expressed an intent to replace the card, confirm the intended action rather than representing a replacement as ordered.

3. **Collect a complete claim record, one dispute at a time.**
   Required filing values are:
   - `transaction_id`
   - `card_action`: `keep_active` or `cancel_and_reissue`
   - `card_last_4_digits`
   - registered `full_name`, `user_id`, `phone`, `email`, and `address`
   - `contacted_merchant` as a boolean; ask even for fraud (a fraud answer of no is valid)
   - `purchase_date` and `issue_noticed_date`, each `MM/DD/YYYY`
   - one allowed `dispute_reason`
   - one allowed `resolution_requested`
   - `partial_refund_amount` as a numeric dollar amount only when the requested resolution is `partial_refund`
   - calculated `eligible_for_provisional_credit` as a boolean.

   Map the customer’s description only to one of these exact reason strings:
   `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.

   Map requested resolution only to `full_refund`, `partial_refund`, or `reversal_of_charge`. If partial, obtain the exact dollar amount. Do not invent a resolution, noticed date, merchant-contact answer, or partial amount. If a customer says they noticed the problem “today,” get the current time and use its date in `MM/DD/YYYY` format.

4. **Determine provisional-credit eligibility independently for each claim.**
   Retrieve the account opening date, transaction amount and card tier from current records, and retrieve the customer’s dispute history. Count disputes filed in the 12 months before the filing date; do not rely on a customer’s recollection where the history tool is available.

   A customer is eligible only if *all* conditions are met:
   - the relevant card account has been open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase was more than 30 days ago;
   - amount is at least $25 and no more than the card tier limit;
   - no more than two disputes were filed in the prior 12 months; and
   - for every non-fraud reason, the customer contacted the merchant.

   Limits are $2,500 for Entry, $5,000 for Mid, $10,000 for Premium, $15,000 for Elite, and $25,000 for Invitation tier. Gold Rewards Card and Business Gold Rewards Card are Premium. A claim can still be filed if it is ineligible; send `false`, not a made-up exception.

   Run `scripts/evaluate_and_validate.py` before filing. It checks filing-field completeness and calculates the eligibility decision from supplied runtime facts. See its JSON interface below. Review returned errors and resolve them with the customer or records before filing. Its output is a recommendation only and does not perform a bank action.

5. **File and report accurately.**
   - Unlock `file_credit_card_transaction_dispute_4829` before calling it.
   - Build a fresh JSON object for precisely one validated claim. Include `partial_refund_amount` only for a partial-refund request; encode it as a JSON number, not a formatted currency string.
   - Call `call_discoverable_agent_tool` with `agent_tool_name` set exactly to `file_credit_card_transaction_dispute_4829` and `arguments` set to the serialized claim object.
   - Do not say a dispute was filed until the tool reports success. Preserve and communicate any returned confirmation/reference appropriately.
   - If the tool rejects a claim, do not repeatedly submit it unchanged. Explain the missing/invalid data, correct it, and retry only after correction. If an action’s outcome is reported as unknown, do not repeat it; escalate according to the banking workflow.

## Validation script

Run from the package runtime as:

```text
python scripts/evaluate_and_validate.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. Expected input:

```json
{
  "claim": {
    "transaction_id": "...",
    "card_action": "keep_active",
    "card_last_4_digits": "1234",
    "full_name": "...",
    "user_id": "...",
    "phone": "...",
    "email": "...",
    "address": "...",
    "contacted_merchant": false,
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "unauthorized_fraudulent_charge",
    "resolution_requested": "reversal_of_charge",
    "eligible_for_provisional_credit": true
  },
  "transaction_amount": 100.0,
  "card_type": "Gold Rewards Card",
  "account_open_date": "MM/DD/YYYY",
  "filing_date": "MM/DD/YYYY",
  "prior_dispute_dates": ["MM/DD/YYYY"]
}
```

`prior_dispute_dates` may also contain ISO-style timestamps returned by history. The output contains `valid_for_filing`, `validation_errors`, `calculated_eligible_for_provisional_credit`, `eligibility_reasons`, and `prior_disputes_in_last_12_months`. The claim’s supplied eligibility flag must match the calculated value before submission.

## Missing information and escalation

Keep a pending claim open rather than filing it with placeholders when a transaction cannot be identified, card digits are unavailable, a required customer choice is missing, identity verification fails, or the supported tool has a technical failure. Ask focused, claim-specific follow-up questions. Follow the runtime’s human-transfer process for issues that cannot be safely resolved through the available tools, such as a technical tool failure or a complex billing dispute requiring specialist handling.
