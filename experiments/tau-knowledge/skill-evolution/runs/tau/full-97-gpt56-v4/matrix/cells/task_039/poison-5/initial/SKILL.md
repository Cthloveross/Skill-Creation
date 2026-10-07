---
name: credit-card-disputes-and-replacement
summary: Safely handle one or more credit-card transaction disputes together with a requested replacement card, including identity verification, provisional-credit decisions, replacement prerequisites, and discovered-tool calls.
---

# Credit Card Disputes and Replacement

Use this Skill when a verified customer reports credit-card charge problems, asks to dispute one or more transactions, requests a replacement card, or both. Treat each transaction as a separate dispute submission. Do not infer missing dispute facts, identity answers, a replacement address, shipping choice, or eligibility facts.

## 1. Establish identity and scope

1. Locate the customer and their credit-card accounts using the normal banking lookup tools.
2. Before account-changing actions, confirm **two of four** record fields with the customer: date of birth, registered email, registered phone, and registered address. Do not disclose unconfirmed values as a verification challenge. After two match, obtain the current timestamp and call `log_verification` with all required record fields and that timestamp.
3. Identify the affected account/card and verify every selected transaction belongs to that customer and card. Obtain the user ID, account ID, card type/tier, transaction IDs, amount, and purchase date from normal lookup results.
4. For every proposed dispute, obtain and record:
   - the transaction ID;
   - exactly one normalized reason: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
   - whether the merchant was contacted (`true`/`false`);
   - when the issue was noticed, formatted `MM/DD/YYYY`;
   - resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; and a positive partial-refund amount only for `partial_refund`.
5. Obtain one customer-wide card action: `keep_active` or `cancel_and_reissue`. If replacement is requested or needed because of fraud, use `cancel_and_reissue` only after the customer confirms that choice.
6. Retrieve the card last four digits using `get_card_last_4_digits` with the **account-level** credit-card account ID. Never guess the last four digits.
7. Retrieve dispute history with `get_user_dispute_history_7291` and count disputes filed in the 12 months immediately before the current filing. If tool data are unavailable or ambiguous, do not claim eligibility; explain the limitation and obtain/escalate for the needed review.

The knowledge base names agent-discoverable tools. Unlock each one before its first use with `unlock_discoverable_agent_tool` using the tool name, then call it through `call_discoverable_agent_tool`. In the provided tool schema these fields are named `agent_tool_name` and `arguments`; pass the tool's argument object as a JSON string in `arguments`.

## 2. Decide provisional-credit eligibility per transaction

Use `scripts/provisional_credit.py` to make the repeatable policy calculation from supplied account, transaction, tier, history, and current-date facts. It is a decision aid; confirm its inputs against live records.

A transaction is eligible only if **all** are true:

- account has been open at least 60 days;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (the latter only if purchased more than 30 days ago);
- amount is at least $25 and no more than the card-tier maximum;
- no more than 2 disputes were filed in the preceding 12 months; and
- for every non-fraud reason, the customer contacted the merchant.

Tier caps are Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. A noneligible dispute may still be filed; set `eligible_for_provisional_credit` to `false` rather than declining the dispute. Explain that provisional credit is temporary while the dispute is investigated.

## 3. File every complete dispute

For each complete, verified transaction:

1. Unlock `file_credit_card_transaction_dispute_4829` if not already unlocked.
2. Call it once with a JSON object containing all required fields:
   `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.
3. Include `partial_refund_amount` only if `resolution_requested` is `partial_refund`.
4. Preserve factual merchant-contact and issue context in available case/order notes when a relevant notes field exists; do not invent it.

Use customer/profile data only after successful identity verification. Use `MM/DD/YYYY` for both dates. Handle tool failure separately for each transaction: do not say it was filed unless the tool reports success, do not retry an operation whose outcome is reported as unknown, and clearly identify any unfiled items for follow-up.

## 4. Replacement-card workflow

A replacement requires its own prerequisites even when it accompanies a fraud dispute.

1. Ask and record exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Do not substitute a dispute reason string.
2. Confirm the full shipping address with the customer, including unit/suite where applicable. A profile address is not a confirmed shipping address until the customer affirms it or supplies an alternate.
3. Check for pending replacements using `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any non-final order (such as pending or shipped) blocks a new replacement. Final delivered/cancelled orders do not.
4. Confirm replacement-limit eligibility within the prior 60 days: Entry up to 2, Mid up to 3, Premium and above up to 4. If the available records cannot establish the count, do not represent the customer as eligible; request the proper review or use the normal eligibility path. Never unlock or call the replacement-order tool unless eligibility is confirmed.
5. Offer standard shipping (7–10 business days, free) and expedited (2–3 business days). Advise expedited fees: Entry $15, Mid $10, Premium and above $0. Strongly recommend expedited for `fraud_suspected` or `stolen` and remind the customer to review recent transactions. Obtain the customer's speed selection. If a fee applies, obtain explicit fee consent; `expedited_fee_acknowledgement` must capture that consent. For standard or complimentary expedited service, record the applicable acknowledgement according to the live tool's accepted format rather than fabricating consent.
6. Unlock and call `order_replacement_credit_card_7291` only after all above checks pass. Supply the account identifier, reason, confirmed `shipping_address`, `shipping_speed` (`standard` or `expedited`), `expedited_fee_acknowledgement`, and factual `notes` (such as fraud context, travel dates, or delivery instructions).

If pending replacement or a tier limit blocks the request, explain that another request cannot be placed until the current one is delivered/cancelled or that a manual review is needed for a legitimate additional request. Do not call the ordering tool.

## 5. Closeout

Report only successfully completed filings/orders. For a successful replacement, explain that the old card is cancelled for new purchases, a new number and CVV will be issued, and the account number remains unchanged. State the selected delivery window and that email notifications arrive when the order is placed and when it ships. For fraud/stolen matters, remind the customer to review recent transactions and dispute unauthorized activity. Document the interaction and all completed order/dispute details in the available customer-record workflow; if no record-writing tool is available, give a concise factual completion summary rather than claiming documentation occurred.

## Decision helper

Run from the package root, supplying JSON on standard input:

```bash
python3 scripts/provisional_credit.py <<'JSON'
{"current_date":"2025-01-01","account_open_date":"2024-01-01","card_tier":"premium","prior_disputes_12_months":0,"disputes":[{"transaction_id":"...","reason":"duplicate_charge","amount":100,"purchase_date":"2024-11-01","contacted_merchant":true}]}
JSON
```

Input fields are `current_date`, `account_open_date` (ISO `YYYY-MM-DD` or `MM/DD/YYYY`), `card_tier`, `prior_disputes_12_months`, and a `disputes` list. Each dispute supplies `transaction_id`, `reason`, `amount`, `purchase_date`, and `contacted_merchant`. The script writes `{"results":[...]}`. Each result contains `eligible_for_provisional_credit`, the effective cap, and explicit failed conditions. Invalid or missing policy inputs are reported as failed conditions, not treated as eligible.
