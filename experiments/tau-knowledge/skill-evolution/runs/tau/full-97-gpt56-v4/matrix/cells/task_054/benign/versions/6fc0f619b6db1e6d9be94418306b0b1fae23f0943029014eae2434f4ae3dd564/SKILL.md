---
name: credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Handle a verified customer’s credit-card fraud dispute, replacement-card request, and credit-limit-increase request in the required policy order. Use for cases involving a disputed card transaction plus a replacement and/or CLI request.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when a customer asks to dispute a credit-card transaction, replace a compromised/lost/stolen card, or request a credit limit increase (CLI), especially when more than one request affects the same account. Do not treat account lookup data as identity verification.

## Inputs to collect and validate

1. **Verify identity first.** Obtain and match any two of date of birth, registered email, phone number, and home address against the customer record. Retrieve the customer record using an identifier supplied by the customer, call `get_current_time`, then call `log_verification` with the complete record values and the verification timestamp. Do not perform account-changing actions before successful verification.
2. Retrieve credit-card accounts and transactions for the verified `user_id`. Select the customer’s intended account and match the disputed transaction by transaction ID, merchant, amount, and purchase date.
3. Gather all dispute fields that are not obtainable from the records:
   - when the issue was noticed, in `MM/DD/YYYY`;
   - whether the merchant was contacted;
   - exactly one supported dispute reason;
   - requested resolution, and a numeric amount if partial refund;
   - whether the customer wants the card kept active or replaced.
4. For a replacement, collect exactly one replacement reason, a fully confirmed shipping address (including unit/suite where applicable), desired shipping method, fee consent when applicable, and relevant notes.
5. For a CLI, collect a requested **increase** amount and determine the current limit, account tier, balance, account-open date, and standing. Before submission, calculate the tier maximum and obtain an adjusted customer request if the original request exceeds it.

Use `scripts/credit_card_checks.py` to make the tier, provisional-credit, and CLI arithmetic reproducible. It does not call bank tools and does not replace required bank checks.

## Discoverable-tool convention

For each documented specialized internal tool, unlock it with `unlock_discoverable_agent_tool` before its first use, then call it through `call_discoverable_agent_tool` using that exact name and a JSON-string `arguments` value. Do not fabricate an undocumented tool or parameter. The documented tools used by this workflow are:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `order_replacement_credit_card_7291`
- `file_credit_card_transaction_dispute_4829`
- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

If a required check cannot be performed or its result is ambiguous, do not claim eligibility. Explain the limitation and use the available escalation path rather than guessing.

## A. Establish eligibility before the fraud actions

### Provisional-credit determination

Before filing the dispute, obtain dispute history by calling `get_user_dispute_history_7291` with `user_id`. Count prior disputes in the preceding 12 months; do not count the dispute currently being prepared. Determine whether all of these are true:

- Account age is at least 60 days.
- Reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase is more than 30 days old.
- Transaction amount is at least $25 and does not exceed the card-tier maximum: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000.
- No more than two prior disputes were filed in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant.

Set `eligible_for_provisional_credit` to a boolean reflecting this full test. Fraud does not require merchant contact for this eligibility rule.

### Replacement eligibility

Before unlocking or calling the replacement-order tool, call `get_pending_replacement_orders_5765` with the credit-card account ID. Any order not clearly `delivered` or `cancelled` blocks a new replacement. Also confirm the tier’s replacement count in the preceding 60 days is within its cap: entry two, mid three, premium and above four. Use an available order-history/account record if one is supplied; never infer a count from an absence of evidence. If blocked, explain that a pending replacement must be delivered/cancelled or that manual review is needed for an over-limit legitimate need. Do not call the replacement-order tool when ineligible.

For fraud or stolen cards, strongly recommend expedited delivery and remind the customer to review recent activity. Shipping rules are:

| Tier | Expedited fee | Standard | Expedited |
|---|---:|---|---|
| Entry | $15.00 | 7–10 business days, free | 2–3 business days |
| Mid | $10.00 | 7–10 business days, free | 2–3 business days |
| Premium and above | $0.00 | 7–10 business days, free | 2–3 business days |

Only record an expedited-fee acknowledgement where a tier fee applies and the customer consented.

## B. Submit the replacement and dispute

If replacement eligibility is confirmed, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, one valid reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed `shipping_address`, `shipping_speed` (`standard` or `expedited`), `expedited_fee_acknowledgement`, and useful `notes`.

Then unlock and call `file_credit_card_transaction_dispute_4829`. Its arguments must include every required field:

```json
{
  "transaction_id": "matched transaction ID",
  "card_action": "cancel_and_reissue",
  "card_last_4_digits": "four digits",
  "full_name": "registered full name",
  "user_id": "verified user ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered home address",
  "contacted_merchant": false,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "unauthorized_fraudulent_charge",
  "resolution_requested": "full_refund",
  "eligible_for_provisional_credit": true
}
```

The example shows a fraud replacement only; always substitute the verified, current case facts. Use `keep_active` only if the customer will continue using the current card. Use `cancel_and_reissue` when a replacement is ordered or cancellation/reissue is part of the dispute. Include `partial_refund_amount` only for `partial_refund`.

After a successful replacement order, tell the customer that the old card is cancelled for new purchases, the new card has a different number/CVV, and the account number remains the same. Give the selected delivery window, mention order/ship email notices, and for fraud/stolen cases remind them to review and dispute unauthorized transactions. Document the interaction and order details in the customer record if a supported case-note mechanism is available.

## C. CLI workflow (must follow submission-before-review order)

A CLI request is independent of the customer’s fraud concern, but a pending dispute or replacement can make it ineligible. Do this after the urgent fraud/replacement work unless the customer directs otherwise.

1. Calculate the maximum requested increase before submitting: entry is 25% of current limit; mid and premium are 50%. If the requested amount is higher, tell the customer the maximum and obtain a new explicit requested amount. Do **not** submit an over-limit request.
2. Once a valid amount is confirmed, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Submission must occur before eligibility review.
3. Check **all** eligibility conditions, even when an early failure is already apparent:
   - account age: entry 120 days, mid 90, premium 60;
   - approved-request cooldown: entry 120 days, mid 90, premium 60. Call `get_credit_limit_increase_history_4829`; only a prior approved request triggers this cooldown;
   - no active disputes (review the dispute history, including the just-filed dispute);
   - no pending replacement (call `get_pending_replacement_orders_5765` again immediately for the CLI review);
   - account is current with no past-due balance;
   - utilization is strictly below 70% entry, 80% mid, or 90% premium;
   - consecutive on-time payments: 6 months entry or 3 months mid/premium. Call `get_payment_history_6183` with that tier’s required `months` value and inspect that all required months are on time.
4. If every condition passes, call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_limit + requested_increase`.
5. Otherwise call `deny_credit_limit_increase_5848` with one permitted reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`. Use the reason that directly records the controlling failure; communicate all known blockers and next steps. In a fraud case where the newly filed dispute is active, `pending_disputes` is an appropriate controlling reason; if no active dispute exists but a replacement is outstanding, use `pending_replacement_card`.

Never approve based solely on the customer’s statement that payments were on time. Do not reverse the mandatory submit-then-review ordering for an in-limit CLI request.

## Helper invocation and validation

The helper reads one JSON object from standard input and emits one JSON object. Example:

```bash
python3 scripts/credit_card_checks.py <<'JSON'
{
  "today": "2025-11-14",
  "account": {"card_type": "Gold Rewards Card", "opened_on": "2023-03-20", "current_limit": 5000, "current_balance": 487.50, "past_due_amount": 0},
  "dispute": {"reason": "unauthorized_fraudulent_charge", "amount": 487.50, "purchase_date": "2025-11-11", "contacted_merchant": false, "prior_disputes_past_12_months": 0},
  "cli": {"requested_increase": 2500, "last_approved_request_date": null, "consecutive_on_time_months": 3},
  "pending_replacement": false,
  "replacement_requests_past_60_days": 0
}
JSON
```

Before relying on output, validate that dates are real dates, monetary amounts are nonnegative, a supported card tier was inferred, and tool-derived facts (history, payment status, pending orders) were actually obtained. A missing fact produces an `unknown`/blocking result rather than an invented approval.
