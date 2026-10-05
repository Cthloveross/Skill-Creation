---
name: credit-card-dispute-filing-and-fraud-reissue
description: File one formal credit-card dispute for every customer-selected transaction and coordinate a fraud-related card reissue. Use after transactions and customer dispute instructions are available; includes identity verification, discoverable-tool calls, provisional-credit decisions, pending-replacement checks, and replacement ordering.
---

# Credit-Card Dispute Filing and Fraud Reissue

This Skill completes the requested banking actions. A customer-selected transaction must be submitted as an individual formal dispute; collecting the facts, explaining the process, or transferring the customer is not a substitute for filing it.

## Verify and collect facts

1. Before account-changing actions, verify identity by matching **two of four** profile fields: date of birth, email, phone number, and address. Profile lookup is not itself verification.
2. Get the current time and call `log_verification` with the complete verified profile and timestamp.
3. Look up the customer's card accounts and transaction history. Match every selected merchant/date/amount to exactly one transaction on the stated card. Do not dispute similarly named transactions or a different card.
4. For each selected transaction, record the exact reason, purchase date, issue-noticed date, merchant-contact boolean, requested resolution, and partial-refund amount when applicable. Valid codes are:
   - reasons: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`
   - resolutions: `full_refund`, `partial_refund`, `reversal_of_charge`
   - card actions: `keep_active`, `cancel_and_reissue`
5. For a partial refund, obtain a positive amount no greater than the transaction amount. Do not include `partial_refund_amount` for any other resolution.
6. If conflicting instructions for the same transaction exist, obtain an explicit final confirmation before filing that transaction. Use the latest unambiguous customer confirmation; never silently choose between a prior partial-refund instruction and a later full-refund or reversal instruction.

## Required supporting lookups

- Obtain the disputed card's last four digits with the documented `get_card_last_4_digits(credit_card_account_id)` workflow. Follow the runtime's discovered-tool access model; never request a full card number from the customer.
- Unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes already filed in the preceding 12 months **before this batch**. The current batch must not inflate the baseline used for any of its provisional-credit decisions.
- If the customer requests cancellation/reissue, confirm the shipping address, replacement reason, and standard versus expedited shipping. For suspected fraud use `fraud_suspected`; recommend expedited shipping. Gold and other premium-or-higher cards have complimentary expedited shipping.
- Immediately before a replacement order, unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Do this even if the customer does not know their replacement history. A pending or shipped order blocks a new replacement; delivered/cancelled orders do not. Also apply the documented 60-day replacement-tier limit (premium and above: four).

Do not transfer or declare eligibility unknown merely because the customer is unsure about a prior replacement when the pending-order check is available. If the check and tier-limit review permit a replacement, unlock and call `order_replacement_credit_card_7291` with the account identifier, `fraud_suspected` reason, confirmed address, requested speed, fee acknowledgement when a fee applies, and relevant notes. For a permitted fraud reissue, tell the customer that the old card is cancelled and delivery is 2–3 business days expedited or 7–10 business days standard.

## Determine provisional credit per dispute

A dispute is eligible only when every condition is true:

1. The card account was open at least 60 days.
2. The reason is fraud, duplicate, or goods/services not received with a purchase more than 30 days ago.
3. The amount is at least $25 and no greater than the tier maximum (Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000).
4. The pre-batch dispute-history count is no more than two in the preceding 12 months.
5. For every non-fraud dispute, the customer contacted the merchant.

An ineligible provisional-credit result does **not** block filing: submit the dispute with `eligible_for_provisional_credit: false`. Missing required dispute fields, an unverified transaction, or unresolved contradictory customer instructions do block that individual filing.

## Build payloads

Use `scripts/build_dispute_plan.py` to validate collected facts and build exact payloads. It is deterministic and performs no bank action.

It reads one JSON object from stdin and writes one JSON object to stdout. Required input fields are:

- `current_date`: `MM/DD/YYYY`.
- `profile`: `full_name`, `user_id`, `phone`, `email`, `address`.
- `accounts`: nonempty objects containing `account_id`, `card_type`, `date_of_account_open` (`MM/DD/YYYY`), and retrieved `card_last_4_digits`.
- `prior_dispute_count_12_months`, a nonnegative integer from the history lookup, or `prior_disputes`, a list with `dispute_date` values.
- `disputes`: nonempty objects with `transaction_id`, `account_id`, `transaction_amount`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `contacted_merchant`, and `card_action`; add `partial_refund_amount` only for a partial refund.

Example:

```sh
python scripts/build_dispute_plan.py <<'JSON'
{"current_date":"MM/DD/YYYY","profile":{"full_name":"<name>","user_id":"<user-id>","phone":"<phone>","email":"<email>","address":"<address>"},"accounts":[{"account_id":"<account-id>","card_type":"Gold Rewards Card","date_of_account_open":"MM/DD/YYYY","card_last_4_digits":"1234"}],"prior_dispute_count_12_months":0,"disputes":[{"transaction_id":"<transaction-id>","account_id":"<account-id>","transaction_amount":100.0,"purchase_date":"MM/DD/YYYY","issue_noticed_date":"MM/DD/YYYY","dispute_reason":"duplicate_charge","resolution_requested":"full_refund","contacted_merchant":true,"card_action":"cancel_and_reissue"}]}
JSON
```

The result contains `ok`, `validation_errors`, `prior_dispute_count_12_months`, `dispute_assessments`, and `payloads`. Only proceed with generated payloads if `ok` is true. Review that there is one payload for each selected transaction and that every payload has the intended action and provisional-credit flag.

## Mandatory filing sequence

1. Resolve validation errors, but do not stop merely because provisional credit is false.
2. If reissue was requested, perform the pending-order check and, if allowed, submit the replacement order. A replacement may be ordered before the disputes.
3. Unlock `file_credit_card_transaction_dispute_4829`.
4. Submit **every** generated payload separately through `call_discoverable_agent_tool` using `agent_tool_name: file_credit_card_transaction_dispute_4829` and a JSON-serialized `arguments` payload.
5. Retain each result. If one call fails, do not claim it was filed; address that transaction's failure without omitting the other valid submissions. Do not blindly retry after an ambiguous result.
6. Confirm the individually submitted disputes and replacement outcome. Explain that provisional credit, when eligible, is temporary and can be reversed after investigation.

The script neither unlocks nor calls banking tools. The execution agent must perform the discoverable-tool calls above; script output is a filing plan, not a completed dispute or replacement order.
