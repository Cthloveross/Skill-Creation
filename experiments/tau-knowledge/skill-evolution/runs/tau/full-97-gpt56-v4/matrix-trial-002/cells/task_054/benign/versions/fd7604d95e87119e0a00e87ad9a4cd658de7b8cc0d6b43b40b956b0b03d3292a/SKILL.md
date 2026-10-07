---
name: secured-credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Handle a verified customer's credit-card fraud dispute, replacement-card request, and subsequent credit-limit-increase request using the required banking and discoverable-tool workflows. Use when the request may combine any of these actions, especially when fraud makes card security the priority.
---

# Secured Credit-Card Fraud, Replacement, and CLI Workflow

## Scope and safety

Use this Skill for credit-card transaction disputes, card replacements, and credit-limit increases (CLI). Treat a fraud or stolen-card report as the priority before a discretionary CLI. Do not expose account details or perform an account-changing action until identity verification has succeeded and has been logged.

Use the normal banking lookup/logging tools and the named discoverable agent tools. Before each named discoverable tool is called, unlock that exact tool with `unlock_discoverable_agent_tool`; then call it with `call_discoverable_agent_tool`. Keep tool arguments as JSON strings. Do not retry an action if its result is unknown or ambiguous; explain/escalate as appropriate instead.

Never invent customer facts, eligibility results, records, dates, or a successful action. If a required field is unavailable, ask the customer for it; if an internal check is unavailable or ambiguous, do not claim eligibility.

## 1. Verify identity and establish the target account

1. Obtain a customer identifier and compare at least two of the four identity fields against the retrieved customer record: date of birth, email, phone number, and address.
2. Retrieve the customer record with the appropriate user lookup tool and retrieve the current time with `get_current_time`.
3. When two fields match, call `log_verification` with all required fields from the authoritative user record, the user ID, and the returned timestamp. Do not rely merely on a customer statement that verification occurred.
4. Retrieve the user's credit-card accounts and identify the account/card involved. Retrieve the user's transactions and match the disputed charge by transaction ID, merchant, date, amount, and account. Resolve any ambiguity with the customer before proceeding.
5. Preserve the authoritative user ID, account ID, card last four digits, account-open date, tier/card type, current limit, balance, and account status for subsequent checks.

## 2. Gather and normalize required customer choices

For a dispute, collect or confirm:

- the matching transaction;
- when the issue was noticed, normalized to `MM/DD/YYYY`;
- whether the customer contacted the merchant (`true`/`false`);
- exactly one allowed dispute reason;
- exactly one requested resolution; and
- full name, registered phone, email, and registered address from the verified record.

Allowed dispute reasons are `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`. Resolution is `full_refund`, `partial_refund`, or `reversal_of_charge`; request a numeric partial amount only for `partial_refund`.

For a replacement, confirm the complete shipping address (including unit/suite when applicable), select exactly one replacement reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), and ask for `standard` or `expedited` shipping. State the delivery period and fee before consent. Fraud/stolen cases warrant a strong recommendation for expedited delivery and a reminder to review recent transactions.

For a CLI, collect the requested *increase* in whole dollars and the customer's confirmation after informing them of any per-tier maximum. A request above the maximum must not be submitted. If the customer adjusts it, record the adjusted amount and confirmation.

## 3. Determine dispute provisional-credit eligibility

Before filing the dispute, obtain the user's dispute history using `get_user_dispute_history_7291` and count disputes filed in the preceding 12 months using the current date. Determine eligibility from the authoritative account and transaction information:

- account open at least 60 days;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (the latter only when the purchase is more than 30 days old);
- amount is at least $25 and no more than the card-tier maximum;
- no more than two prior disputes in the past 12 months; and
- for every non-fraud reason, the customer contacted the merchant.

The maximums are $2,500 entry, $5,000 mid, $10,000 premium, $15,000 elite, and $25,000 invitation tier. A fraud dispute does not require merchant contact, but that response is still a required filing argument. Use `scripts/evaluate_credit_card_case.py` for a transparent calculation when normalized dates and records are available.

Set `card_action` to `cancel_and_reissue` when the customer wants the compromised card replaced; otherwise set it to `keep_active`. Do not set `cancel_and_reissue` unless replacement/cancellation is actually intended.

Unlock and call `file_credit_card_transaction_dispute_4829` with every required field:

```json
{
  "transaction_id": "<matched transaction id>",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "<four digits>",
  "full_name": "<verified full name>",
  "user_id": "<verified user id>",
  "phone": "<registered phone>",
  "email": "<registered email>",
  "address": "<registered address>",
  "contacted_merchant": false,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "<allowed reason>",
  "resolution_requested": "<allowed resolution>",
  "eligible_for_provisional_credit": true
}
```

Include `partial_refund_amount` only for `partial_refund`. Interpret a failed tool response as no dispute filed; do not proceed on an assumption that it exists.

## 4. Order replacement only after eligibility checks

Before unlocking or calling `order_replacement_credit_card_7291`, confirm replacement eligibility. Unlock and call `get_pending_replacement_orders_5765` for the credit-card account. Any pending or shipped/non-final order blocks a new order. Check the applicable 60-day replacement count from available authoritative replacement records; limits are two entry, three mid, and four premium-and-above. If the available records cannot establish the count, do not assert eligibility—obtain the required internal record or explain that the request needs review.

Calculate expedited fees by tier: entry $15, mid $10, premium and above $0. Standard is free. Obtain explicit acknowledgement only where a fee applies; represent the acknowledgement accurately. Once eligibility, address, reason, speed, and any fee consent are established, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant `notes` (such as fraud context or delivery instructions).

If the replacement succeeds, explain that the old card is cancelled for new purchases, the replacement has a new number/CVV, and the account number remains unchanged. Give the selected delivery range and mention order/ship email notifications. For fraud/stolen cases, again advise reviewing and disputing unauthorized transactions.

## 5. Process a CLI in its mandated order

Process a CLI only after the security/dispute work the customer prioritized. The request submission must precede internal eligibility checks, but amount validation must precede submission.

1. Calculate the maximum increase from the *current* limit: 25% for entry tier and 50% for mid/premium tiers. If the requested amount exceeds it, explain the maximum and obtain an adjusted explicit request; do not submit the excessive amount.
2. Unlock and call `submit_credit_limit_increase_request_7392` with account ID, user ID, and the confirmed integer increase amount.
3. After a successful submission, perform and document **all** checks, even if one has already failed:
   - account age: 120/90/60 days for entry/mid/premium;
   - cooldown using `get_credit_limit_increase_history_4829`: 120/90/60 days, applying only after a prior approved request;
   - active/pending disputes;
   - pending replacement via `get_pending_replacement_orders_5765` immediately before the decision;
   - current/no past-due account standing;
   - utilization strictly below 70%/80%/90%; and
   - payment history using `get_payment_history_6183` for 6/3/3 consecutive months.
4. If every check passes, unlock and call `approve_credit_limit_increase_5847` with the new total limit (current limit plus confirmed increase). If any check fails, unlock and call `deny_credit_limit_increase_5848` with the documented permitted reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.
5. Communicate only the decision actually returned by the tool. In a fraud/replacement case, do not overlook that the newly filed dispute and/or non-final replacement can block the CLI. Explain the applicable next step without promising a later approval date unless it is supported by the records.

## 6. Close the interaction

Document verification, matched transaction, customer selections, eligibility evidence, tool calls/results, and customer-facing commitments in the customer record through the available approved record mechanism. Summarize completed actions and unresolved items. For fraud, remind the customer to review transactions and use the app/site dispute path for additional unauthorized charges.

## Helper script

`scripts/evaluate_credit_card_case.py` accepts one JSON object on stdin and emits a JSON eligibility calculation on stdout. It performs no banking actions. Its input schema is documented in the script header. Provide normalized values from current account, transaction, and history lookups; treat `null`/missing results as not established rather than as passing.
