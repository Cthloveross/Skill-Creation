---
name: credit-card-dispute-and-fraud-replacement
version: 1.0.0
description: Process one or more credit-card transaction disputes, determine provisional-credit eligibility, and arrange a fraud-driven replacement card when requested. Use for customers reporting unauthorized charges, duplicate charges, billing errors, merchant problems, or requesting cancellation and reissue of an affected card.
---

# Credit-Card Dispute and Fraud Replacement

Use this Skill to accurately collect the required dispute facts, retrieve missing card last-four digits through the documented customer tool, determine provisional-credit eligibility separately for every transaction, and submit each dispute through the required internal tool. If the customer requests a replacement, handle the replacement workflow before filing disputes with `card_action: "cancel_and_reissue"`.

## Required information for every dispute

Each disputed transaction is a separate submission. Before submitting, obtain or verify:

- `transaction_id`
- card action: exactly `keep_active` or `cancel_and_reissue`
- affected card's last four digits
- full name, user ID, registered phone, registered email, and registered address
- whether the customer contacted the merchant (`contacted_merchant`, boolean)
- purchase date and issue-noticed date in `MM/DD/YYYY`
- exactly one permitted reason:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`
- a numeric `partial_refund_amount` only when resolution is `partial_refund`
- the per-transaction boolean `eligible_for_provisional_credit`

Do not infer a transaction merely from a merchant name. Ask the customer to select each charge by transaction ID or unambiguous date and amount, then verify it belongs to the affected card.

## Workflow

1. **Verify identity and obtain account facts.** Ask the customer to confirm at least two of the registered identity fields (date of birth, email, phone, address). Look up the user and credit-card account(s), and after confirmation obtain the current time and call `log_verification` with all required registered fields. Do not treat data found in an internal lookup as the customer's confirmation.

2. **Identify the card and transaction records.** Retrieve the customer's accounts and transactions. Match every selected transaction to its account, transaction amount, date, and card tier. Use the account opening date and tier in the eligibility decision.

3. **Resolve missing card last four digits.** Do not guess or fabricate the digits. The documented card-number procedure designates `get_card_last_4_digits(credit_card_account_id: str)` as a customer-discoverable tool. Pass it with `give_discoverable_user_tool`, using the selected account ID in the JSON argument string, and await the resulting digits before filing. If the customer instead supplies digits, verify they identify the selected account/card when possible.

4. **Collect dispute-specific facts.** For every selected transaction, map customer wording to the exact reason and resolution enums. “Fraud” or “unauthorized” maps to `unauthorized_fraudulent_charge`; “missing refund” maps to `refund_never_processed`; and “not as described” maps to `goods_services_not_as_described`. A merchant-contact statement such as “I contacted them” is `true`; do not assume merchant contact for a non-fraud dispute. Obtain an explicit requested resolution if it was not stated. If all issues were noticed “today,” get the current date and use it in `MM/DD/YYYY` format.

5. **If replacement is requested, complete its prerequisites first.** Confirm the shipping address, replacement reason (`fraud_suspected` for suspected fraudulent use), and shipping speed. Check for a pending replacement order using `get_pending_replacement_orders_5765` with the credit-card account ID; unlock that agent tool first if necessary. A pending or shipped order blocks a new replacement request. Also confirm the tier's replacement-limit eligibility from available replacement history; do not order when a documented eligibility condition fails. For fraud/stolen replacement, recommend expedited shipping. Explain applicable fees and record fee consent when applicable. Unlock and call `order_replacement_credit_card_7291` only after all prerequisites are satisfied. The affected old card is cancelled after a successful order, so use `cancel_and_reissue` on all disputes for that card. A replacement is not required when the customer wants to keep the card active.

6. **Determine provisional-credit eligibility for each transaction.** First retrieve the user's filed dispute history with `get_user_dispute_history_7291` (unlock it before calling if the environment requires it). Count disputes filed in the preceding 12 months, rather than counting the batch currently being prepared as historical disputes. Apply every condition below independently to each charge:
   - account has been open at least 60 days;
   - reason is fraud, duplicate, or `goods_services_not_received` (the latter only when purchase is more than 30 days old);
   - transaction amount is at least $25 and does not exceed the tier cap;
   - no more than two previously filed disputes in the prior 12 months;
   - for every non-fraud reason, the customer contacted the merchant.

   Tier caps are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Gold and Business Gold are Premium. Set the boolean false whenever a condition is not met or cannot be established; never promise a provisional credit merely because a dispute can be filed.

7. **Validate before submission.** Run `scripts/dispute_helper.py` once per final payload (or apply the same checks manually). It validates enums, date format, conditional partial-refund fields, basic required data, and can calculate eligibility from supplied factual context. Correct missing facts before submitting.

8. **File every valid dispute.** Unlock `file_credit_card_transaction_dispute_4829`, then call `call_discoverable_agent_tool` once for each transaction with `agent_tool_name` set to that exact name and `arguments` set to a JSON string containing that transaction's complete payload. Do not combine multiple transactions in one call. Do not automatically execute recommendations emitted by a script; only the declared banking tool call files the dispute.

9. **Report results accurately.** Record each returned case/result. Tell the customer which disputes were filed, that provisional credit (if eligible) is temporary during investigation and can later become permanent or be reversed, and—if a replacement was ordered—the selected delivery window and notification expectations. If a required datum cannot be obtained, say which datum is blocking filing and request it rather than inventing it. Escalate an unrecoverable tool or account problem using the applicable supported handoff process.

## Helper script

`scripts/dispute_helper.py` reads one JSON object from standard input and writes one JSON object to standard output. It never calls bank tools and never accesses customer records.

Input schema:

```json
{
  "action": "validate" | "eligibility",
  "payload": { "...dispute tool fields...": "..." },
  "context": {
    "current_date": "MM/DD/YYYY",
    "account_open_date": "MM/DD/YYYY",
    "transaction_amount": 0,
    "card_tier": "Premium",
    "previous_dispute_dates": ["MM/DD/YYYY"],
    "purchase_date": "MM/DD/YYYY"
  }
}
```

For `validate`, the output has `valid`, `errors`, and normalized `payload`. `transaction_amount` in context is optional but lets the helper reject an invalid partial amount. For `eligibility`, output has `eligible`, `reasons`, and diagnostic values. The executor must obtain all input values at runtime from customer statements, account/transaction lookup, dispute-history results, and current time.

Example invocation in the packaged runtime:

```sh
printf '%s' '<JSON input matching the schema above>' | python3 scripts/dispute_helper.py
```

Treat a `valid: false` result as a blocking correction list. Treat `eligible: false` as the exact value for the dispute tool's `eligible_for_provisional_credit` field; it does not prohibit filing an otherwise complete dispute.
