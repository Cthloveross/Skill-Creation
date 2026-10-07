---
name: credit-card-transaction-dispute
version: 1.0.0
description: File one or more credit-card transaction disputes after identity verification, while validating required filing fields and determining provisional-credit eligibility from account, transaction, and dispute-history data. Use when a customer reports fraudulent, duplicate, billing, delivery, product-description, subscription, or missing-refund card charges.
---

# Credit Card Transaction Dispute

Use this Skill to file each eligible, fully specified credit-card dispute independently. It supports batches across cards, but never combines transactions into one dispute.

## Required information

For every transaction, collect or retrieve:

- Transaction ID, amount, transaction purchase date, card/account association, and card last four digits.
- Customer full name, user ID, registered phone, registered email, and registered address.
- Date the customer noticed the issue (`MM/DD/YYYY`). If they noticed it today, use `get_current_time` to establish the date.
- Whether the merchant was contacted (`true` or `false`). Fraud does not require merchant contact for provisional-credit eligibility; the filing field is still required.
- A supported dispute reason:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- A supported requested resolution:
  - `full_refund`
  - `partial_refund` — requires an exact numeric `partial_refund_amount`
  - `reversal_of_charge`
- Card action: `keep_active` or `cancel_and_reissue`.

Do not infer a partial-refund amount from a total charge, normal bill, merchant promise, or description. Leave that transaction pending until the customer supplies an exact amount or valid documentation establishes it. Other fully specified disputes may proceed.

## Safe operating sequence

1. **Verify identity before taking action.** Obtain confirmation of at least two of date of birth, email, phone, and address; retrieve the registered record; get the current time; then call `log_verification` with the complete registered identity record and timestamp. If identity cannot be verified, do not file disputes.
2. Retrieve the customer’s card accounts and transaction history. Match each customer report to exactly one transaction ID and card. Do not file if a transaction match is ambiguous or absent.
3. For every involved account, obtain its final four digits. Unlock `get_card_last_4_digits` if necessary, then call it with the credit-card account ID. Do not substitute an account ID, card type, or an unverified customer-provided value for the last four digits.
4. Obtain prior credit-card disputes for the user. Unlock and call `get_user_dispute_history_7291` with `user_id` if it is available as a discoverable tool. Retain dispute filing dates for the rolling 12-month count.
5. Build normalized case input and run the packaged planner:

   ```sh
   python3 scripts/dispute_workflow.py <<'JSON'
   {"as_of":"2025-01-31","profile":{"full_name":"...","user_id":"...","phone":"...","email":"...","address":"..."},"prior_disputes":[{"dispute_date":"2024-08-01"}],"transactions":[{"transaction_id":"...","amount":50.00,"purchase_date":"01/01/2025","issue_noticed_date":"01/31/2025","reason":"duplicate_charge","resolution_requested":"full_refund","contacted_merchant":true,"card_action":"keep_active","card_last_4_digits":"1234","card_type":"Gold Rewards Card","account_open_date":"01/01/2024"}]}
   JSON
   ```

   The script reads one JSON object from stdin and writes one JSON object to stdout. See the script docstring for the complete schema. Review `errors` for every case; only cases with `ready: true` have a `filing_arguments` object.
6. Explain that provisional credit, when eligible, is temporary during investigation and can be made permanent or reversed after the outcome. Do not promise it where the planner says ineligible.
7. Unlock `file_credit_card_transaction_dispute_4829` once. For each ready case, call `call_discoverable_agent_tool` separately with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: the compact JSON serialization of that case’s `filing_arguments`.

   Preserve the boolean and numeric JSON types; do not turn them into quoted strings. Include `partial_refund_amount` only for `partial_refund`.
8. Record each filing result. A failure for one transaction does not authorize altering, assuming, or silently skipping another. Tell the customer which disputes were filed, which remain pending and why, and any returned case/reference IDs.

## Provisional-credit rules applied by the planner

Eligibility is `true` only when all conditions hold:

- The card account was open at least 60 days as of the filing date.
- The reason is fraud, duplicate charge, or goods/services not received. The last category additionally requires a purchase more than 30 days before filing.
- Amount is at least $25 and no greater than the applicable tier cap: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.
- The customer has filed no more than two disputes in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant.

The planner requires evidence for every eligibility factor. Missing dates, unknown card tiers, missing prior-history data, or malformed amounts make a case not ready rather than treating unknown information as `false`.

## Failure handling

- Ask a focused follow-up for missing required filing fields.
- If a tool reports an error, do not claim a dispute was filed; retain the transaction details and report the problem.
- If dispute history is empty, treat it as zero prior disputes only when the tool successfully returned an empty result. If unavailable or incomplete, obtain a usable result before determining eligibility.
- Never choose `cancel_and_reissue` merely because a charge is fraud-related; follow the customer’s card-action choice.
