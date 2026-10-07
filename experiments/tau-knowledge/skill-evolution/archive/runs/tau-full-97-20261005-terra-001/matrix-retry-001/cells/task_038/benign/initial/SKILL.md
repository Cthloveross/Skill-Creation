---
name: credit-card-disputes-and-replacement
version: 1.0.0
description: Safely files one or more credit-card transaction disputes and, when requested, coordinates a replacement card. Use when a verified customer identifies transactions to dispute and may want the affected card cancelled and reissued.
---

# Credit-card disputes and replacement

Use this skill for a customer who wants to dispute credit-card transactions, including a fraud-related request to replace the card. Treat each transaction as a separate dispute. Do not submit a dispute or replacement order until the applicable prerequisites are complete.

## Required workflow

1. **Verify identity first.** Use standard verification: confirm at least two of date of birth, registered email, phone number, and address against the retrieved customer record. After successful verification, obtain the current timestamp with `get_current_time` and call `log_verification` with all required profile fields and the timestamp. Do not disclose card data or take account actions before verification.
2. **Find the intended card and transactions.** Look up the customer, accounts, and transactions using the normal banking tools. Confirm that every selected transaction belongs to the selected card/account and record its ID, amount, and purchase date. Never infer a transaction ID from merchant, amount, or date alone where multiple matches are possible.
3. **Collect or derive all dispute facts.** For every selected transaction, collect:
   - the exact permitted `dispute_reason`;
   - whether the customer contacted the merchant (`contacted_merchant`);
   - the issue-noticed date in `MM/DD/YYYY` (if the customer says “today,” use the verified current date);
   - the requested resolution; and
   - a partial-refund amount when and only when `partial_refund` is selected.

   Use only these reason values: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`. Use only `full_refund`, `partial_refund`, or `reversal_of_charge` for resolution. Map the customer’s stated facts without changing their meaning. In particular, a charge described as a repeated instance of the same charge is normally `duplicate_charge`; an unrecognized charge is `unauthorized_fraudulent_charge`.
4. **Obtain the card last four digits securely.** If the verified customer does not have the digits, provide the customer the discovered tool `get_card_last_4_digits` using `give_discoverable_user_tool`, with JSON arguments containing the selected `credit_card_account_id`. Capture only the returned last four digits. Do not ask for or expose a full card number.
5. **Evaluate provisional-credit eligibility independently for each dispute.** Retrieve the customer’s dispute history with `get_user_dispute_history_7291` (unlock it first if the runtime requires agent-tool unlocking). Count disputes filed in the preceding 12 months, using the current date. Evaluate all criteria, not just the reason:
   - account has been open at least 60 days;
   - reason is fraud, duplicate, or goods/services not received (the latter only when purchase is more than 30 days old);
   - amount is at least $25 and no more than the limit for the actual card tier;
   - no more than two prior disputes were filed in the past 12 months; and
   - for every non-fraud reason, the customer contacted the merchant.

   The limits are entry $2,500, mid $5,000, premium $10,000, elite $15,000, and invitation $25,000. Pass a boolean result for every dispute. Do not promise a credit merely because the boolean is true; it is provisional pending investigation.
6. **If a replacement is requested, complete replacement prerequisites.** Confirm the exact shipping address, including business, unit, or suite details, and obtain an explicit speed choice. Explain standard delivery (7–10 business days, free) and expedited delivery (2–3 business days). Determine the fee from the actual card tier: entry $15, mid $10, premium and above $0. For fraud or stolen requests, strongly recommend expedited shipping and remind the customer to review recent activity.

   Before unlocking or calling the replacement-order tool, check `get_pending_replacement_orders_5765` for the selected credit-card account (unlock first if required). A pending or shipped order blocks a new request; delivered and cancelled orders are final. Also confirm the number of replacements in the last 60 days is within the tier limit: entry 2, mid 3, premium and above 4. If the available records cannot establish this eligibility condition, do not submit the replacement; obtain the required record or explain that a manual review is needed. If expedited shipping has a fee, obtain explicit consent to that exact fee before submission.
7. **Submit only when complete.** If ordering a replacement, unlock `order_replacement_credit_card_7291` and then call it with the account identifier, one permitted replacement reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed address, `standard` or `expedited`, the fee acknowledgement, and useful notes. Use `fraud_suspected` for a replacement requested because of an unrecognized/fraudulent transaction. The tool call must not be used as an eligibility check.

   Then unlock `file_credit_card_transaction_dispute_4829` and make one call per dispute, passing a JSON string containing every required argument: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `eligible_for_provisional_credit`, plus `partial_refund_amount` only for a partial refund. Set `card_action` to `cancel_and_reissue` when the customer requested card cancellation/reissue; otherwise use `keep_active`. The replacement may have been ordered first or the cancellation may occur as part of the dispute, but the selected action must accurately reflect the customer’s request.
8. **Close out accurately.** Report each successful or failed submission separately. When a replacement order succeeds, explain that the old card is cancelled for new purchases, the replacement has a new card number and CVV, the account number remains unchanged, and the customer will receive order and shipping emails. State the selected delivery window. For fraud/stolen matters, remind the customer to review recent transactions and dispute unauthorized activity. Document the verification, selected transactions, dispute payload facts, eligibility determinations, replacement eligibility check, order/dispute results, and customer communications in the customer record using the available record mechanism; do not claim documentation was completed if no such mechanism exists.

## Missing information and failures

- Ask focused follow-up questions for any missing required dispute field, last four digits, merchant-contact answer, resolution, or noticed date. Do not submit incomplete payloads.
- A customer-provided alternate/work address still must be explicitly confirmed as the shipping address; never silently substitute the registered address.
- Do not require merchant contact for an unauthorized-fraudulent-charge dispute. Merchant contact is required to mark any other reason eligible for provisional credit, but a dispute itself can still be filed with `eligible_for_provisional_credit: false`.
- If a discovered tool is unavailable, denied, malformed, or returns ambiguous data, do not fabricate a result or mark eligibility satisfied. Retry only when appropriate; otherwise explain the blocking issue and use the supported escalation path if needed.
- A replacement rejection due to a pending order or tier limit means no new replacement submission. Explain that the customer must wait for delivery/cancellation or request manual review for a legitimate exception.

## Optional payload preflight helper

`scripts/preflight.py` is a local validator and calculator; it never contacts the bank or submits actions. Send one JSON object on stdin and read one JSON object from stdout.

Input schema (all identifiers and personal data are supplied at runtime):

```json
{
  "now_date": "MM/DD/YYYY",
  "account": {
    "account_id": "string",
    "card_type": "string",
    "opened_date": "MM/DD/YYYY",
    "card_last_4_digits": "1234",
    "replacement_count_60_days": 0,
    "no_pending_replacement": true
  },
  "customer": {
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string"
  },
  "card_action": "keep_active",
  "prior_disputes_12_months": 0,
  "disputes": [{
    "transaction_id": "string",
    "amount": 0,
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "one permitted reason",
    "contacted_merchant": false,
    "resolution_requested": "full_refund",
    "partial_refund_amount": null
  }],
  "replacement": {
    "requested": false,
    "reason": "fraud_suspected",
    "shipping_address": "string",
    "shipping_speed": "expedited",
    "fee_consent": true,
    "notes": "string"
  }
}
```

The output contains `valid`, `errors`, a tier and fee assessment, per-dispute provisional-credit decisions, and draft payloads only when inputs validate. Review it against live tool results before acting. Example runnable invocation: `python3 scripts/preflight.py < case.json`.
